import json
from collections.abc import Generator
from typing import Any
from typing import cast

from pydantic import BaseModel
from sqlalchemy.orm import Session

from onyx.chat.chat_utils import llm_doc_from_inference_section
from onyx.chat.llm_response_handler import LLMCall
from onyx.chat.models import AnswerStyleConfig
from onyx.chat.models import ContextualPruningConfig
from onyx.chat.models import DocumentPruningConfig
from onyx.chat.models import LlmDoc
from onyx.chat.models import OnyxContext
from onyx.chat.models import OnyxContexts
from onyx.chat.models import PromptConfig
from onyx.chat.models import SectionRelevancePiece
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.chat.prompt_builder.citations_prompt import compute_max_llm_input_tokens
from onyx.chat.prune_and_merge import prune_and_merge_sections
from onyx.chat.prune_and_merge import prune_sections
from onyx.configs.chat_configs import CONTEXT_CHUNKS_ABOVE
from onyx.configs.chat_configs import CONTEXT_CHUNKS_BELOW
from onyx.configs.constants import MessageType
from onyx.configs.model_configs import GEN_AI_MODEL_FALLBACK_MAX_TOKENS
from onyx.context.search.enums import LLMEvaluationType
from onyx.context.search.enums import QueryFlow
from onyx.context.search.enums import SearchType
from onyx.context.search.models import IndexFilters
from onyx.context.search.models import InferenceSection
from onyx.context.search.models import RerankingDetails
from onyx.context.search.models import RetrievalDetails
from onyx.context.search.models import SearchRequest
from onyx.context.search.pipeline import SearchPipeline
from onyx.db.models import Persona
from onyx.db.models import User
from onyx.db.models import Prompt
from onyx.file_store.models import InMemoryChatFile, ChatFileType
from onyx.llm.interfaces import LLM
from onyx.llm.models import PreviousMessage
from onyx.secondary_llm_flows.choose_search import check_if_need_search
from onyx.secondary_llm_flows.query_expansion import history_based_query_rephrase
from onyx.tools.message import ToolCallSummary
from onyx.tools.models import ToolResponse
from onyx.tools.tool import Tool
from onyx.tools.tool_implementations.search.search_utils import llm_doc_to_dict
from onyx.tools.tool_implementations.search_like_tool_utils import (
    build_next_prompt_for_search_like_tool,
)
from onyx.tools.tool_implementations.search_like_tool_utils import (
    FINAL_CONTEXT_DOCUMENTS_ID,
)
from onyx.tools.tool_implementations.search_like_tool_utils import (
    ORIGINAL_CONTEXT_DOCUMENTS_ID,
)
from onyx.utils.logger import setup_logger
from onyx.utils.special_types import JSON_ro
from langchain.schema import SystemMessage, HumanMessage

logger = setup_logger()

SEARCH_RESPONSE_SUMMARY_ID = "search_response_summary"
SEARCH_DOC_CONTENT_ID = "search_doc_content"
SECTION_RELEVANCE_LIST_ID = "section_relevance_list"
SEARCH_EVALUATION_ID = "llm_doc_eval"

class SearchResponseSummary(BaseModel):
    top_sections: list[InferenceSection]
    rephrased_query: str | None = None
    predicted_flow: QueryFlow | None
    predicted_search: SearchType | None
    final_filters: IndexFilters
    recency_bias_multiplier: float


SEARCH_TOOL_DESCRIPTION = """
Runs a semantic search over the user's knowledge base. The default behavior is to use this tool. \
The only scenario where you should not use this tool is if:

- There is sufficient information in chat history to FULLY and ACCURATELY answer the query AND \
additional information or details would provide little or no value.
- The query is some form of request that does not require additional information to handle.
- When a query contains text in double quotes (e.g. "exact phrase"), only return sources that contain that exact quoted text. Do not modify or alter the quoted text in any way.

HINT: if you are unfamiliar with the user input OR think the user input is a typo, use this tool.
"""

# Default fallback prompts
DEFAULT_SEARCH_TOOL_DESCRIPTION_PROMPT = """
Runs a semantic search over the user's knowledge base. The default behavior is to use this tool.
"""

DEFAULT_SEARCH_QUERY_PROMPT = """
When processing user queries, maintain the original query intent while ensuring proper formatting.
If the query cannot be answered with available knowledge bases, return an empty string to indicate no response should be provided.
Preserve specific input formats and handle any special query patterns appropriately.
"""

DEFAULT_SEARCH_DATA_SOURCE_SELECTOR_PROMPT = """Give empty string or empty array for the parameters value"""

DEFAULT_SEARCH_FALLBACK_DATA_SOURCE_SELECTOR_PROMPT = """Give empty string or empty array for the parameters value"""

DEFAULT_SEARCH_STATUS_PROMPT = """
"""

