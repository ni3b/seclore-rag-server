import csv
import json
import uuid
from collections.abc import Generator
from io import BytesIO
from io import StringIO
from typing import Any
from typing import cast
from typing import Dict
from typing import List

import requests
from onyx.chat.models import PromptConfig
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from pydantic import BaseModel
from requests import JSONDecodeError
from litellm.exceptions import ContextWindowExceededError

from onyx.chat.models import PromptConfig
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.configs.constants import FileOrigin
from onyx.db.engine import get_session_with_default_tenant
from onyx.file_store.file_store import get_default_file_store
from onyx.file_store.models import ChatFileType
from onyx.file_store.models import InMemoryChatFile
from onyx.llm.interfaces import LLM
from onyx.llm.models import PreviousMessage
from onyx.tools.base_tool import BaseTool
from onyx.tools.message import ToolCallSummary
from onyx.tools.models import CHAT_SESSION_ID_PLACEHOLDER
from onyx.tools.models import DynamicSchemaInfo
from onyx.tools.models import MESSAGE_ID_PLACEHOLDER
from onyx.tools.models import ToolResponse
from onyx.tools.tool_implementations.custom.custom_tool_prompts import (
    SHOULD_USE_CUSTOM_TOOL_SYSTEM_PROMPT,
)
from onyx.tools.tool_implementations.custom.custom_tool_prompts import (
    SHOULD_USE_CUSTOM_TOOL_USER_PROMPT,
)
from onyx.tools.tool_implementations.custom.custom_tool_prompts import (
    TOOL_ARG_SYSTEM_PROMPT,
)
from onyx.tools.tool_implementations.custom.custom_tool_prompts import (
    TOOL_ARG_USER_PROMPT,
)
from onyx.tools.tool_implementations.custom.custom_tool_prompts import USE_TOOL
from onyx.tools.tool_implementations.custom.openapi_parsing import MethodSpec
from onyx.tools.tool_implementations.custom.openapi_parsing import (
    openapi_to_method_specs,
)
from onyx.tools.tool_implementations.custom.openapi_parsing import openapi_to_url
from onyx.utils.headers import header_list_to_header_dict
from onyx.utils.headers import HeaderItemDict
from onyx.utils.logger import setup_logger
from onyx.utils.special_types import JSON_ro
from onyx.configs.constants import DocumentSource
from onyx.utils.freshdesk_utils import FreshdeskUtils
from onyx.chat.models import LlmDoc
from onyx.chat.models import AnswerStyleConfig, PromptConfig, CitationConfig
from onyx.chat.prompt_builder.answer_prompt_builder import LLMCall
from onyx.tools.tool_implementations.search_like_tool_utils import (
    ORIGINAL_CONTEXT_DOCUMENTS_ID,
)
from onyx.tools.tool_implementations.search_like_tool_utils import (
    FINAL_CONTEXT_DOCUMENTS_ID,
)
from onyx.tools.tool_implementations.search_like_tool_utils import (
                build_next_prompt_for_search_like_tool,
            )
from datetime import datetime, timedelta
from onyx.prompts.prompt_utils import handle_onyx_date_awareness
from onyx.configs.chat_configs import FRESHDESK_API_DOMAIN, FRESHDESK_API_KEY, FRESHDESK_API_PASSWORD

logger = setup_logger()

CUSTOM_TOOL_RESPONSE_ID = "custom_tool_response"
REQUEST_BODY = "request_body"


class CustomToolFileResponse(BaseModel):
    file_ids: List[str]  # References to saved images or CSVs


class CustomToolCallSummary(BaseModel):
    tool_name: str
    response_type: str  # e.g., 'json', 'image', 'csv', 'graph'
    tool_result: Any  # The response data


