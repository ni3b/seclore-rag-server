#!/usr/bin/env python3
"""
Test script to verify that uploaded files are included in search tool responses.
"""

import json
from unittest.mock import Mock, MagicMock

from onyx.file_store.models import InMemoryChatFile, ChatFileType
from onyx.tools.tool_implementations.search.search_tool import SearchTool
from onyx.tools.models import ToolResponse
from onyx.tools.tool_implementations.search_like_tool_utils import FINAL_CONTEXT_DOCUMENTS_ID


def test_search_tool_with_files():
    """Test that SearchTool includes uploaded files in its response"""
    
    # Create a mock uploaded file
    test_file_content = b"This is a test file content for search tool testing."
    mock_file = Mock(spec=InMemoryChatFile)
    mock_file.file_type = ChatFileType.PLAIN_TEXT
    mock_file.filename = "test.txt"
    mock_file.content = test_file_content
    mock_file.to_base64.return_value = "base64encodedcontent"
    
    # Create a mock SearchTool instance
    search_tool = Mock(spec=SearchTool)
    search_tool._uploaded_files = [mock_file]
    
    # Create mock final context docs response
    mock_final_docs_response = Mock(spec=ToolResponse)
    mock_final_docs_response.id = FINAL_CONTEXT_DOCUMENTS_ID
    mock_final_docs_response.response = []  # Empty search results for simplicity
    
    # Test the build_tool_message_content method
    from onyx.tools.tool_implementations.search.search_tool import SearchTool
    
    # Create a real SearchTool instance with minimal setup
    real_search_tool = SearchTool(
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
        uploaded_files=[mock_file]
    )
    
    # Call the method
    result = real_search_tool.build_tool_message_content(mock_final_docs_response)
    
    # Parse the JSON result
    result_data = json.loads(result)
    
    # Verify that uploaded files are included
    assert "uploaded_files" in result_data, "Uploaded files should be included in response"
    assert len(result_data["uploaded_files"]) == 1, "Should have one uploaded file"
    
    file_data = result_data["uploaded_files"][0]
    assert file_data["filename"] == "test.txt", "Filename should match"
    assert "This is a test file content" in file_data["content"], "File content should be included"
    
    print("✅ Test passed: Search tool includes uploaded files in response")
    print(f"Response: {json.dumps(result_data, indent=2)}")


if __name__ == "__main__":
    test_search_tool_with_files() 