class SearchTool(Tool):
    _NAME = "run_search"
    _DISPLAY_NAME = "Search Tool"
    _DESCRIPTION = SEARCH_TOOL_DESCRIPTION

    def __init__(
        self,
        db_session: Session,
        user: User | None,
        persona: Persona,
        retrieval_options: RetrievalDetails | None,
        prompt_config: PromptConfig,
        llm: LLM,
        fast_llm: LLM,
        pruning_config: DocumentPruningConfig,
        answer_style_config: AnswerStyleConfig,
        evaluation_type: LLMEvaluationType,
        # if specified, will not actually run a search and will instead return these
        # sections. Used when the user selects specific docs to talk to
        selected_sections: list[InferenceSection] | None = None,
        chunks_above: int | None = None,
        chunks_below: int | None = None,
        full_doc: bool = False,
        bypass_acl: bool = False,
        rerank_settings: RerankingDetails | None = None,
        uploaded_files: list[InMemoryChatFile] | None = None,
    ) -> None:
        self.user = user
        self.persona = persona
        self.retrieval_options = retrieval_options
        self.prompt_config = prompt_config
        self.llm = llm
        self.fast_llm = fast_llm
        self.evaluation_type = evaluation_type

        self.selected_sections = selected_sections
        self._uploaded_files = uploaded_files or []

        self.full_doc = full_doc
        self.bypass_acl = bypass_acl
        self.db_session = db_session

        # Only used via API
        self.rerank_settings = rerank_settings

        self.chunks_above = (
            chunks_above
            if chunks_above is not None
            else (
                persona.chunks_above
                if persona.chunks_above is not None
                else CONTEXT_CHUNKS_ABOVE
            )
        )
        self.chunks_below = (
            chunks_below
            if chunks_below is not None
            else (
                persona.chunks_below
                if persona.chunks_below is not None
                else CONTEXT_CHUNKS_BELOW
            )
        )

        # For small context models, don't include additional surrounding context
        # The 3 here for at least minimum 1 above, 1 below and 1 for the middle chunk
        max_llm_tokens = compute_max_llm_input_tokens(self.llm.config)
        if max_llm_tokens < 3 * GEN_AI_MODEL_FALLBACK_MAX_TOKENS:
            self.chunks_above = 0
            self.chunks_below = 0

        num_chunk_multiple = self.chunks_above + self.chunks_below + 1

        self.answer_style_config = answer_style_config
        self.contextual_pruning_config = (
            ContextualPruningConfig.from_doc_pruning_config(
                num_chunk_multiple=num_chunk_multiple, doc_pruning_config=pruning_config
            )
        )

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def description(self) -> str:
        search_tool_description_prompt = self.persona.prompts[0].search_tool_description if self.persona.prompts[0].search_tool_description else DEFAULT_SEARCH_TOOL_DESCRIPTION_PROMPT
        return search_tool_description_prompt

    @property
    def searchQueryPrompt(self) -> str:
        search_query_prompt = self.persona.prompts[0].search_query_prompt if self.persona.prompts[0].search_query_prompt else DEFAULT_SEARCH_QUERY_PROMPT
        return search_query_prompt
    
    @property
    def searchDataSourceSelectorPrompt(self) -> str:
        search_data_source_selector_prompt = self.persona.prompts[0].search_data_source_selector_prompt if self.persona.prompts[0].search_data_source_selector_prompt else DEFAULT_SEARCH_DATA_SOURCE_SELECTOR_PROMPT
        return search_data_source_selector_prompt

    @property
    def searchFallbackDataSourceSelectorPrompt(self) -> str:
        #search_fallback_data_source_selector_prompt = self.persona.prompts[0].search_fallback_data_source_selector_prompt if self.persona.prompts[0].search_fallback_data_source_selector_prompt else DEFAULT_SEARCH_FALLBACK_DATA_SOURCE_SELECTOR_PROMPT
        search_fallback_data_source_selector_prompt = self.persona.prompts[0].search_data_source_selector_prompt if self.persona.prompts[0].search_data_source_selector_prompt else DEFAULT_SEARCH_FALLBACK_DATA_SOURCE_SELECTOR_PROMPT
        return search_fallback_data_source_selector_prompt

    @property
    def searchStatusPrompt(self) -> str:
        search_status_prompt = self.searchQueryPrompt
        return search_status_prompt

    @property
    def display_name(self) -> str:
        return self._DISPLAY_NAME

    """For explicit tool calling"""

    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": self.searchQueryPrompt,
                        },
                        "solution_kb": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": self.searchDataSourceSelectorPrompt,
                        },
                        "fallback_kb": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": self.searchDataSourceSelectorPrompt,
                        },
                        "status": {
                            "type": "string",
                            "description": self.searchDataSourceSelectorPrompt,
                        },
                        "ticket_id": {
                            "type": "string",
                            "description": "ticket id or number of the ticket asked by user in the query. give empty string if user is not asking about the freshdesk tickets or tickets",
                        }
                    },
                    "required": ["query", "solution_kb", "status", "ticket_id"],
                },
            },
        }

    def build_tool_message_content(
        self, *args: ToolResponse
    ) -> str | list[str | dict[str, Any]]:
        final_context_docs_response = next(
            response for response in args if response.id == FINAL_CONTEXT_DOCUMENTS_ID
        )
        final_context_docs = cast(list[LlmDoc], final_context_docs_response.response)

        result = {
            "search_results": [
                llm_doc_to_dict(doc, ind)
                for ind, doc in enumerate(final_context_docs)
            ]
        }

        # Include uploaded files if they exist
        if self._uploaded_files:
            uploaded_files_data = []
            for file in self._uploaded_files:
                file_data = {
                    "filename": file.filename,
                    "file_type": file.file_type.value,
                }
                
                # Include file content for text files
                if file.file_type in [ChatFileType.PLAIN_TEXT, ChatFileType.CSV, ChatFileType.DOC]:
                    try:
                        content = file.content.decode('utf-8') if isinstance(file.content, bytes) else file.content
                        file_data["content"] = content
                    except UnicodeDecodeError:
                        file_data["content"] = f"[Binary file: {file.filename}]"
                else:
                    # For other file types, include a reference
                    file_data["content"] = f"[File: {file.filename}]"
                
                uploaded_files_data.append(file_data)
            
            result["uploaded_files"] = uploaded_files_data

        return json.dumps(result)

    """For LLMs that don't support tool calling"""

    def get_args_for_non_tool_calling_llm(
        self,
        query: str,
        history: list[PreviousMessage],
        llm: LLM,
        prompt_config: PromptConfig,
        force_run: bool = False,
    ) -> dict[str, Any] | None:
        logger.info(f"get_args_for_non_tool_calling_llm in {query}")
        if not force_run and not check_if_need_search(
            query=query, history=history, llm=llm
        ):
            return None
        
        # Use the uploaded files that were passed to the constructor
        uploaded_files = self._uploaded_files
        if uploaded_files:
            logger.info(f"[FILE TRACKING] Using {len(uploaded_files)} uploaded files for query rephrase")
            for file in uploaded_files:
                logger.info(f"[FILE TRACKING] File: {file.filename}, Type: {file.file_type.value}")
        
        # First rephrase the query with file context
        rephrased_query = history_based_query_rephrase(
            query=query, history=history, llm=llm, note=prompt_config.history_query_rephrase,
            uploaded_files=uploaded_files
        )
        
        # Create a system message to guide the LLM
        system_message = SystemMessage(content="""You are a helpful assistant that analyzes queries to determine the most appropriate knowledge bases for searching.

Key Principles:
1. Consider the query type and intent:
   - What kind of information is being sought?
   - What context would be most relevant?
   - What sources typically contain this type of information?

2. Search Strategy:
   - Include knowledge bases that might contain primary information
   - Include knowledge bases that might contain supporting context
   - Consider both explicit and implicit information sources

3. Return Format:
   - Return an array of ALL relevant knowledge base names
   - Include any knowledge base that might contain relevant information
   - Do not limit yourself to just the most obvious sources

Remember: It's better to include a potentially relevant knowledge base than to miss important information.""")

        # Create the user message with the query
        user_message = HumanMessage(content=f"""Please analyze this query and determine the most appropriate knowledge bases to search:

Query: {query}

Previous Context: {history[-1].message if history else 'No previous context'}

Consider:
1. What type of information is being sought?
2. What knowledge bases might contain this information?
3. What supporting context might be relevant?
4. If this is a follow-up query, maintain focus on the original subject

{self.searchDataSourceSelectorPrompt}

Additionally, consider which knowledge bases might be useful as fallback options if the primary search doesn't yield sufficient results:

{self.searchFallbackDataSourceSelectorPrompt}""")

        try:
            # Call the LLM with tool calling enabled
            response = llm.invoke(
                prompt=f"{system_message.content}\n\n{user_message.content}",
                tools=[self.tool_definition()],
                tool_choice="required"
            )
            
            # Extract the tool call arguments
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tool_call = response.tool_calls[0]
                args = tool_call.get('args', {})
                
                return {
                    "query": rephrased_query,
                    "solution_kb": args.get("solution_kb", []),
                    "fallback_kb": args.get("fallback_kb", []),
                    "status": args.get("status", ""),
                    "ticket_id": args.get("ticket_id", "")
                }
            else:
                logger.error("No tool call found in LLM response")
                return {
                    "query": rephrased_query,
                    "solution_kb": [],
                    "fallback_kb": [],
                    "status": "",
                    "ticket_id": ""
                }
                
        except Exception as e:
            logger.error(f"Error in tool call analysis: {e}")
            return {
                "query": rephrased_query,
                "solution_kb": [],
                "fallback_kb": [],
                "status": "",
                "ticket_id": ""
            }

    """Actual tool execution"""

    def _build_response_for_specified_sections(
        self, query: str
    ) -> Generator[ToolResponse, None, None]:
        if self.selected_sections is None:
            raise ValueError("Sections must be specified")

        yield ToolResponse(
            id=SEARCH_RESPONSE_SUMMARY_ID,
            response=SearchResponseSummary(
                rephrased_query=None,
                top_sections=[],
                predicted_flow=None,
                predicted_search=None,
                final_filters=IndexFilters(access_control_list=None),  # dummy filters
                recency_bias_multiplier=1.0,
            ),
        )

        # Build selected sections for specified documents
        selected_sections = [
            SectionRelevancePiece(
                relevant=True,
                document_id=section.center_chunk.document_id,
                chunk_id=section.center_chunk.chunk_id,
            )
            for section in self.selected_sections
        ]

        yield ToolResponse(
            id=SECTION_RELEVANCE_LIST_ID,
            response=selected_sections,
        )

        final_context_sections = prune_and_merge_sections(
            sections=self.selected_sections,
            section_relevance_list=None,
            prompt_config=self.prompt_config,
            llm_config=self.llm.config,
            question=query,
            contextual_pruning_config=self.contextual_pruning_config,
        )

        llm_docs = [
            llm_doc_from_inference_section(section)
            for section in final_context_sections
        ]

        yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=llm_docs)

    def run(self, **kwargs: str) -> Generator[ToolResponse, None, None]:
        query = cast(str, kwargs["query"])
        # Ensure solution_kb and fallback_kb are always lists
        solution_kb = kwargs.get("solution_kb", [])
        fallback_kb = kwargs.get("fallback_kb", [])
        if isinstance(solution_kb, str):
            solution_kb = [solution_kb]
        if isinstance(fallback_kb, str):
            fallback_kb = [fallback_kb]
        status = cast(str, kwargs.get("status", ""))
        ticket_id = cast(str, kwargs.get("ticket_id", ""))
        
        if self.selected_sections:
            yield from self._build_response_for_specified_sections(query)
            return
        
        # Get existing filters from retrieval_options if they exist
        existing_filters = self.retrieval_options.filters if self.retrieval_options else None
        logger.info(f"Existing filters: {existing_filters}")
        
        # Check if user has already selected any source - if so, skip solution_kb/fallback_kb logic
        user_has_selected_source = False
        if existing_filters:
            user_has_selected_source = bool(
                existing_filters.source_type or 
                existing_filters.connector_name or 
                existing_filters.document_set
            )
        
        if user_has_selected_source:
            logger.info("User has already selected a source, using existing filters only not any solution_kb")
            # todo: we need to remove this indexfilters and use basefilters only
            # merged_filters = existing_filters
            # Create IndexFilters from existing BaseFilters to ensure compatibility
            merged_filters = IndexFilters(
                tenant_id=existing_filters.tenant_id,
                access_control_list=existing_filters.access_control_list,
                source_type=existing_filters.source_type,
                tags=existing_filters.tags,
                document_set=existing_filters.document_set,
                time_range=existing_filters.time_range,
                connector_name=existing_filters.connector_name,
                status=None,  # Not relevant when user has pre-selected source
                ticket_id=None  # Not relevant when user has pre-selected source
            )
        else:
            # First try with solution_kb
            merged_filters = IndexFilters(
                tenant_id=existing_filters.tenant_id if existing_filters else None,
                access_control_list=existing_filters.access_control_list if existing_filters else None,
                source_type=existing_filters.source_type if existing_filters else None,
                tags=existing_filters.tags if existing_filters else None,  
                document_set=existing_filters.document_set if existing_filters else None,
                time_range=existing_filters.time_range if existing_filters else None,
                connector_name=solution_kb,  # Use solution_kb first
                status=status if status else None,
                ticket_id=ticket_id if ticket_id else None
            )

        search_pipeline = SearchPipeline(
            search_request=SearchRequest(
                query=query,
                evaluation_type=self.evaluation_type,
                human_selected_filters=merged_filters,
                persona=self.persona,
                offset=self.retrieval_options.offset if self.retrieval_options else None,
                limit=self.retrieval_options.limit if self.retrieval_options else None,
                rerank_settings=self.rerank_settings,
                chunks_above=self.chunks_above,
                chunks_below=self.chunks_below,
                full_doc=self.full_doc,
                enable_auto_detect_filters=self.retrieval_options.enable_auto_detect_filters if self.retrieval_options else None,
            ),
            user=self.user,
            llm=self.llm,
            fast_llm=self.fast_llm,
            bypass_acl=self.bypass_acl,
            db_session=self.db_session,
            prompt_config=self.prompt_config,
        )

        # Only try fallback if user hasn't already selected a source
        should_try_fallback = False
        if not user_has_selected_source:
            if not search_pipeline.final_context_sections:
                should_try_fallback = True
                logger.info("No results found in solution_kb, trying fallback_kb")
            elif search_pipeline.section_relevance is not None:
                # LLM relevance filtering is enabled, check if any section is relevant
                has_relevant_sections = any(search_pipeline.section_relevance_list)
                if not has_relevant_sections:
                    should_try_fallback = True
                    logger.info("Solution KB results not relevant, trying fallback_kb")
                else:
                    logger.info(f"Relevant details found in solution_kb: {len(search_pipeline.final_context_sections)} sections")
            else:
                # LLM relevance filtering is disabled, so all sections are considered relevant
                logger.info(f"LLM relevance filtering disabled, using all solution_kb results: {len(search_pipeline.final_context_sections)} sections")
        else:
            logger.info("User has already selected a source, using existing filters only not any fallback_kb")
        
        
        if should_try_fallback and fallback_kb:
            # Try with fallback_kb
            merged_filters = IndexFilters(
                tenant_id=existing_filters.tenant_id if existing_filters else None,
                access_control_list=existing_filters.access_control_list if existing_filters else None,
                source_type=existing_filters.source_type if existing_filters else None,
                tags=existing_filters.tags if existing_filters else None,
                document_set=existing_filters.document_set if existing_filters else None,
                time_range=existing_filters.time_range if existing_filters else None,
                connector_name=fallback_kb,  # Use fallback_kb
                status=status if status else None,
                ticket_id=ticket_id if ticket_id else None
            )

            search_pipeline = SearchPipeline(
                search_request=SearchRequest(
                    query=query,
                    evaluation_type=self.evaluation_type,
                    human_selected_filters=merged_filters,
                    persona=self.persona,
                    offset=self.retrieval_options.offset if self.retrieval_options else None,
                    limit=self.retrieval_options.limit if self.retrieval_options else None,
                    rerank_settings=self.rerank_settings,
                    chunks_above=self.chunks_above,
                    chunks_below=self.chunks_below,
                    full_doc=self.full_doc,
                    enable_auto_detect_filters=self.retrieval_options.enable_auto_detect_filters if self.retrieval_options else None,
                ),
                user=self.user,
                llm=self.llm,
                fast_llm=self.fast_llm,
                bypass_acl=self.bypass_acl,
                db_session=self.db_session,
                prompt_config=self.prompt_config,
            )
            logger.info(f"Fallback KB search results count: {len(search_pipeline.final_context_sections) if search_pipeline.final_context_sections else 0}")

            # Check if fallback KB results are relevant
            if search_pipeline.section_relevance is not None:
                has_relevant_sections = any(search_pipeline.section_relevance_list)
                if not has_relevant_sections:
                    logger.info("Fallback KB results not relevant, returning empty results")
                    # Return empty results if no relevant sections found
                    yield ToolResponse(
                        id=SEARCH_RESPONSE_SUMMARY_ID,
                        response=SearchResponseSummary(
                            rephrased_query=query,
                            top_sections=[],
                            predicted_flow=search_pipeline.predicted_flow,
                            predicted_search=search_pipeline.predicted_search_type,
                            final_filters=search_pipeline.search_query.filters,
                            recency_bias_multiplier=search_pipeline.search_query.recency_bias_multiplier,
                        ),
                    )
                    yield ToolResponse(id=SEARCH_DOC_CONTENT_ID, response=OnyxContexts(contexts=[]))
                    yield ToolResponse(id=SECTION_RELEVANCE_LIST_ID, response=[])
                    yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=[])
                    return
                else:
                    logger.info(f"Relevant details found in fallback_kb: {len(search_pipeline.final_context_sections)} sections")
            else:
                # LLM relevance filtering is disabled, so all sections are considered relevant
                logger.info(f"LLM relevance filtering disabled, using all fallback_kb results: {len(search_pipeline.final_context_sections)} sections")
        elif should_try_fallback and not fallback_kb:
            # Try searching across all datasources when fallback_kb is empty
            logger.info("Fallback KB is empty, searching across all datasources")
            merged_filters = IndexFilters(
                tenant_id=existing_filters.tenant_id if existing_filters else None,
                access_control_list=existing_filters.access_control_list if existing_filters else None,
                source_type=existing_filters.source_type if existing_filters else None,
                tags=existing_filters.tags if existing_filters else None,
                document_set=existing_filters.document_set if existing_filters else None,
                time_range=existing_filters.time_range if existing_filters else None,
                connector_name=None,  # No connector filter - search all datasources
                status=status if status else None,
                ticket_id=ticket_id if ticket_id else None
            )

            search_pipeline = SearchPipeline(
                search_request=SearchRequest(
                    query=query,
                    evaluation_type=self.evaluation_type,
                    human_selected_filters=merged_filters,
                    persona=self.persona,
                    offset=self.retrieval_options.offset if self.retrieval_options else None,
                    limit=self.retrieval_options.limit if self.retrieval_options else None,
                    rerank_settings=self.rerank_settings,
                    chunks_above=self.chunks_above,
                    chunks_below=self.chunks_below,
                    full_doc=self.full_doc,
                    enable_auto_detect_filters=self.retrieval_options.enable_auto_detect_filters if self.retrieval_options else None,
                ),
                user=self.user,
                llm=self.llm,
                fast_llm=self.fast_llm,
                bypass_acl=self.bypass_acl,
                db_session=self.db_session,
                prompt_config=self.prompt_config,
            )
            logger.info(f"All datasources search results count: {len(search_pipeline.final_context_sections) if search_pipeline.final_context_sections else 0}")

            # Check if all datasources results are relevant
            if search_pipeline.section_relevance is not None:
                has_relevant_sections = any(search_pipeline.section_relevance_list)
                if not has_relevant_sections:
                    logger.info("All datasources results not relevant, returning empty results")
                    # Return empty results if no relevant sections found
                    yield ToolResponse(
                        id=SEARCH_RESPONSE_SUMMARY_ID,
                        response=SearchResponseSummary(
                            rephrased_query=query,
                            top_sections=[],
                            predicted_flow=search_pipeline.predicted_flow,
                            predicted_search=search_pipeline.predicted_search_type,
                            final_filters=search_pipeline.search_query.filters,
                            recency_bias_multiplier=search_pipeline.search_query.recency_bias_multiplier,
                        ),
                    )
                    yield ToolResponse(id=SEARCH_DOC_CONTENT_ID, response=OnyxContexts(contexts=[]))
                    yield ToolResponse(id=SECTION_RELEVANCE_LIST_ID, response=[])
                    yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=[])
                    return
                else:
                    logger.info(f"Relevant details found across all datasources: {len(search_pipeline.final_context_sections)} sections")
            else:
                # LLM relevance filtering is disabled, so all sections are considered relevant
                logger.info(f"LLM relevance filtering disabled, using all datasources results: {len(search_pipeline.final_context_sections)} sections")

        yield ToolResponse(
            id=SEARCH_RESPONSE_SUMMARY_ID,
            response=SearchResponseSummary(
                rephrased_query=query,
                top_sections=search_pipeline.final_context_sections,
                predicted_flow=search_pipeline.predicted_flow,
                predicted_search=search_pipeline.predicted_search_type,
                final_filters=search_pipeline.search_query.filters,
                recency_bias_multiplier=search_pipeline.search_query.recency_bias_multiplier,
            ),
        )

        yield ToolResponse(
            id=SEARCH_DOC_CONTENT_ID,
            response=OnyxContexts(
                contexts=[
                    OnyxContext(
                        content=section.combined_content,
                        document_id=section.center_chunk.document_id,
                        semantic_identifier=section.center_chunk.semantic_identifier,
                        blurb=section.center_chunk.blurb,
                    )
                    for section in search_pipeline.reranked_sections
                ]
            ),
        )

        # When LLM relevance filtering is disabled, section_relevance is None
        # We need to create a list of all True values to indicate all sections are relevant
        section_relevance_response = search_pipeline.section_relevance
        if section_relevance_response is None:
            # LLM relevance filtering is disabled, so all sections are considered relevant
            # Use reranked_sections to match the citations which are based on reranked_sections
            section_relevance_response = [
                SectionRelevancePiece(
                    relevant=True,
                    document_id=section.center_chunk.document_id,
                    chunk_id=section.center_chunk.chunk_id,
                )
                for section in search_pipeline.reranked_sections
            ]
        
        yield ToolResponse(
            id=SECTION_RELEVANCE_LIST_ID,
            response=section_relevance_response,
        )

        # Diagnostic logging for context flow
        # logger.info(f"Pre-pruning sections count: {len(search_pipeline.final_context_sections) if search_pipeline.final_context_sections else 0}")
        # logger.info(f"Section relevance count: {len(search_pipeline.section_relevance_list) if search_pipeline.section_relevance_list else 0}")
        # if search_pipeline.section_relevance_list:
        #     relevant_count = sum(1 for rel in search_pipeline.section_relevance_list if rel)
        #     logger.info(f"Relevant sections count: {relevant_count}")

        pruned_sections = prune_sections(
            sections=search_pipeline.final_context_sections,
            section_relevance_list=search_pipeline.section_relevance_list,
            prompt_config=self.prompt_config,
            llm_config=self.llm.config,
            question=query,
            contextual_pruning_config=self.contextual_pruning_config,
        )

        llm_docs = [
            llm_doc_from_inference_section(section) for section in pruned_sections
        ]

        # logger.info(f"Final LLM docs count: {len(llm_docs)}")
        # if llm_docs:
        #     logger.info(f"Sample LLM doc semantic identifiers: {[doc.semantic_identifier for doc in llm_docs[:3]]}")
        # else:
        #     logger.warning("No LLM docs available for final context - this will result in no context being provided to the LLM")

        yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=llm_docs)

    def final_result(self, *args: ToolResponse) -> JSON_ro:
        final_docs = cast(
            list[LlmDoc],
            next(arg.response for arg in args if arg.id == FINAL_CONTEXT_DOCUMENTS_ID),
        )
        # NOTE: need to do this json.loads(doc.json()) stuff because there are some
        # subfields that are not serializable by default (datetime)
        # this forces pydantic to make them JSON serializable for us
        return [json.loads(doc.model_dump_json()) for doc in final_docs]

    def build_next_prompt(
        self,
        prompt_builder: AnswerPromptBuilder,
        tool_call_summary: ToolCallSummary,
        tool_responses: list[ToolResponse],
        using_tool_calling_llm: bool,
    ) -> AnswerPromptBuilder:
        return build_next_prompt_for_search_like_tool(
            prompt_builder=prompt_builder,
            tool_call_summary=tool_call_summary,
            tool_responses=tool_responses,
            using_tool_calling_llm=using_tool_calling_llm,
            answer_style_config=self.answer_style_config,
            prompt_config=self.prompt_config,
        )

    """Other utility functions"""

    @classmethod
    def get_search_result(
        cls, llm_call: LLMCall
    ) -> tuple[list[LlmDoc], list[LlmDoc]] | None:
        """
        Returns the final search results and a map of docs to their original search rank (which is what is displayed to user)
        """
        if not llm_call.tool_call_info:
            return None

        final_search_results = []
        initial_search_results = []

        for yield_item in llm_call.tool_call_info:
            if (
                isinstance(yield_item, ToolResponse)
                and yield_item.id == FINAL_CONTEXT_DOCUMENTS_ID
            ):
                final_search_results = cast(list[LlmDoc], yield_item.response)
            elif (
                isinstance(yield_item, ToolResponse)
                and yield_item.id == ORIGINAL_CONTEXT_DOCUMENTS_ID
            ):
                search_contexts = yield_item.response.contexts
                # original_doc_search_rank = 1
                for doc in search_contexts:
                    if doc.document_id not in initial_search_results:
                        initial_search_results.append(doc)

                initial_search_results = cast(list[LlmDoc], initial_search_results)

        return final_search_results, initial_search_results