class CustomTool(BaseTool):
    def __init__(
        self,
        method_spec: MethodSpec,
        base_url: str,
        custom_headers: list[HeaderItemDict] | None = None,
        user_oauth_token: str | None = None,
        answer_style_config: AnswerStyleConfig | None = None,
        prompt_config: PromptConfig | None = None,
    ) -> None:
        self._base_url = base_url
        self._method_spec = method_spec
        self._tool_definition = self._method_spec.to_tool_definition()
        self._user_oauth_token = user_oauth_token

        self._name = self._method_spec.name
        self._description = self._method_spec.summary
        self.headers = (
            header_list_to_header_dict(custom_headers) if custom_headers else {}
        )
        self.answer_style_config = answer_style_config
        self.prompt_config = prompt_config

        # Check for both Authorization header and OAuth token
        has_auth_header = any(
            key.lower() == "authorization" for key in self.headers.keys()
        )
        if has_auth_header and self._user_oauth_token:
            logger.warning(
                f"Tool '{self._name}' has both an Authorization "
                "header and OAuth token set. This is likely a configuration "
                "error as the OAuth token will override the custom header."
            )

        if self._user_oauth_token:
            self.headers["Authorization"] = f"Bearer {self._user_oauth_token}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def display_name(self) -> str:
        return self._name

    """For LLMs which support explicit tool calling"""

    def tool_definition(self) -> dict:
        logger.info(f"tool_definition description: {self._tool_definition}")
        return self._tool_definition

    def build_tool_message_content(
        self, *args: ToolResponse
    ) -> str | list[str | dict[str, Any]]:
        response = cast(CustomToolCallSummary, args[0].response)

        if response.response_type == "image" or response.response_type == "csv":
            image_response = cast(CustomToolFileResponse, response.tool_result)
            return json.dumps({"file_ids": image_response.file_ids})

        # For JSON or other responses, return as-is
        return json.dumps(response.tool_result)

    def _truncate_history_for_tool_prompt(self, history: list[PreviousMessage]) -> str:
        """Truncate conversation history to prevent context window exceeded errors.
        
        This is a simplified version that limits the number of messages rather than tokens
        to avoid circular imports with chat_utils.
        """
        if not history:
            return ""
        
        # Use a conservative limit for custom tool prompts
        # Limit to last 10 messages to prevent context window issues
        max_messages = 10
        limited_history = history[-max_messages:] if len(history) > max_messages else history
        
        # Convert to simple string format
        history_str = ""
        for message in limited_history:
            role = message.message_type.value.upper()
            history_str += f"{role}:\n{message.message}\n\n"
        
        return history_str.strip()

    """For LLMs which do NOT support explicit tool calling"""

    def get_args_for_non_tool_calling_llm(
        self,
        query: str,
        history: list[PreviousMessage],
        llm: LLM,
        prompt_config: PromptConfig,
        force_run: bool = False,
    ) -> dict[str, Any] | None:
        logger.debug(f"in custom tool class for query {query}")
        
        # Truncate history to prevent context window exceeded errors
        truncated_history = self._truncate_history_for_tool_prompt(history)
        
        logger.debug(f"Original history length: {len(history)}, Truncated history length: {len(truncated_history)}")
        
        if not force_run:
            try:
                should_use_result = llm.invoke(
                    [
                        SystemMessage(content=SHOULD_USE_CUSTOM_TOOL_SYSTEM_PROMPT),
                        HumanMessage(
                            content=SHOULD_USE_CUSTOM_TOOL_USER_PROMPT.format(
                                history=truncated_history,
                                query=query,
                                tool_name=self.name,
                                tool_description=self.description,
                            )
                        ),
                    ]
                )
                if cast(str, should_use_result.content).strip() != USE_TOOL:
                    return None
            except ContextWindowExceededError as e:
                logger.warning(f"Context window exceeded while determining tool usage: {e}")
                # If context window is exceeded, assume we should use the tool
                pass
            except Exception as e:
                logger.warning(f"Failed to determine if custom tool should be used: {e}")
                # If we can't determine, assume we should use the tool
                pass

        content = ""
        custom_tool_system_prompt = getattr(prompt_config, 'custom_tool_argument_system_prompt', None) or TOOL_ARG_SYSTEM_PROMPT
        custom_tool_system_prompt = handle_onyx_date_awareness(custom_tool_system_prompt, prompt_config, True)
        logger.info(f"custom_tool_system_prompt: {custom_tool_system_prompt}")
        try:
            args_result = llm.invoke(   
                [
                    SystemMessage(content=custom_tool_system_prompt),
                    HumanMessage(
                        content=TOOL_ARG_USER_PROMPT.format(
                            history=truncated_history,
                            query=query,
                            tool_name=self.name,
                            tool_description=self.description,
                            tool_args=self.tool_definition()["function"]["parameters"],
                        )
                    ),
                ]
            )
            logger.info(f"argument result in custom tool: {args_result}")
            args_result_str = cast(str, args_result.content)
        except ContextWindowExceededError as e:
            logger.error(f"Context window exceeded for custom tool '{self.name}': {e}")
            # Return a basic response if context window is exceeded
            return {"query": query}
        except Exception as e:
            logger.error(f"Failed to get arguments for custom tool '{self.name}': {e}")
            # Return a basic response if we can't get arguments
            return {"query": query}
        
        try:
            return json.loads(args_result_str.strip())
        except json.JSONDecodeError:
            pass

        # try removing ```
        try:
            return json.loads(args_result_str.strip("```"))
        except json.JSONDecodeError:
            pass

        # try removing ```json
        try:
            return json.loads(args_result_str.strip("```").strip("json"))
        except json.JSONDecodeError:
            pass

        # pretend like nothing happened if not parse-able
        logger.error(
            f"Failed to parse args for '{self.name}' tool. Recieved: {args_result_str}"
        )
        return None

    def _save_and_get_file_references(
        self, file_content: bytes | str, content_type: str
    ) -> List[str]:
        with get_session_with_default_tenant() as db_session:
            file_store = get_default_file_store(db_session)

            file_id = str(uuid.uuid4())

            # Handle both binary and text content
            if isinstance(file_content, str):
                content = BytesIO(file_content.encode())
            else:
                content = BytesIO(file_content)

            file_store.save_file(
                file_name=file_id,
                content=content,
                display_name=file_id,
                file_origin=FileOrigin.CHAT_UPLOAD,
                file_type=content_type,
                file_metadata={
                    "content_type": content_type,
                },
            )

        return [file_id]

    def _parse_csv(self, csv_text: str) -> List[Dict[str, Any]]:
        csv_file = StringIO(csv_text)
        reader = csv.DictReader(csv_file)
        return [row for row in reader]

    """Actual execution of the tool"""

    def run(self, **kwargs: Any) -> Generator[ToolResponse, None, None]:
        request_body = kwargs.get(REQUEST_BODY)

        path_params = {}

        for path_param_schema in self._method_spec.get_path_param_schemas():
            path_params[path_param_schema["name"]] = kwargs[path_param_schema["name"]]

        logger.info(f"kwargs path params: {path_params}")
        query_params = {}
        for query_param_schema in self._method_spec.get_query_param_schemas():
            if query_param_schema["name"] in kwargs:
                query_params[query_param_schema["name"]] = kwargs[
                    query_param_schema["name"]
                ]

        url = self._method_spec.build_url(self._base_url, path_params, query_params)
        method = self._method_spec.method
        logger.info(f"url: {url}")
        logger.info(f"request_body: {request_body}")
        logger.info(f"headers: {self.headers}")

        # Initialize llm_docs for potential citation creation
        llm_docs = []
        
        # Handle Freshdesk API calls with custom logic
        if "seclore.freshdesk.com" in url:
            freshdesk_utils = FreshdeskUtils(
                domain=FRESHDESK_API_DOMAIN,
                api_key=FRESHDESK_API_KEY,
                password=FRESHDESK_API_PASSWORD
            )
            
            # Handle different Freshdesk endpoints
            if "/search/tickets" in url:
                # Search tickets endpoint
                logger.info(f"query_params: {query_params}")
                tool_result = freshdesk_utils.search_tickets_custom_tool(**query_params)
                response_type = "json"
                logger.info(f"Freshdesk search tickets result type: {type(tool_result)}")
                if isinstance(tool_result, dict):
                    logger.info(f"Freshdesk search tickets result keys: {list(tool_result.keys())}")
            elif "/tickets/" in url and path_params.get("ticket_id"):
                # Get ticket details endpoint
                ticket_id = path_params["ticket_id"]
                tool_result = freshdesk_utils.get_ticket_details(ticket_id)
                response_type = "json"
                logger.info(f"Freshdesk ticket details result type: {type(tool_result)}")
                if isinstance(tool_result, dict):
                    logger.info(f"Freshdesk ticket details result keys: {list(tool_result.keys())}")
            elif "/tickets" in url:
                # List tickets endpoint (this is what's being called)
                tool_result = freshdesk_utils.search_tickets_custom_tool(**query_params)
                response_type = "json"
                logger.info(f"Freshdesk list tickets result type: {type(tool_result)}")
                if isinstance(tool_result, dict):
                    logger.info(f"Freshdesk list tickets result keys: {list(tool_result.keys())}")
            else:
                # Fallback to regular API call for other endpoints
                auth = (FRESHDESK_API_KEY, FRESHDESK_API_PASSWORD)
                response = requests.request(
                    method, url, json=request_body, headers=self.headers, auth=auth
                )
                logger.info(f"response: {response}")
                content_type = response.headers.get("Content-Type", "")
                
                if "application/json" in content_type:
                    tool_result = response.json()
                    response_type = "json"
                else:
                    tool_result = response.text
                    response_type = "text"
            
            # Create LlmDoc objects for Freshdesk API responses to enable citations
            # IMPORTANT: Only create LlmDoc objects for current page tickets to prevent context window issues
            # Previous page tickets from chat history will not be included in the context
            logger.info(f"Creating LlmDoc objects for Freshdesk API response: {response_type}")
            if response_type == "json" and isinstance(tool_result, dict):
                # Convert Freshdesk API response to LlmDoc objects
                logger.info(f"Processing Freshdesk JSON response with keys: {list(tool_result.keys())}")
                
                # Handle the new response format with "results" array
                if "results" in tool_result:
                    # Multiple tickets in results array (paginated)
                    tickets = tool_result.get("results", [])
                    total = tool_result.get("total", 0)
                    current_page = tool_result.get("page", 1)
                    total_pages = tool_result.get("total_pages", 1)
                    has_next_page = tool_result.get("has_next_page", False)
                    has_previous_page = tool_result.get("has_previous_page", False)
                    next_page = tool_result.get("next_page")
                    previous_page = tool_result.get("previous_page")
                    summary = tool_result.get("summary", "")
                    
                    logger.info(f"Found {len(tickets)} tickets in results array (page {current_page}/{total_pages}, total available: {total}, has_next: {has_next_page})")
                    
                    # Only create LlmDoc objects for current page tickets to prevent context window issues
                    # Previous page tickets from chat history will not be included
                    for i, ticket in enumerate(tickets):
                        doc_id = f"freshdesk_ticket_{ticket.get('id', i)}"
                        content = json.dumps(ticket, indent=2)
                        blurb = f"Ticket #{ticket.get('id', 'N/A')}: {ticket.get('subject', 'No subject')}"
                        
                        llm_doc = LlmDoc(
                            document_id=doc_id,
                            content=content,
                            blurb=blurb,
                            semantic_identifier=f"Freshdesk Ticket #{ticket.get('id', 'N/A')}",
                            source_type=DocumentSource.FRESHDESK,
                            metadata={
                                "ticket_id": str(ticket.get('id', '')),
                                "subject": ticket.get('subject', ''),
                                "status": str(ticket.get('status', '')),
                                "priority": str(ticket.get('priority', '')),
                                "created_at": ticket.get('created_at', ''),
                                "updated_at": ticket.get('updated_at', ''),
                                "source": "Freshdesk API",
                                "total_available": str(total),
                                "current_page": str(current_page),
                                "total_pages": str(total_pages),
                                "has_next_page": str(has_next_page),
                                "has_previous_page": str(has_previous_page),
                                "next_page": str(next_page) if next_page is not None else "",
                                "previous_page": str(previous_page) if previous_page is not None else "",
                                "pagination_summary": summary
                            },
                            updated_at=datetime.now(),
                            link=ticket.get('link', ''),
                            source_links={i: ticket.get('link', '')} if ticket.get('link') else None,
                            match_highlights=None
                        )
                        llm_docs.append(llm_doc)
                        logger.info(f"Created LlmDoc for ticket {ticket.get('id', 'N/A')}: {doc_id}")
                else:                                                        
                    # Only create LlmDoc objects for current page tickets to prevent context window issues
                    # Previous page tickets from chat history will not be included
                    ticket = tool_result
                    doc_id = f"freshdesk_ticket_{ticket.get('id', 0)}"
                    content = json.dumps(ticket, indent=2)
                    blurb = f"Ticket #{ticket.get('id', 'N/A')}: {ticket.get('subject', 'No subject')}"
                    
                    llm_doc = LlmDoc(
                        document_id=doc_id,
                        content=content,
                        blurb=blurb,
                        semantic_identifier=f"Freshdesk Ticket #{ticket.get('id', 'N/A')}",
                        source_type=DocumentSource.FRESHDESK,
                        metadata={
                            "ticket_id": str(ticket.get('id', '')),
                            "subject": ticket.get('subject', ''),
                            "status": str(ticket.get('status', '')),
                            "priority": str(ticket.get('priority', '')),
                            "created_at": ticket.get('created_at', ''),
                            "updated_at": ticket.get('updated_at', ''),
                            "source": "Freshdesk API"
                        },
                        updated_at=datetime.now(),
                        link=ticket.get('link', ''),
                        source_links={0: ticket.get('link', '')} if ticket.get('link') else None,
                        match_highlights=None
                    )
                    llm_docs.append(llm_doc)
                    logger.info(f"Created LlmDoc for ticket {ticket.get('id', 'N/A')}: {doc_id}")
            
            logger.info(f"Created {len(llm_docs)} LlmDoc objects for Freshdesk API response")
        else:
            # Regular API call for non-Freshdesk URLs
            response = requests.request(
                method, url, json=request_body, headers=self.headers
            )
            
            logger.info(f"response: {response}")
            content_type = response.headers.get("Content-Type", "")

            tool_result: Any
            response_type: str
            if "text/csv" in content_type:
                file_ids = self._save_and_get_file_references(
                    response.content, content_type
                )
                tool_result = CustomToolFileResponse(file_ids=file_ids)
                response_type = "csv"
            elif "image/" in content_type:
                file_ids = self._save_and_get_file_references(
                    response.content, content_type
                )
                tool_result = CustomToolFileResponse(file_ids=file_ids)
                response_type = "image"
            elif "application/json" in content_type:
                try:
                    tool_result = response.json()
                    response_type = "json"
                except JSONDecodeError:
                    tool_result = response.text
                    response_type = "text"
            else:
                tool_result = response.text
                response_type = "text"

        # Yield the main tool response
        yield ToolResponse(
            id=CUSTOM_TOOL_RESPONSE_ID,
            response=CustomToolCallSummary(
                tool_name=self._name,
                tool_result=tool_result, 
                response_type=response_type
            ),
        )
        
        # Yield FINAL_CONTEXT_DOCUMENTS_ID response if LlmDoc objects were created
        if llm_docs:
            logger.info(f"Yielding {len(llm_docs)} LlmDoc objects with FINAL_CONTEXT_DOCUMENTS_ID")
            for doc in llm_docs:
                logger.info(f"LlmDoc: {doc.document_id} - {doc.semantic_identifier}")
            yield ToolResponse(
                id=FINAL_CONTEXT_DOCUMENTS_ID,
                response=llm_docs
            )
        else:
            logger.warning("No LlmDoc objects created - citations will not be available")
            
        # Yield pagination information if available
        if response_type == "json" and isinstance(tool_result, dict) and "results" in tool_result:
            pagination_info = {
                "total_tickets": str(tool_result.get("total", 0)),
                "current_page": str(tool_result.get("page", 1)),
                "total_pages": str(tool_result.get("total_pages", 1)),
                "tickets_in_current_page": str(len(tool_result.get("results", []))),
                "has_next_page": str(tool_result.get("has_next_page", False)),
                "has_previous_page": str(tool_result.get("has_previous_page", False)),
                "next_page": str(tool_result.get("next_page")) if tool_result.get("next_page") is not None else "",
                "previous_page": str(tool_result.get("previous_page")) if tool_result.get("previous_page") is not None else "",
                "summary": tool_result.get("summary", "")
            }
            
            yield ToolResponse(
                id="pagination_info",
                response=pagination_info
            )
       
    def build_next_prompt(
        self,
        prompt_builder: AnswerPromptBuilder,
        tool_call_summary: ToolCallSummary,
        tool_responses: list[ToolResponse],
        using_tool_calling_llm: bool,
    ) -> AnswerPromptBuilder:
        response = cast(CustomToolCallSummary, tool_responses[0].response)

        # Handle non-file responses using search-like tool behavior for citations
        if response.response_type not in ["image", "csv"]:
            return build_next_prompt_for_search_like_tool(
                prompt_builder=prompt_builder,
                tool_call_summary=tool_call_summary,
                tool_responses=tool_responses,
                using_tool_calling_llm=using_tool_calling_llm,
                answer_style_config=self.answer_style_config,
                prompt_config=self.prompt_config,
            )

        # Handle image and CSV file responses
        file_type = (
            ChatFileType.IMAGE
            if response.response_type == "image"
            else ChatFileType.CSV
        )

        # Load files from storage
        files = []
        with get_session_with_default_tenant() as db_session:
            file_store = get_default_file_store(db_session)

            for file_id in response.tool_result.file_ids:
                try:
                    file_io = file_store.read_file(file_id, mode="b")
                    files.append(
                        InMemoryChatFile(
                            file_id=file_id,
                            filename=file_id,
                            content=file_io.read(),
                            file_type=file_type,
                        )
                    )
                except Exception:
                    logger.exception(f"Failed to read file {file_id}")

            # Update prompt with file content
            prompt_builder.update_user_prompt(
                build_custom_image_generation_user_prompt(
                    query=prompt_builder.get_user_message_content(),
                    files=files,
                    file_type=file_type,
                )
            )

        return prompt_builder

    def final_result(self, *args: ToolResponse) -> JSON_ro:
        response = cast(CustomToolCallSummary, args[0].response)
        if isinstance(response.tool_result, CustomToolFileResponse):
            return response.tool_result.model_dump()
        return response.tool_result

    """Other utility functions"""

    @classmethod
    def get_custom_tool_result(
        cls, llm_call: LLMCall
    ) -> tuple[list[LlmDoc], list[LlmDoc]] | None:
        """
        Returns the final custom tool results and a map of docs to their original rank (which is what is displayed to user)
        Similar to SearchTool.get_search_result but for custom tools
        """
        if not llm_call.tool_call_info:
            logger.info("No tool call info available for custom tool result extraction")
            return None

        final_custom_results = []
        initial_custom_results = []

        logger.info(f"Processing {len(llm_call.tool_call_info)} tool call info items for custom tool results")
        
        # Log all tool call info items for debugging
        for i, item in enumerate(llm_call.tool_call_info):
            logger.info(f"Tool call info item {i}: type={type(item)}, id={getattr(item, 'id', 'N/A')}")

        for yield_item in llm_call.tool_call_info:
            if (
                isinstance(yield_item, ToolResponse)
                and yield_item.id == FINAL_CONTEXT_DOCUMENTS_ID
            ):
                final_custom_results = cast(list[LlmDoc], yield_item.response)
                logger.info(f"Found {len(final_custom_results)} final custom tool results")
                for doc in final_custom_results:
                    logger.info(f"Final custom doc: {doc.document_id} - {doc.semantic_identifier}")
            elif (
                isinstance(yield_item, ToolResponse)
                and yield_item.id == ORIGINAL_CONTEXT_DOCUMENTS_ID
            ):
                # For custom tools, we might not have original context documents
                # but we can still handle them if they exist
                search_contexts = yield_item.response.contexts
                for doc in search_contexts:
                    if doc.document_id not in initial_custom_results:
                        initial_custom_results.append(doc)

                initial_custom_results = cast(list[LlmDoc], initial_custom_results)
                logger.info(f"Found {len(initial_custom_results)} initial custom tool results")
            else:
                logger.info(f"Skipping tool call info item: type={type(yield_item)}, id={getattr(yield_item, 'id', 'N/A')}")

        # If we found final results, return them even if initial results are empty
        if final_custom_results:
            logger.info(f"Returning custom tool results: final={len(final_custom_results)}, initial={len(initial_custom_results)}")
            return final_custom_results, initial_custom_results
        else:
            logger.warning("No final custom tool results found - citations may not appear")
            return None


