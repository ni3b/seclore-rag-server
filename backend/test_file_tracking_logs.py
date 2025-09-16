#!/usr/bin/env python3
"""
Test script to verify file tracking logs in query rephrase and search tool.
"""

import logging
from unittest.mock import Mock, MagicMock
from onyx.file_store.models import InMemoryChatFile, ChatFileType
from onyx.configs.constants import MessageType
from onyx.llm.models import PreviousMessage
from onyx.secondary_llm_flows.query_expansion import history_based_query_rephrase, _build_file_content_for_rephrase

# Set up logging to see our tracking logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_file_tracking_logs():
    """Test that file tracking logs are working correctly"""
    
    print("=" * 50)
    print("Testing File Tracking Logs")
    print("=" * 50)
    
    # Create mock files
    test_file_1 = Mock(spec=InMemoryChatFile)
    test_file_1.file_type = ChatFileType.PLAIN_TEXT
    test_file_1.filename = "test1.txt"
    test_file_1.content = b"This is the first test file content."
    
    test_file_2 = Mock(spec=InMemoryChatFile)
    test_file_2.file_type = ChatFileType.CSV
    test_file_2.filename = "test2.csv"
    test_file_2.content = b"name,age,city\nJohn,25,NYC\nJane,30,LA"
    
    uploaded_files = [test_file_1, test_file_2]
    
    print("\n1. Testing _build_file_content_for_rephrase function:")
    file_content = _build_file_content_for_rephrase(uploaded_files)
    print(f"File content built: {len(file_content)} chars")
    print(f"Preview: {file_content[:100]}...")
    
    print("\n2. Testing history_based_query_rephrase function:")
    
    # Create mock history
    mock_history = [
        Mock(spec=PreviousMessage),
        Mock(spec=PreviousMessage)
    ]
    mock_history[0].message_type = MessageType.USER
    mock_history[0].files = uploaded_files
    mock_history[0].message = "What is the content of these files?"
    
    mock_history[1].message_type = MessageType.ASSISTANT
    mock_history[1].files = []
    mock_history[1].message = "I can help you analyze the files."
    
    # Mock LLM
    mock_llm = Mock()
    mock_llm.invoke.return_value = Mock()
    mock_llm.invoke.return_value.content = "Rephrased query with file context"
    
    # Mock prompt config
    mock_prompt_config = Mock()
    mock_prompt_config.history_query_rephrase = "Rephrase the query considering the context"
    
    try:
        # This should trigger our file tracking logs
        rephrased_query = history_based_query_rephrase(
            query="What information is in the uploaded files?",
            history=mock_history,
            llm=mock_llm,
            note="Test note",
            uploaded_files=uploaded_files
        )
        print(f"Rephrased query: {rephrased_query}")
    except Exception as e:
        print(f"Error in query rephrase: {e}")
    
    print("\n3. Testing SearchTool file tracking:")
    
    # Import and test SearchTool
    from onyx.tools.tool_implementations.search.search_tool import SearchTool
    from onyx.tools.models import ToolResponse
    from onyx.tools.tool_implementations.search_like_tool_utils import FINAL_CONTEXT_DOCUMENTS_ID
    
    # Create a mock SearchTool
    search_tool = SearchTool(
        db_session=Mock(),
        user=None,
        persona=Mock(),
        retrieval_options=None,
        prompt_config=Mock(),
        llm=Mock(),
        fast_llm=Mock(),
        pruning_config=Mock(),
        answer_style_config=Mock(),
        evaluation_type=Mock(),
        uploaded_files=uploaded_files
    )
    
    # Test get_args_for_non_tool_calling_llm
    try:
        args = search_tool.get_args_for_non_tool_calling_llm(
            query="What is in the files?",
            history=mock_history,
            llm=mock_llm,
            prompt_config=mock_prompt_config
        )
        print(f"Search tool args: {args}")
    except Exception as e:
        print(f"Error in search tool args: {e}")
    
    # Test build_tool_message_content
    mock_response = Mock(spec=ToolResponse)
    mock_response.id = FINAL_CONTEXT_DOCUMENTS_ID
    mock_response.response = []  # Empty search results
    
    try:
        tool_response = search_tool.build_tool_message_content(mock_response)
        print(f"Tool response preview: {tool_response[:200]}...")
    except Exception as e:
        print(f"Error in tool response: {e}")
    
    print("\n" + "=" * 50)
    print("File tracking test completed!")
    print("=" * 50)

if __name__ == "__main__":
    test_file_tracking_logs() 