import copy
import json
from collections.abc import Callable
from collections.abc import Generator
from typing import Any
from typing import cast
from typing import TypeVar

from sqlalchemy.orm import Session

from onyx.chat.chat_utils import llm_doc_from_inference_section
from onyx.chat.models import AnswerStyleConfig
from onyx.chat.models import ContextualPruningConfig
from onyx.chat.models import DocumentPruningConfig
from onyx.chat.models import LlmDoc
from onyx.chat.models import PromptConfig
from onyx.chat.models import SectionRelevancePiece
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.chat.prompt_builder.citations_prompt import compute_max_llm_input_tokens
from onyx.chat.prune_and_merge import prune_and_merge_sections
from onyx.chat.prune_and_merge import prune_sections
from onyx.configs.chat_configs import CONTEXT_CHUNKS_ABOVE
from onyx.configs.chat_configs import CONTEXT_CHUNKS_BELOW
from onyx.configs.model_configs import GEN_AI_MODEL_FALLBACK_MAX_TOKENS
from onyx.context.search.enums import LLMEvaluationType
from onyx.context.search.enums import QueryFlow
from onyx.context.search.models import BaseFilters
from onyx.context.search.models import IndexFilters
from onyx.context.search.models import InferenceSection
from onyx.context.search.models import RerankingDetails
from onyx.context.search.models import RetrievalDetails
from onyx.context.search.models import SearchRequest
from onyx.context.search.models import UserFileFilters
from onyx.context.search.pipeline import SearchPipeline
from onyx.context.search.pipeline import section_relevance_list_impl
from onyx.db.models import Persona
from onyx.db.models import User
from onyx.llm.interfaces import LLM
from onyx.llm.models import PreviousMessage
from onyx.secondary_llm_flows.choose_search import check_if_need_search
from onyx.secondary_llm_flows.query_expansion import history_based_query_rephrase
from onyx.tools.message import ToolCallSummary
from onyx.tools.models import SearchQueryInfo
from onyx.tools.models import SearchToolOverrideKwargs
from onyx.tools.models import ToolResponse
from onyx.tools.tool import Tool
from onyx.tools.tool_implementations.search.search_utils import llm_doc_to_dict
from onyx.tools.tool_implementations.search_like_tool_utils import (
    build_next_prompt_for_search_like_tool,
)
from onyx.tools.tool_implementations.search_like_tool_utils import (
    FINAL_CONTEXT_DOCUMENTS_ID,
)
from onyx.utils.logger import setup_logger
from onyx.utils.special_types import JSON_ro

