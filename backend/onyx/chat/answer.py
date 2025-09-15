from collections.abc import Callable
from collections.abc import Iterator
import time
from uuid import uuid4

from langchain.schema.messages import BaseMessage
from langchain_core.messages import AIMessageChunk
from langchain_core.messages import ToolCall
from langchain_core.messages import SystemMessage
from langchain_core.messages import HumanMessage

from onyx.chat.llm_response_handler import LLMResponseHandlerManager
from onyx.chat.models import AnswerQuestionPossibleReturn
from onyx.chat.models import AnswerStyleConfig
from onyx.chat.models import CitationInfo
from onyx.chat.models import OnyxAnswerPiece
from onyx.chat.models import PromptConfig
from onyx.llm.utils import check_message_tokens
from onyx.chat.prompt_builder.answer_prompt_builder import AnswerPromptBuilder
from onyx.chat.prompt_builder.answer_prompt_builder import default_build_system_message
from onyx.chat.prompt_builder.answer_prompt_builder import default_build_user_message
from onyx.chat.prompt_builder.answer_prompt_builder import LLMCall
from onyx.chat.stream_processing.answer_response_handler import (
    CitationResponseHandler,
)
from onyx.chat.stream_processing.answer_response_handler import (
    DummyAnswerResponseHandler,
)
from onyx.chat.stream_processing.utils import (
    map_document_id_order,
)
from onyx.chat.tool_handling.tool_response_handler import ToolResponseHandler
from onyx.file_store.utils import InMemoryChatFile
from onyx.llm.interfaces import LLM
from onyx.llm.models import PreviousMessage
from onyx.natural_language_processing.utils import get_tokenizer
from onyx.tools.force import ForceUseTool
from onyx.tools.models import ToolResponse
from onyx.tools.tool import Tool
from onyx.tools.tool_implementations.search.search_tool import SearchTool
from onyx.tools.tool_runner import ToolCallKickoff
from onyx.tools.utils import explicit_tool_calling_supported
from onyx.utils.logger import setup_logger
from onyx.chat.chunked_processing import ChunkedContentProcessor
from onyx.file_store.models import ChatFileType

logger = setup_logger()


AnswerStream = Iterator[AnswerQuestionPossibleReturn | ToolCallKickoff | ToolResponse]


