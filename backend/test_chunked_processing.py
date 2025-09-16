#!/usr/bin/env python3
"""
Test script for chunked processing functionality.
This demonstrates how large content is automatically split and processed in chunks.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onyx.chat.chunked_processing import ChunkedContentProcessor, should_use_chunked_processing
from onyx.llm.chat_llm import DefaultMultiLLM
from langchain_core.messages import HumanMessage, SystemMessage
from onyx.utils.logger import setup_logger

logger = setup_logger()

def test_chunked_processing():
    """Test the chunked processing with a sample large content."""
    
    # Create a mock LLM (you'll need to configure this with your actual LLM settings)
    llm = DefaultMultiLLM(
        api_key="test-key",  # Replace with actual key
        timeout=30,
        model_provider="openai",
        model_name="gpt-4",
        temperature=0.7
    )
    
    # Create large sample content
    large_content = """
FILES:

DOCUMENT: sample_log.log
```
2025-01-18 10:00:01 INFO Starting application
2025-01-18 10:00:02 DEBUG Initializing database connection
2025-01-18 10:00:03 INFO Database connection established
2025-01-18 10:00:04 DEBUG Loading configuration
2025-01-18 10:00:05 INFO Configuration loaded successfully
2025-01-18 10:00:06 DEBUG Starting web server
2025-01-18 10:00:07 INFO Web server started on port 8080
2025-01-18 10:00:08 INFO Application ready to serve requests
""" * 100  # Repeat to make it large
    
    original_query = "Analyze this log file and tell me what the application is doing during startup"
    
    # Test if chunked processing should be used
    max_tokens = 10000  # Simulate a smaller token limit
    history_messages = [
        SystemMessage(content="You are a helpful log analysis assistant.")
    ]
    
    should_chunk = should_use_chunked_processing(large_content, max_tokens, history_messages)
    print(f"Should use chunked processing: {should_chunk}")
    
    if should_chunk:
        processor = ChunkedContentProcessor(llm, max_tokens)
        
        print("\n=== CHUNKED PROCESSING DEMO ===")
        print("Processing large content in chunks...")
        
        for response in processor.process_large_content(
            content=large_content,
            original_query=original_query,
            history_messages=[],
            system_message=SystemMessage(content="You are a helpful log analysis assistant.")
        ):
            print(response)
            print("\n" + "="*50 + "\n")
    else:
        print("Content is small enough for normal processing")

if __name__ == "__main__":
    print("Testing Chunked Processing...")
    test_chunked_processing() 