logger = setup_logger()

SEARCH_RESPONSE_SUMMARY_ID = "search_response_summary"
SECTION_RELEVANCE_LIST_ID = "section_relevance_list"
SEARCH_EVALUATION_ID = "llm_doc_eval"
QUERY_FIELD = "query"


class SearchResponseSummary(SearchQueryInfo):
    top_sections: list[InferenceSection]
    rephrased_query: str | None = None
    predicted_flow: QueryFlow | None


SEARCH_TOOL_DESCRIPTION = """
Runs a semantic search over the user's knowledge base. The default behavior is to use this tool. \
The only scenario where you should not use this tool is if:

- There is sufficient information in chat history to FULLY and ACCURATELY answer the query AND \
additional information or details would provide little or no value.
- The query is some form of request that does not require additional information to handle.

HINT: if you are unfamiliar with the user input OR think the user input is a typo, use this tool.
"""


class SearchTool(Tool[SearchToolOverrideKwargs]):
    _NAME = "run_search"
    _DISPLAY_NAME = "Search Tool"
    _DESCRIPTION = SEARCH_TOOL_DESCRIPTION

    def __init__(
        self,
        tool_id: int,
        db_session: Session,
        user: User | None,
        persona: Persona,
        retrieval_options: RetrievalDetails | None,
        prompt_config: PromptConfig,
        llm: LLM,
        fast_llm: LLM,
        document_pruning_config: DocumentPruningConfig,
        answer_style_config: AnswerStyleConfig,
        evaluation_type: LLMEvaluationType,
        # if specified, will not actually run a search and will instead return these
        # sections. Used when the user selects specific docs to talk to
        selected_sections: list[InferenceSection] | None = None,
        chunks_above: int | None = None,
        chunks_below: int | None = None,
        full_doc: bool = False,
        bypass_acl: bool = False,
        rerank_settings: RerankingDetails | None = None,
    ) -> None:
        self.user = user
        self.persona = persona
        self.retrieval_options = retrieval_options
        self.prompt_config = prompt_config
        self.llm = llm
        self.fast_llm = fast_llm
        self.evaluation_type = evaluation_type

        self.selected_sections = selected_sections

        self.full_doc = full_doc
        self.bypass_acl = bypass_acl
        self.db_session = db_session

        # Only used via API
        self.rerank_settings = rerank_settings

        self.chunks_above = (
            chunks_above
            if chunks_above is not None
            else (
                persona.chunks_above
                if persona.chunks_above is not None
                else CONTEXT_CHUNKS_ABOVE
            )
        )
        self.chunks_below = (
            chunks_below
            if chunks_below is not None
            else (
                persona.chunks_below
                if persona.chunks_below is not None
                else CONTEXT_CHUNKS_BELOW
            )
        )

        # For small context models, don't include additional surrounding context
        # The 3 here for at least minimum 1 above, 1 below and 1 for the middle chunk

        max_input_tokens = compute_max_llm_input_tokens(
            llm_config=llm.config,
        )
        if max_input_tokens < 3 * GEN_AI_MODEL_FALLBACK_MAX_TOKENS:
            self.chunks_above = 0
            self.chunks_below = 0

        num_chunk_multiple = self.chunks_above + self.chunks_below + 1

        self.answer_style_config = answer_style_config
        self.contextual_pruning_config = (
            ContextualPruningConfig.from_doc_pruning_config(
                num_chunk_multiple=num_chunk_multiple,
                doc_pruning_config=document_pruning_config,
            )
        )

        self._id = tool_id

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def description(self) -> str:
        return self._DESCRIPTION

    @property
    def display_name(self) -> str:
        return self._DISPLAY_NAME

    """For explicit tool calling"""

    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        QUERY_FIELD: {
                            "type": "string",
                            "description": "What to search for",
                        },
                    },
                    "required": [QUERY_FIELD],
                },
            },
        }

    def build_tool_message_content(
        self, *args: ToolResponse
    ) -> str | list[str | dict[str, Any]]:
        final_context_docs_response = next(
            response for response in args if response.id == FINAL_CONTEXT_DOCUMENTS_ID
        )
        final_context_docs = cast(list[LlmDoc], final_context_docs_response.response)

        return json.dumps(
            {
                "search_results": [
                    llm_doc_to_dict(doc, ind)
                    for ind, doc in enumerate(final_context_docs)
                ]
            }
        )

    """For LLMs that don't support tool calling"""

    def get_args_for_non_tool_calling_llm(
        self,
        query: str,
        history: list[PreviousMessage],
        llm: LLM,
        force_run: bool = False,
    ) -> dict[str, Any] | None:
        if not force_run and not check_if_need_search(
            query=query, history=history, llm=llm
        ):
            return None

        rephrased_query = history_based_query_rephrase(
            query=query, history=history, llm=llm
        )
        return {QUERY_FIELD: rephrased_query}

    """Actual tool execution"""

    def _build_response_for_specified_sections(
        self, query: str
    ) -> Generator[ToolResponse, None, None]:
        if self.selected_sections is None:
            raise ValueError("Sections must be specified")

        yield ToolResponse(
            id=SEARCH_RESPONSE_SUMMARY_ID,
            response=SearchResponseSummary(
                rephrased_query=None,
                top_sections=[],
                predicted_flow=None,
                predicted_search=None,
                final_filters=IndexFilters(access_control_list=None),  # dummy filters
                recency_bias_multiplier=1.0,
            ),
        )

        # Build selected sections for specified documents
        selected_sections = [
            SectionRelevancePiece(
                relevant=True,
                document_id=section.center_chunk.document_id,
                chunk_id=section.center_chunk.chunk_id,
            )
            for section in self.selected_sections
        ]

        yield ToolResponse(
            id=SECTION_RELEVANCE_LIST_ID,
            response=selected_sections,
        )

        final_context_sections = prune_and_merge_sections(
            sections=self.selected_sections,
            section_relevance_list=None,
            prompt_config=self.prompt_config,
            llm_config=self.llm.config,
            question=query,
            contextual_pruning_config=self.contextual_pruning_config,
        )

        llm_docs = [
            llm_doc_from_inference_section(section)
            for section in final_context_sections
        ]

        yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=llm_docs)

    def run(
        self, override_kwargs: SearchToolOverrideKwargs | None = None, **llm_kwargs: Any
    ) -> Generator[ToolResponse, None, None]:
        query = cast(str, llm_kwargs[QUERY_FIELD])
        original_query = None
        precomputed_query_embedding = None
        precomputed_is_keyword = None
        precomputed_keywords = None
        force_no_rerank = False
        alternate_db_session = None
        retrieved_sections_callback = None
        skip_query_analysis = False
        user_file_ids = None
        user_folder_ids = None
        document_sources = None
        time_cutoff = None
        expanded_queries = None
        kg_entities = None
        kg_relationships = None
        kg_terms = None
        kg_sources = None
        kg_chunk_id_zero_only = False
        if override_kwargs:
            original_query = override_kwargs.original_query
            precomputed_is_keyword = override_kwargs.precomputed_is_keyword
            precomputed_keywords = override_kwargs.precomputed_keywords
            precomputed_query_embedding = override_kwargs.precomputed_query_embedding
            force_no_rerank = use_alt_not_None(override_kwargs.force_no_rerank, False)
            alternate_db_session = override_kwargs.alternate_db_session
            retrieved_sections_callback = override_kwargs.retrieved_sections_callback
            skip_query_analysis = use_alt_not_None(
                override_kwargs.skip_query_analysis, False
            )
            user_file_ids = override_kwargs.user_file_ids
            user_folder_ids = override_kwargs.user_folder_ids
            document_sources = override_kwargs.document_sources
            time_cutoff = override_kwargs.time_cutoff
            expanded_queries = override_kwargs.expanded_queries
            kg_entities = override_kwargs.kg_entities
            kg_relationships = override_kwargs.kg_relationships
            kg_terms = override_kwargs.kg_terms
            kg_sources = override_kwargs.kg_sources
            kg_chunk_id_zero_only = override_kwargs.kg_chunk_id_zero_only or False

        if self.selected_sections:
            yield from self._build_response_for_specified_sections(query)
            return

        retrieval_options = copy.deepcopy(self.retrieval_options) or RetrievalDetails()
        if document_sources or time_cutoff:
            # if empty, just start with an empty filters object
            if not retrieval_options.filters:
                retrieval_options.filters = BaseFilters()

            # Handle document sources
            if document_sources:
                source_types = retrieval_options.filters.source_type or []
                retrieval_options.filters.source_type = list(
                    set(source_types + document_sources)
                )

            # Handle time cutoff
            if time_cutoff:
                # Overwrite time-cutoff should supercede existing time-cutoff, even if defined
                retrieval_options.filters.time_cutoff = time_cutoff

        retrieval_options = copy.deepcopy(retrieval_options) or RetrievalDetails()
        retrieval_options.filters = retrieval_options.filters or BaseFilters()
        if kg_entities:
            retrieval_options.filters.kg_entities = kg_entities
        if kg_relationships:
            retrieval_options.filters.kg_relationships = kg_relationships
        if kg_terms:
            retrieval_options.filters.kg_terms = kg_terms
        if kg_sources:
            retrieval_options.filters.kg_sources = kg_sources
        if kg_chunk_id_zero_only:
            retrieval_options.filters.kg_chunk_id_zero_only = kg_chunk_id_zero_only

        search_pipeline = SearchPipeline(
            search_request=SearchRequest(
                query=query,
                evaluation_type=(
                    LLMEvaluationType.SKIP if force_no_rerank else self.evaluation_type
                ),
                human_selected_filters=(
                    retrieval_options.filters if retrieval_options else None
                ),
                user_file_filters=UserFileFilters(
                    user_file_ids=user_file_ids, user_folder_ids=user_folder_ids
                ),
                persona=self.persona,
                offset=(retrieval_options.offset if retrieval_options else None),
                limit=retrieval_options.limit if retrieval_options else None,
                rerank_settings=(
                    RerankingDetails(
                        rerank_model_name=None,
                        rerank_api_url=None,
                        rerank_provider_type=None,
                        rerank_api_key=None,
                        num_rerank=0,
                        disable_rerank_for_streaming=True,
                    )
                    if force_no_rerank
                    else self.rerank_settings
                ),
                chunks_above=self.chunks_above,
                chunks_below=self.chunks_below,
                full_doc=self.full_doc,
                enable_auto_detect_filters=(
                    retrieval_options.enable_auto_detect_filters
                    if retrieval_options
                    else None
                ),
                precomputed_query_embedding=precomputed_query_embedding,
                precomputed_is_keyword=precomputed_is_keyword,
                precomputed_keywords=precomputed_keywords,
                # add expanded queries
                expanded_queries=expanded_queries,
                original_query=original_query,
            ),
            user=self.user,
            llm=self.llm,
            fast_llm=self.fast_llm,
            skip_query_analysis=skip_query_analysis,
            bypass_acl=self.bypass_acl,
            db_session=alternate_db_session or self.db_session,
            prompt_config=self.prompt_config,
            retrieved_sections_callback=retrieved_sections_callback,
            contextual_pruning_config=self.contextual_pruning_config,
        )

        search_query_info = SearchQueryInfo(
            predicted_search=search_pipeline.search_query.search_type,
            final_filters=search_pipeline.search_query.filters,
            recency_bias_multiplier=search_pipeline.search_query.recency_bias_multiplier,
        )
        yield from yield_search_responses(
            query=query,
            # give back the merged sections to prevent duplicate docs from appearing in the UI
            get_retrieved_sections=lambda: search_pipeline.merged_retrieved_sections,
            get_final_context_sections=lambda: search_pipeline.final_context_sections,
            search_query_info=search_query_info,
            get_section_relevance=lambda: search_pipeline.section_relevance,
            search_tool=self,
        )

    def final_result(self, *args: ToolResponse) -> JSON_ro:
        final_docs = cast(
            list[LlmDoc],
            next(arg.response for arg in args if arg.id == FINAL_CONTEXT_DOCUMENTS_ID),
        )
        # NOTE: need to do this json.loads(doc.json()) stuff because there are some
        # subfields that are not serializable by default (datetime)
        # this forces pydantic to make them JSON serializable for us
        return [json.loads(doc.model_dump_json()) for doc in final_docs]

    def build_next_prompt(
        self,
        prompt_builder: AnswerPromptBuilder,
        tool_call_summary: ToolCallSummary,
        tool_responses: list[ToolResponse],
        using_tool_calling_llm: bool,
    ) -> AnswerPromptBuilder:
        return build_next_prompt_for_search_like_tool(
            prompt_builder=prompt_builder,
            tool_call_summary=tool_call_summary,
            tool_responses=tool_responses,
            using_tool_calling_llm=using_tool_calling_llm,
            answer_style_config=self.answer_style_config,
            prompt_config=self.prompt_config,
        )


