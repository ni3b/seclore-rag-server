"""
Chunked processing for large content that exceeds token limits.
This module handles splitting large content into manageable chunks and processing them iteratively.
"""

import math
from typing import Iterator, List, Tuple, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from onyx.llm.interfaces import LLM
from onyx.llm.utils import check_message_tokens, check_number_of_tokens
from onyx.natural_language_processing.utils import get_tokenizer
from onyx.utils.logger import setup_logger

logger = setup_logger()


class ChunkedContentProcessor:
    """Handles processing of large content by splitting it into chunks and processing iteratively."""
    
    def __init__(self, llm: LLM, max_tokens: int):
        self.llm = llm
        self.max_tokens = max_tokens
        self.tokenizer = get_tokenizer(
            provider_type=llm.config.model_provider,
            model_name=llm.config.model_name,
        )
        
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(self.tokenizer.encode(text))
    
    def _calculate_available_tokens(self, messages: List[BaseMessage]) -> int:
        """Calculate how many tokens are available for new content."""
        used_tokens = sum(
            check_message_tokens(msg, self.tokenizer.encode) for msg in messages
        )
        # Reserve tokens for response and buffers
        reserved_tokens = 2000  # Reserve for AI response and safety buffer
        available = self.max_tokens - used_tokens - reserved_tokens
        return max(available, 1000)  # Minimum 1000 tokens for content
    
    def _split_content_into_chunks(self, content: str, chunk_size: int) -> List[str]:
        """Split content into chunks based on token limits."""
        content_tokens = self._estimate_tokens(content)
        
        if content_tokens <= chunk_size:
            return [content]
        
        # Split by lines first to preserve structure
        lines = content.split('\n')
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for line in lines:
            line_tokens = self._estimate_tokens(line + '\n')
            
            if current_tokens + line_tokens > chunk_size and current_chunk:
                # Current chunk is full, start new one
                chunks.append(current_chunk.strip())
                current_chunk = line + '\n'
                current_tokens = line_tokens
            else:
                current_chunk += line + '\n'
                current_tokens += line_tokens
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _create_chunk_prompt(
        self, 
        chunk: str, 
        chunk_index: int, 
        total_chunks: int,
        previous_responses: List[str],
        original_query: str
    ) -> str:
        """Create a prompt for processing a specific chunk."""
        
        prompt = f"""You are analyzing a large document/content in chunks. 

ORIGINAL QUERY: {original_query}

CHUNK {chunk_index + 1} OF {total_chunks}:
{chunk}

"""
        
        if previous_responses:
            prompt += f"""
PREVIOUS ANALYSIS FROM EARLIER CHUNKS:
{chr(10).join(f"Chunk {i+1}: {resp}" for i, resp in enumerate(previous_responses))}

INSTRUCTIONS:
1. Analyze this new chunk in the context of the original query
2. Consider the previous analysis from earlier chunks
3. If this chunk provides NEW information that should be added to the previous analysis, state what should be added
4. If this chunk CONTRADICTS or MODIFIES previous analysis, state what should be changed
5. If this chunk doesn't add significant new information, state that
6. Provide your analysis for this chunk

RESPONSE FORMAT:
MODIFICATIONS_TO_PREVIOUS: [What changes/additions should be made to previous analysis, or "None"]
CURRENT_CHUNK_ANALYSIS: [Your analysis of this chunk]
"""
        else:
            prompt += """
INSTRUCTIONS:
This is the first chunk. Analyze it according to the original query and provide your findings.

RESPONSE FORMAT:
CURRENT_CHUNK_ANALYSIS: [Your analysis of this chunk]
"""
        
        return prompt
    
    def _create_final_consolidation_prompt(
        self, 
        all_responses: List[str], 
        original_query: str
    ) -> str:
        """Create a prompt for final consolidation of all chunk responses."""
        
        prompt = f"""You have analyzed a large document/content in chunks. Now provide a final consolidated response.

ORIGINAL QUERY: {original_query}

ALL CHUNK ANALYSES:
{chr(10).join(f"Chunk {i+1}: {resp}" for i, resp in enumerate(all_responses))}

INSTRUCTIONS:
Provide a comprehensive, consolidated response to the original query based on all the chunk analyses. 
Synthesize the information, resolve any contradictions, and provide a coherent final answer.

FINAL RESPONSE:
"""
        return prompt
    
    def process_large_content(
        self,
        content: str,
        original_query: str,
        history_messages: List[BaseMessage],
        system_message: Optional[BaseMessage] = None
    ) -> Iterator[str]:
        # logger.info(f"content11111111: {content}")
        # logger.info(f"original_query11111111: {original_query}")
        # logger.info(f"history_messages11111111: {history_messages}")
        # logger.info(f"system_message11111111: {system_message}")

        """
        Process large content by splitting into chunks and processing iteratively.
        
        Args:
            content: The large content to process
            original_query: The original user query
            history_messages: Previous conversation history
            system_message: Optional system message
            
        Yields:
            Incremental responses as chunks are processed
        """
        
        logger.info(f"Starting chunked processing for content with {self._estimate_tokens(content)} tokens")
        
        # Extract the actual file content if it's in the message
        from onyx.llm.utils import extract_large_content_from_message
        actual_content = extract_large_content_from_message(content)
        # logger.info(f"actual_content11111111: {actual_content}")
        
        # Calculate available tokens for content
        base_messages = []
        if system_message:
            base_messages.append(system_message)
        base_messages.extend(history_messages)
        
        available_tokens = self._calculate_available_tokens(base_messages)
        # Use 80% of available tokens per chunk for better efficiency
        # This reduces the number of chunks significantly
        chunk_size = int(available_tokens * 0.8)
        
        logger.info(f"Available tokens: {available_tokens}, chunk size: {chunk_size}")
        logger.info(f"Total content tokens: {self._estimate_tokens(actual_content)}")
        logger.info(f"Expected number of chunks: {math.ceil(self._estimate_tokens(actual_content) / chunk_size)}")
        
        # Split content into chunks
        chunks = self._split_content_into_chunks(actual_content, chunk_size)
        logger.info(f"Split content into {len(chunks)} chunks")
        
        # If only one chunk, just process normally
        if len(chunks) == 1:
            logger.info("Content fits in one chunk after extraction, processing normally")
            yield f"PROCESSING CONTENT:\n{chunks[0]}"
            return
        
        previous_responses = []
        
        # Process each chunk silently (don't yield intermediate results)
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            # Create prompt for this chunk
            chunk_prompt = self._create_chunk_prompt(
                chunk, i, len(chunks), previous_responses, original_query
            )
            
            # Build messages for this chunk
            messages = []
            if system_message:
                messages.append(system_message)
            messages.extend(history_messages)
            messages.append(HumanMessage(content=chunk_prompt))
            
            # Get response for this chunk
            try:
                estimated_tokens = self._estimate_tokens(chunk_prompt)
                logger.info(f"Estimated tokens for chunk {i+1}: {estimated_tokens}")
                response = self.llm.invoke(messages)
                chunk_response = response.content if hasattr(response, 'content') else str(response)
                previous_responses.append(chunk_response)
                
                # Don't yield intermediate results - just log for debugging
                logger.info(f"Chunk {i+1}/{len(chunks)} processed successfully")
                
            except Exception as e:
                logger.error(f"Error processing chunk {i+1}: {e}")
                error_response = f"Error processing chunk {i+1}: {str(e)}"
                previous_responses.append(error_response)
        
        # Final consolidation
        if len(chunks) > 1:
            logger.info("Creating final consolidated response")
            
            final_prompt = self._create_final_consolidation_prompt(
                previous_responses, original_query
            )
            
            messages = []
            if system_message:
                messages.append(system_message)
            messages.extend(history_messages)
            messages.append(HumanMessage(content=final_prompt))
            
            try:
                # Stream the final response in real-time
                stream = self.llm.stream(messages)
                
                # Yield the response as it streams
                for chunk in stream:
                    if hasattr(chunk, 'content') and chunk.content:
                        yield chunk.content
                
            except Exception as e:
                logger.error(f"Error in final consolidation: {e}")
                yield f"❌ **Error in final consolidation:** {str(e)}"
        else:
            # Single chunk, stream the response
            try:
                messages = []
                if system_message:
                    messages.append(system_message)
                messages.extend(history_messages)
                messages.append(HumanMessage(content=original_query))
                
                stream = self.llm.stream(messages)
                for chunk in stream:
                    if hasattr(chunk, 'content') and chunk.content:
                        yield chunk.content
                        
            except Exception as e:
                logger.error(f"Error streaming single chunk response: {e}")
                yield f"❌ **Error:** {str(e)}"