class Answer:
    def __init__(
        self,
        question: str,
        answer_style_config: AnswerStyleConfig,
        llm: LLM,
        prompt_config: PromptConfig,
        force_use_tool: ForceUseTool,
        # must be the same length as `docs`. If None, all docs are considered "relevant"
        message_history: list[PreviousMessage] | None = None,
        single_message_history: str | None = None,
        # newly passed in files to include as part of this question
        # TODO THIS NEEDS TO BE HANDLED
        latest_query_files: list[InMemoryChatFile] | None = None,
        files: list[InMemoryChatFile] | None = None,
        tools: list[Tool] | None = None,
        # NOTE: for native tool-calling, this is only supported by OpenAI atm,
        #       but we only support them anyways
        # if set to True, then never use the LLMs provided tool-calling functonality
        skip_explicit_tool_calling: bool = False,
        # Returns the full document sections text from the search tool
        return_contexts: bool = False,
        skip_gen_ai_answer_generation: bool = False,
        is_connected: Callable[[], bool] | None = None,
        conversation_summary: str | None = None,
    ) -> None:
        # if single_message_history and message_history:
        #     raise ValueError(
        #         "Cannot provide both `message_history` and `single_message_history`"
        #     )

        self.question = question
        self.is_connected: Callable[[], bool] | None = is_connected

        self.latest_query_files = latest_query_files or []
        self.file_id_to_file = {file.file_id: file for file in (files or [])}

        self.tools = tools or []
        self.force_use_tool = force_use_tool

        self.message_history = message_history or []
        # used for QA flow where we only want to send a single message
        self.single_message_history = single_message_history

        self.answer_style_config = answer_style_config
        self.prompt_config = prompt_config

        self.llm = llm
        self.llm_tokenizer = get_tokenizer(
            provider_type=llm.config.model_provider,
            model_name=llm.config.model_name,
        )

        self._final_prompt: list[BaseMessage] | None = None

        self._streamed_output: list[str] | None = None
        self._processed_stream: (
            list[AnswerQuestionPossibleReturn | ToolResponse | ToolCallKickoff] | None
        ) = None

        self._return_contexts = return_contexts
        self.skip_gen_ai_answer_generation = skip_gen_ai_answer_generation
        self._is_cancelled = False

        self.using_tool_calling_llm = (
            explicit_tool_calling_supported(
                self.llm.config.model_provider, self.llm.config.model_name
            )
            and not skip_explicit_tool_calling
        )

        self.conversation_summary = conversation_summary

    def _get_tools_list(self) -> list[Tool]:
        if not self.force_use_tool.force_use:
            return self.tools

        tool = next(
            (t for t in self.tools if t.name == self.force_use_tool.tool_name), None
        )
        if tool is None:
            raise RuntimeError(f"Tool '{self.force_use_tool.tool_name}' not found")

        logger.info(
            f"Forcefully using tool='{tool.name}'"
            + (
                f" with args='{self.force_use_tool.args}'"
                if self.force_use_tool.args is not None
                else ""
            )
        )
        return [tool]

    def _should_use_chunked_processing(self, final_prompt: list[BaseMessage], max_tokens: int) -> bool:
        """Check if chunked processing should be used based on token limits."""
        try:
            # Calculate total tokens in the final prompt
            total_tokens = sum(
                check_message_tokens(message, self.llm_tokenizer.encode) 
                for message in final_prompt
            )
            
            # Reserve tokens for response and safety buffer
            reserved_tokens = 2000
            available_tokens = max_tokens - reserved_tokens
            
            logger.info(f"Final prompt tokens: {total_tokens}, Max tokens: {max_tokens}, Available: {available_tokens}")
            
            return total_tokens > available_tokens
            
        except Exception as e:
            logger.error(f"Error checking token limits for chunked processing: {e}")
            return False

    def _handle_chunked_processing(self, current_llm_call: LLMCall) -> AnswerStream:
        """Handle chunked processing when the final prompt is too large."""
        logger.info("Using chunked processing due to large prompt size")
        
        # Get the final prompt
        final_prompt = current_llm_call.prompt_builder.build()
        
        # Extract system message and history
        system_message = None
        history_messages = []
        user_message = None
        
        for message in final_prompt:
            if isinstance(message, SystemMessage):
                system_message = message
            elif isinstance(message, BaseMessage) and hasattr(message, 'type'):
                if message.type == 'human':
                    user_message = message
                else:
                    history_messages.append(message)
        
        # If no user message found, create one from the question
        if not user_message:
            user_message = HumanMessage(content=self.question)
        
        # Initialize chunked processor
        max_tokens = getattr(self.llm.config, 'max_tokens', 8192)
        chunked_processor = ChunkedContentProcessor(self.llm, max_tokens)
        
        # Get the content that needs to be chunked (from user message or files)
        content_to_chunk = user_message.content if hasattr(user_message, 'content') else self.question
        
        # Add file contents if available
        if self.latest_query_files:
            file_contents = []
            for file in self.latest_query_files:
                if hasattr(file, 'content'):
                    file_contents.append(f"File: {file.file_id}\n{file.content}")
            if file_contents:
                content_to_chunk += "\n\n" + "\n\n".join(file_contents)
        
        # Process the content in chunks and stream the response
        logger.info("Starting chunked processing...")
        
        # Stream the chunked response directly
        for response_chunk in chunked_processor.process_large_content(
            content=content_to_chunk,
            original_query=self.question,
            history_messages=history_messages,
            system_message=system_message
        ):
            # Create answer pieces for each chunk of the response
            from onyx.chat.models import OnyxAnswerPiece
            if response_chunk and response_chunk.strip():
                yield OnyxAnswerPiece(answer_piece=response_chunk)
        
        # Handle citations if any
        # Note: In chunked processing, citations might be limited
        # You may want to implement citation handling for chunked responses
        
        logger.info("Chunked processing completed successfully")

    def _handle_specified_tool_call(
        self, llm_calls: list[LLMCall], tool: Tool, tool_args: dict
    ) -> AnswerStream:
        current_llm_call = llm_calls[-1]

        # make a dummy tool handler
        tool_handler = ToolResponseHandler([tool])

        dummy_tool_call_chunk = AIMessageChunk(content="")
        dummy_tool_call_chunk.tool_calls = [
            ToolCall(name=tool.name, args=tool_args, id=str(uuid4()))
        ]

        response_handler_manager = LLMResponseHandlerManager(
            tool_handler, DummyAnswerResponseHandler(), self.is_cancelled
        )
        yield from response_handler_manager.handle_llm_response(
            iter([dummy_tool_call_chunk])
        )

        new_llm_call = response_handler_manager.next_llm_call(current_llm_call)
        if new_llm_call:
            yield from self._get_response(llm_calls + [new_llm_call])
        else:
            raise RuntimeError("Tool call handler did not return a new LLM call")

    def _get_response(self, llm_calls: list[LLMCall]) -> AnswerStream:
        current_llm_call = llm_calls[-1]

        # handle the case where no decision has to be made; we simply run the tool
        if (
            current_llm_call.force_use_tool.force_use
            and current_llm_call.force_use_tool.args is not None
        ):
            tool_name, tool_args = (
                current_llm_call.force_use_tool.tool_name,
                current_llm_call.force_use_tool.args,
            )
            tool = next(
                (t for t in current_llm_call.tools if t.name == tool_name), None
            )
            if not tool:
                raise RuntimeError(f"Tool '{tool_name}' not found")

            yield from self._handle_specified_tool_call(llm_calls, tool, tool_args)
            return

        # special pre-logic for non-tool calling LLM case
        if not self.using_tool_calling_llm and current_llm_call.tools:
            chosen_tool_and_args = (
                ToolResponseHandler.get_tool_call_for_non_tool_calling_llm(
                    current_llm_call, self.llm, self.prompt_config
                )
            )
            logger.info("returning from the tool call 1")
            if chosen_tool_and_args:
                tool, tool_args = chosen_tool_and_args
                logger.info("returning from the tool call 2")
                logger.info(f"returning from the tool call {tool_args}")
                yield from self._handle_specified_tool_call(llm_calls, tool, tool_args)
                return

        # if we're skipping gen ai answer generation, we should break
        # out unless we're forcing a tool call. If we don't, we might generate an
        # answer, which is a no-no!
        if (
            self.skip_gen_ai_answer_generation
            and not current_llm_call.force_use_tool.force_use
        ):
            logger.info("returning from the tool call 2.5")
            return
        logger.info("returning from the tool call 3")
        
        # Check if chunked processing is needed due to large prompt size
        final_prompt = current_llm_call.prompt_builder.build()
        # logger.info(f"final prompt: {final_prompt}")
        max_tokens = current_llm_call.prompt_builder.max_tokens
        if not max_tokens:
            # Fallback to LLM config max_tokens or default
            max_tokens = getattr(self.llm.config, 'max_tokens', 8192)
        
        if self._should_use_chunked_processing(final_prompt, max_tokens):
            logger.info("Final prompt is too large, using chunked processing")
            yield from self._handle_chunked_processing(current_llm_call)
            return
        
        # set up "handlers" to listen to the LLM response stream and
        # feed back the processed results + handle tool call requests
        # + figure out what the next LLM call should be
        tool_call_handler = ToolResponseHandler(current_llm_call.tools)

        # Get search results
        final_search_results, displayed_search_results = SearchTool.get_search_result(
            current_llm_call
        ) or ([], [])

        answer_handler = CitationResponseHandler(
            context_docs=final_search_results,
            final_doc_id_to_rank_map=map_document_id_order(final_search_results),
            display_doc_id_to_rank_map=map_document_id_order(displayed_search_results),
        )

        response_handler_manager = LLMResponseHandlerManager(
            tool_call_handler, answer_handler, self.is_cancelled
        )

        for tool in current_llm_call.tools:
            definition = tool.tool_definition()
            logger.info(f"tool definition: {definition}")

        tools=[tool.tool_definition() for tool in current_llm_call.tools] or None
        logger.info(f"tool list: {tools}")

        # Log token counts and max tokens
        max_tokens = current_llm_call.prompt_builder.max_tokens
        logger.info(f"Max allowed tokens: {max_tokens}")
        
        total_tokens = 0
        for i, message in enumerate(final_prompt):
            #token_count = check_message_tokens(message, self.llm_tokenizer_encode_func)
            #total_tokens += token_count
            # logger.info(f"Message {i + 1}:")
            # logger.info(f"Type: {message.type}")
            # #logger.info(f"Token count: {token_count}")
            # logger.info(f"Content: {message.content}")
            # logger.info("---")
            pass
        
        #logger.info(f"Total tokens in final prompt: {total_tokens}")
        #logger.info(f"Tokens remaining: {max_tokens - total_tokens}")
        
        # Add detailed logging of the final prompt and history
        logger.info("=== Final Prompt and History Being Sent to Model ===")

        # DEBUG: good breakpoint
        stream = self.llm.stream(
            # For tool calling LLMs, we want to insert the task prompt as part of this flow, this is because the LLM
            # may choose to not call any tools and just generate the answer, in which case the task prompt is needed.
            prompt=final_prompt,
            tools=[tool.tool_definition() for tool in current_llm_call.tools] or None,
            tool_choice=(
                "required"
                if current_llm_call.tools and current_llm_call.force_use_tool.force_use
                else None
            ),
            structured_response_format=self.answer_style_config.structured_response_format,
        )

        logger.info("Documents after LLM call:")
        logger.info(f"Final search results1: {[doc.document_id for doc in final_search_results]}")
        logger.info(f"Displayed search results1: {[doc.document_id for doc in displayed_search_results]}")
        
        start_llm = time.perf_counter()
        yield from response_handler_manager.handle_llm_response(stream)
        end_llm = time.perf_counter()
        logger.info(f"LLM + response handling time: {end_llm - start_llm:.2f}s")

        new_llm_call = response_handler_manager.next_llm_call(current_llm_call)
        if new_llm_call:
            yield from self._get_response(llm_calls + [new_llm_call])

    def _get_response(self, llm_calls: list[LLMCall]) -> AnswerStream:
        current_llm_call = llm_calls[-1]

        # handle the case where no decision has to be made; we simply run the tool
        if (
            current_llm_call.force_use_tool.force_use
            and current_llm_call.force_use_tool.args is not None
        ):
            tool_name, tool_args = (
                current_llm_call.force_use_tool.tool_name,
                current_llm_call.force_use_tool.args,
            )
            tool = next(
                (t for t in current_llm_call.tools if t.name == tool_name), None
            )
            if not tool:
                raise RuntimeError(f"Tool '{tool_name}' not found")

            yield from self._handle_specified_tool_call(llm_calls, tool, tool_args)
            return

        # special pre-logic for non-tool calling LLM case
        if not self.using_tool_calling_llm and current_llm_call.tools:
            chosen_tool_and_args = (
                ToolResponseHandler.get_tool_call_for_non_tool_calling_llm(
                    current_llm_call, self.llm, self.prompt_config
                )
            )
            logger.info("returning from the tool call 1")
            if chosen_tool_and_args:
                tool, tool_args = chosen_tool_and_args
                logger.info("returning from the tool call 2")
                logger.info(f"returning from the tool call {tool_args}")
                yield from self._handle_specified_tool_call(llm_calls, tool, tool_args)
                return

        # if we're skipping gen ai answer generation, we should break
        # out unless we're forcing a tool call. If we don't, we might generate an
        # answer, which is a no-no!
        if (
            self.skip_gen_ai_answer_generation
            and not current_llm_call.force_use_tool.force_use
        ):
            logger.info("returning from the tool call 2.5")
            return
        logger.info("returning from the tool call 3")
        
        # Check for large content BEFORE building the final prompt
        max_tokens = current_llm_call.prompt_builder.max_tokens
        
        # Check if we have large files that need chunked processing
        large_files_detected = False
        try:
            # Check the raw files before they're processed into the user message
            raw_files = current_llm_call.files
            if raw_files:
                # Get tokenizer for estimation
                tokenizer = get_tokenizer(model_name="gpt-4", provider_type="openai")
                
                total_file_tokens = 0
                for file in raw_files:
                    if file.file_type in (ChatFileType.PLAIN_TEXT, ChatFileType.CSV):
                        try:
                            file_content = file.content.decode("utf-8")
                            file_tokens = len(tokenizer.encode(file_content))
                            total_file_tokens += file_tokens
                            logger.info(f"File {file.filename}: {file_tokens:,} tokens")
                        except Exception as e:
                            logger.warning(f"Could not estimate tokens for file {file.filename}: {e}")
                
                logger.info(f"Total file tokens: {total_file_tokens:,}")
                
                # If files are extremely large, use chunked processing
                if total_file_tokens > 50000:  # 50K token threshold for chunked processing
                    large_files_detected = False
                    logger.info(f"Large files detected ({total_file_tokens:,} tokens), using chunked processing")
                    
        except Exception as e:
            logger.warning(f"Error checking file sizes for chunked processing: {e}")
        
        # Check if content should be processed in chunks
        if large_files_detected:
            logger.info("Content is too large, using chunked processing")
            
            # Build the final prompt only for chunked processing
            final_prompt = current_llm_call.prompt_builder.build()
            
            # Extract system message and history
            system_message = None
            history_messages = []
            
            for message in final_prompt:
                if message.type == "system":
                    system_message = message
                elif message.type != "human":  # Not the current user message
                    history_messages.append(message)
            
            # Use chunked processor
            chunked_processor = ChunkedContentProcessor(self.llm, max_tokens)
            
            # Extract file content directly from raw files
            file_content = ""
            for file in raw_files:
                if file.file_type in (ChatFileType.PLAIN_TEXT, ChatFileType.CSV):
                    try:
                        file_content += f"DOCUMENT: {file.filename}\n" if file.filename else ""
                        file_content += file.content.decode("utf-8") + "\n\n"
                    except Exception as e:
                        logger.warning(f"Could not decode file {file.filename}: {e}")
            
            # Process in chunks and yield responses
            logger.info(f"before process in chunks and yield responses ")
            for chunk_response in chunked_processor.process_large_content(
                content=file_content,
                original_query=self.question,
                history_messages=history_messages,
                system_message=system_message
            ):
                logger.info(f"chunk response11: {chunk_response}")
                yield OnyxAnswerPiece(answer_piece=chunk_response)
            
            return
        
        # Continue with normal processing if content is not too large
        # Build the final prompt for normal processing
        try:
            logger.info("building the final prompt in the normal processing")
            final_prompt = current_llm_call.prompt_builder.build()
            # logger.info(f"final prompt: {final_prompt}")
            logger.info(f"final prompt done in the normal processing")
        except ValueError as e:
            if "too large to process" in str(e):
                logger.info("Content from tool response is too large, using chunked processing")
                
                # Extract the user message content from the prompt builder
                user_message_content = current_llm_call.prompt_builder.get_user_message_content()
                
                # Extract system message and history
                system_message = None
                history_messages = []

                logger.info(f"system message and token cnt: {current_llm_call.prompt_builder.system_message_and_token_cnt[1]}")
                logger.info(f"message history: {current_llm_call.prompt_builder.message_history}")
                logger.info(f"user message content: {current_llm_call.prompt_builder.user_message_and_token_cnt[1]}")
                
                if current_llm_call.prompt_builder.system_message_and_token_cnt:
                    system_message = current_llm_call.prompt_builder.system_message_and_token_cnt[0]
                
                # Add history messages
                history_messages.extend(current_llm_call.prompt_builder.message_history)
                
                # Use chunked processor
                chunked_processor = ChunkedContentProcessor(self.llm, max_tokens)
                
                # Process in chunks and yield responses
                for chunk_response in chunked_processor.process_large_content(
                    content=user_message_content,
                    original_query=self.question,
                    history_messages=history_messages,
                    system_message=system_message
                ):
                    # logger.info(f"chunk response11111111: {chunk_response}")
                    yield OnyxAnswerPiece(answer_piece=chunk_response)
                
                return
            else:
                # Re-raise if it's a different ValueError
                raise
        
        # set up "handlers" to listen to the LLM response stream and
        # feed back the processed results + handle tool call requests
        # + figure out what the next LLM call should be
        tool_call_handler = ToolResponseHandler(current_llm_call.tools)

        final_search_results, displayed_search_results = SearchTool.get_search_result(
            current_llm_call
        ) or ([], [])

        answer_handler = CitationResponseHandler(
                context_docs=final_search_results,
                final_doc_id_to_rank_map=map_document_id_order(final_search_results),
                display_doc_id_to_rank_map=map_document_id_order(displayed_search_results),
            )

        response_handler_manager = LLMResponseHandlerManager(
            tool_call_handler, answer_handler, self.is_cancelled
        )

        for tool in current_llm_call.tools:
            definition = tool.tool_definition()
            logger.info(f"tool definition: {definition}")

        tools=[tool.tool_definition() for tool in current_llm_call.tools] or None
        logger.info(f"tool list: {tools}")
        logger.info(f"Max allowed tokens: {max_tokens}")
        # total_tokens = 0
        for i, message in enumerate(final_prompt):
            # token_count = check_message_tokens(message, self.llm_tokenizer_encode_func)
            # total_tokens += token_count
            logger.info(f"Message {i + 1}:")
            logger.info(f"Type: {message.type}")
            #logger.info(f"Token count: {token_count}")
            logger.info(f"Content: {message.content}")
            # logger.info(f"type: {message.type} content length: {len(message.content)}")
            pass
        
        # logger.info(f"Total tokens in final prompt: {total_tokens}")
        #logger.info(f"Tokens remaining: {max_tokens - total_tokens}")
        
        # DEBUG: good breakpoint
        stream = self.llm.stream(
            # For tool calling LLMs, we want to insert the task prompt as part of this flow, this is because the LLM
            # may choose to not call any tools and just generate the answer, in which case the task prompt is needed.
            prompt=final_prompt,
            tools=[tool.tool_definition() for tool in current_llm_call.tools] or None,
            tool_choice=(
                "required"
                if current_llm_call.tools and current_llm_call.force_use_tool.force_use
                else None
            ),
            structured_response_format=self.answer_style_config.structured_response_format,
        )
        
        logger.info("Documents after LLM call:")
        logger.info(f"Final search results1: {[doc.document_id for doc in final_search_results]}")
        logger.info(f"Displayed search results1: {[doc.document_id for doc in displayed_search_results]}")
        start_llm2 = time.perf_counter()
        yield from response_handler_manager.handle_llm_response(stream)
        end_llm2 = time.perf_counter()
        logger.info(f"LLM + response handling time: {end_llm2 - start_llm2:.2f}s")

        new_llm_call = response_handler_manager.next_llm_call(current_llm_call)
        if new_llm_call:
            yield from self._get_response(llm_calls + [new_llm_call])

    @property
    def processed_streamed_output(self) -> AnswerStream:
        if self._processed_stream is not None:
            yield from self._processed_stream
            return

        prompt_builder = AnswerPromptBuilder(
            user_message=default_build_user_message(
                user_query=self.question,
                prompt_config=self.prompt_config,
                files=self.latest_query_files,
                single_message_history=self.single_message_history,
            ),
            message_history=self.message_history,
            llm_config=self.llm.config,
            raw_user_query=self.question,
            raw_user_uploaded_files=self.latest_query_files or [],
            single_message_history=self.single_message_history,
        )
        prompt_builder.update_system_prompt(
            default_build_system_message(self.prompt_config)
        )
        
        # Add conversation summary to the system message if it exists
        if self.conversation_summary:
            # Get the current system message and append the summary to it
            current_system_msg = default_build_system_message(self.prompt_config)
            if current_system_msg:
                enhanced_content = f"{current_system_msg.content}\n\nPrevious conversation summary: {self.conversation_summary}"
                enhanced_system_msg = SystemMessage(content=enhanced_content)
                prompt_builder.update_system_prompt(enhanced_system_msg)
                logger.info(f"[SUMMARY ADDED] Added conversation summary to system message: {self.conversation_summary[:100]}...")
            else:
                # If no system message exists, create one with just the summary
                summary_system_msg = SystemMessage(content=f"Previous conversation summary: {self.conversation_summary}")
                prompt_builder.update_system_prompt(summary_system_msg)
                logger.info(f"[SUMMARY ADDED] Created system message with summary: {self.conversation_summary[:100]}...")
        
        llm_call = LLMCall(
            prompt_builder=prompt_builder,
            tools=self._get_tools_list(),
            force_use_tool=self.force_use_tool,
            files=self.latest_query_files,
            tool_call_info=[],
            using_tool_calling_llm=self.using_tool_calling_llm,
        )

        processed_stream = []
        for processed_packet in self._get_response([llm_call]):
            processed_stream.append(processed_packet)
            yield processed_packet

        self._processed_stream = processed_stream

    @property
    def llm_answer(self) -> str:
        answer = ""
        for packet in self.processed_streamed_output:
            if isinstance(packet, OnyxAnswerPiece) and packet.answer_piece:
                answer += packet.answer_piece

        return answer

    @property
    def citations(self) -> list[CitationInfo]:
        citations: list[CitationInfo] = []
        for packet in self.processed_streamed_output:
            if isinstance(packet, CitationInfo):
                citations.append(packet)

        return citations

    def is_cancelled(self) -> bool:
        if self._is_cancelled:
            return True

        if self.is_connected is not None:
            if not self.is_connected():
                logger.debug("Answer stream has been cancelled")
            self._is_cancelled = not self.is_connected()

        return self._is_cancelled