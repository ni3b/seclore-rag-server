from typing import cast

from langchain_core.messages import HumanMessage

from onyx.chat.models import AnswerStyleConfig
from onyx.chat.models import LlmDoc
from onyx.chat.models import PromptConfig
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.chat.prompt_builder.citations_prompt import (
    build_citations_system_message,
)
from onyx.chat.prompt_builder.citations_prompt import build_citations_user_message
from onyx.llm.utils import build_content_with_imgs
from onyx.tools.message import ToolCallSummary
from onyx.tools.models import ToolResponse
from onyx.utils.logger import setup_logger
from onyx.configs.chat_configs import PREVENT_LLM_HALLUCINATION_ON_EMPTY_SEARCH

logger = setup_logger()


ORIGINAL_CONTEXT_DOCUMENTS_ID = "search_doc_content"
FINAL_CONTEXT_DOCUMENTS_ID = "final_context_documents"


def _create_no_results_prompt_config(
    base_prompt_config: PromptConfig,
    user_query: str
) -> PromptConfig:
    """
    Create a modified prompt config that informs the LLM that no relevant documents were found.
    This allows the LLM to generate an appropriate response with this context.
    """
    no_results_system_addition = f"""

IMPORTANT: No relevant documents were found in the knowledge base for the user's query: "{user_query}". 
You should acknowledge this and respond appropriately. You may:
- Inform the user that no relevant information was found in the available documents
- Suggest rephrasing the question or trying different keywords  
- Ask clarifying questions to better understand what they're looking for
- Provide general guidance if appropriate to the context

Be helpful and conversational while being honest about the lack of specific information in the knowledge base."""

    modified_system_prompt = base_prompt_config.system_prompt + no_results_system_addition
    
    # Create a new PromptConfig with the modified system prompt
    return PromptConfig(
        system_prompt=modified_system_prompt,
        search_tool_description=base_prompt_config.search_tool_description,
        history_query_rephrase=base_prompt_config.history_query_rephrase,
        custom_tool_argument_system_prompt=base_prompt_config.custom_tool_argument_system_prompt,
        search_query_prompt=base_prompt_config.search_query_prompt,
        search_data_source_selector_prompt=base_prompt_config.search_data_source_selector_prompt,
        task_prompt=base_prompt_config.task_prompt,
        datetime_aware=base_prompt_config.datetime_aware,
        include_citations=base_prompt_config.include_citations,
    )


def build_next_prompt_for_search_like_tool(
    prompt_builder: AnswerPromptBuilder,
    tool_call_summary: ToolCallSummary,
    tool_responses: list[ToolResponse],
    using_tool_calling_llm: bool,
    answer_style_config: AnswerStyleConfig,
    prompt_config: PromptConfig,
) -> AnswerPromptBuilder:
    if not using_tool_calling_llm:
        try:
            final_context_docs_response = next(
                response
                for response in tool_responses
                if response.id == FINAL_CONTEXT_DOCUMENTS_ID
            )
            final_context_documents = cast(
                list[LlmDoc], final_context_docs_response.response
            )
            logger.info(f"Found {len(final_context_documents)} final context documents for citations")
            for doc in final_context_documents:
                logger.info(f"Context doc: {doc.document_id} - {doc.semantic_identifier}")
        except StopIteration:
            # If no FINAL_CONTEXT_DOCUMENTS_ID response exists, use empty list
            logger.warning(f"No {FINAL_CONTEXT_DOCUMENTS_ID} response found in tool_responses. Using empty context documents.")
            final_context_documents = []
        
        # If no relevant documents found and the feature is enabled, modify the prompt
        if not final_context_documents and PREVENT_LLM_HALLUCINATION_ON_EMPTY_SEARCH:
            prompt_config = _create_no_results_prompt_config(
                base_prompt_config=prompt_config,
                user_query=prompt_builder.raw_user_query
            )
    else:
        # if using tool calling llm, then the final context documents are the tool responses
        final_context_documents = []
        logger.info("Using tool calling LLM - final context documents will be handled differently")

    prompt_builder.update_system_prompt(build_citations_system_message(prompt_config))
    prompt_builder.update_user_prompt(
        build_citations_user_message(
            # make sure to use the original user query here in order to avoid duplication
            # of the task prompt
            message=HumanMessage(
                content=build_content_with_imgs(
                    prompt_builder.raw_user_query,
                    prompt_builder.raw_user_uploaded_files,
                )
            ),
            prompt_config=prompt_config,
            context_docs=final_context_documents,
            all_doc_useful=(
                answer_style_config.citation_config.all_docs_useful
                if answer_style_config.citation_config
                else False
            ),
            history_message=prompt_builder.single_message_history or "",
        )
    )

    if using_tool_calling_llm:
        prompt_builder.append_message(tool_call_summary.tool_call_request)
        prompt_builder.append_message(tool_call_summary.tool_call_result)

    return prompt_builder

from typing import cast

from onyx.chat.models import AnswerStyleConfig
from onyx.chat.models import LlmDoc
from onyx.chat.models import PromptConfig
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.chat.prompt_builder.citations_prompt import (
    build_citations_system_message,
)
from onyx.chat.prompt_builder.citations_prompt import build_citations_user_message
from onyx.connectors.models import Document
from onyx.connectors.models import IndexingDocument
from onyx.connectors.models import Section
from onyx.tools.message import ToolCallSummary
from onyx.tools.models import ToolResponse


FINAL_CONTEXT_DOCUMENTS_ID = "final_context_documents"


def build_next_prompt_for_search_like_tool(
    prompt_builder: AnswerPromptBuilder,
    tool_call_summary: ToolCallSummary,
    tool_responses: list[ToolResponse],
    using_tool_calling_llm: bool,
    answer_style_config: AnswerStyleConfig,
    prompt_config: PromptConfig,
    context_type: str = "context documents",
) -> AnswerPromptBuilder:
    if not using_tool_calling_llm:
        final_context_docs_response = next(
            response
            for response in tool_responses
            if response.id == FINAL_CONTEXT_DOCUMENTS_ID
        )
        final_context_documents = cast(
            list[LlmDoc], final_context_docs_response.response
        )
    else:
        # if using tool calling llm, then the final context documents are the tool responses
        final_context_documents = []

    prompt_builder.update_system_prompt(build_citations_system_message(prompt_config))
    prompt_builder.update_user_prompt(
        build_citations_user_message(
            # make sure to use the original user query here in order to avoid duplication
            # of the task prompt
            user_query=prompt_builder.raw_user_query,
            files=prompt_builder.raw_user_uploaded_files,
            prompt_config=prompt_config,
            context_docs=final_context_documents,
            all_doc_useful=(
                answer_style_config.citation_config.all_docs_useful
                if answer_style_config.citation_config
                else False
            ),
            history_message=prompt_builder.single_message_history or "",
            context_type=context_type,
        )
    )

    if using_tool_calling_llm:
        prompt_builder.append_message(tool_call_summary.tool_call_request)
        prompt_builder.append_message(tool_call_summary.tool_call_result)

    return prompt_builder


def documents_to_indexing_documents(
    documents: list[Document],
) -> list[IndexingDocument]:
    indexing_documents = []

    for document in documents:
        processed_sections = []
        for section in document.sections:
            processed_section = Section(
                text=section.text or "",
                link=section.link,
                image_file_id=None,
            )
            processed_sections.append(processed_section)

        indexed_document = IndexingDocument(
            **document.model_dump(), processed_sections=processed_sections
        )
        indexing_documents.append(indexed_document)
    return indexing_documents