def build_custom_tools_from_openapi_schema_and_headers(
    openapi_schema: dict[str, Any],
    custom_headers: list[HeaderItemDict] | None = None,
    dynamic_schema_info: DynamicSchemaInfo | None = None,
    user_oauth_token: str | None = None,
    answer_style_config: AnswerStyleConfig | None = None,
    prompt_config: PromptConfig | None = None,
) -> list[CustomTool]:
    if dynamic_schema_info:
        # Process dynamic schema information
        schema_str = json.dumps(openapi_schema)
        placeholders = {
            CHAT_SESSION_ID_PLACEHOLDER: dynamic_schema_info.chat_session_id,
            MESSAGE_ID_PLACEHOLDER: dynamic_schema_info.message_id,
        }

        for placeholder, value in placeholders.items():
            if value:
                schema_str = schema_str.replace(placeholder, str(value))

        openapi_schema = json.loads(schema_str)

    url = openapi_to_url(openapi_schema)
    method_specs = openapi_to_method_specs(openapi_schema)
    return [
        CustomTool(
            method_spec,
            url,
            custom_headers,
            user_oauth_token=user_oauth_token,
            answer_style_config=answer_style_config,
            prompt_config=prompt_config,
        )
        for method_spec in method_specs
    ]


if __name__ == "__main__":
    import openai

    openapi_schema = {
        "openapi": "3.0.0",
        "info": {
            "version": "1.0.0",
            "title": "Assistants API",
            "description": "An API for managing assistants",
        },
        "servers": [
            {"url": "http://localhost:8080"},
        ],
        "paths": {
            "/assistant/{assistant_id}": {
                "get": {
                    "summary": "Get a specific Assistant",
                    "operationId": "getAssistant",
                    "parameters": [
                        {
                            "name": "assistant_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                },
                "post": {
                    "summary": "Create a new Assistant",
                    "operationId": "createAssistant",
                    "parameters": [
                        {
                            "name": "assistant_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                },
            }
        },
    }
    validate_openapi_schema(openapi_schema)

    tools = build_custom_tools_from_openapi_schema_and_headers(
        openapi_schema, dynamic_schema_info=None
    )

    openai_client = openai.OpenAI()
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Can you fetch assistant with ID 10"},
        ],
        tools=[tool.tool_definition() for tool in tools],  # type: ignore
    )
    choice = response.choices[0]
    if choice.message.tool_calls:
        print(choice.message.tool_calls)
        for tool_response in tools[0].run(
            **json.loads(choice.message.tool_calls[0].function.arguments)
        ):
            print(tool_response)