# Allows yielding the same responses as a SearchTool without being a SearchTool.
# SearchTool passed in to allow for access to SearchTool properties.
# We can't just call SearchTool methods in the graph because we're operating on
# the retrieved docs (reranking, deduping, etc.) after the SearchTool has run.
#
# The various inference sections are passed in as functions to allow for lazy
# evaluation. The SearchPipeline object properties that they correspond to are
# actually functions defined with @property decorators, and passing them into
# this function causes them to get evaluated immediately which is undesirable.
def yield_search_responses(
    query: str,
    get_retrieved_sections: Callable[[], list[InferenceSection]],
    get_final_context_sections: Callable[[], list[InferenceSection]],
    search_query_info: SearchQueryInfo,
    get_section_relevance: Callable[[], list[SectionRelevancePiece] | None],
    search_tool: SearchTool,
) -> Generator[ToolResponse, None, None]:
    yield ToolResponse(
        id=SEARCH_RESPONSE_SUMMARY_ID,
        response=SearchResponseSummary(
            rephrased_query=query,
            top_sections=get_retrieved_sections(),
            predicted_flow=QueryFlow.QUESTION_ANSWER,
            predicted_search=search_query_info.predicted_search,
            final_filters=search_query_info.final_filters,
            recency_bias_multiplier=search_query_info.recency_bias_multiplier,
        ),
    )

    section_relevance = get_section_relevance()
    yield ToolResponse(
        id=SECTION_RELEVANCE_LIST_ID,
        response=section_relevance,
    )

    final_context_sections = get_final_context_sections()

    # Use the section_relevance we already computed above
    pruned_sections = prune_sections(
        sections=final_context_sections,
        section_relevance_list=section_relevance_list_impl(
            section_relevance, final_context_sections
        ),
        prompt_config=search_tool.prompt_config,
        llm_config=search_tool.llm.config,
        question=query,
        contextual_pruning_config=search_tool.contextual_pruning_config,
    )
    llm_docs = [llm_doc_from_inference_section(section) for section in pruned_sections]

    yield ToolResponse(id=FINAL_CONTEXT_DOCUMENTS_ID, response=llm_docs)


T = TypeVar("T")


def use_alt_not_None(value: T | None, alt: T) -> T:
    return value if value is not None else alt