def should_use_chunked_processing(
    content: str, 
    max_tokens: int, 
    existing_messages: List[BaseMessage]
) -> bool:
    """
    Determine if content should be processed in chunks.
    
    Args:
        content: The content to check
        max_tokens: Maximum allowed tokens
        existing_messages: Existing messages in the conversation
        
    Returns:
        True if chunked processing should be used
    """
    try:
        # Get tokenizer for estimation
        tokenizer = get_tokenizer(model_name="gpt-4", provider_type="openai")
        
        # Estimate tokens for content
        content_tokens = len(tokenizer.encode(content))
        logger.debug(f"Content tokens: {content_tokens}")
        
        # Estimate tokens for existing messages
        existing_tokens = sum(
            check_message_tokens(msg, tokenizer.encode) for msg in existing_messages
        )
        
        # Reserve tokens for response and safety buffer
        reserved_tokens = 2000
        
        total_estimated = content_tokens + existing_tokens + reserved_tokens
        
        logger.info(f"Token estimation - Content: {content_tokens}, Existing: {existing_tokens}, Total: {total_estimated}, Max: {max_tokens}")
        
        return total_estimated > max_tokens
        
    except Exception as e:
        logger.error(f"Error estimating tokens for chunked processing: {e}")
        # Conservative approach - use chunking if content is very large
        return len(content) > 50000  # 50KB threshold 