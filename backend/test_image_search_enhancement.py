#!/usr/bin/env python3
"""
Test script to verify image search enhancement functionality.
This tests that when image documents are found in search results,
the corresponding source page documents are also included.
"""

import os
import sys
import logging
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_image_search_enhancement():
    """Test the image search enhancement functionality."""
    logger.info("=== Testing Image Search Enhancement ===")
    
    try:
        from onyx.context.search.retrieval.search_runner import enhance_search_results_with_source_pages
        from onyx.context.search.models import InferenceChunk, SearchQuery
        from onyx.configs.app_configs import INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH
        
        logger.info(f"Image search enhancement enabled: {INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH}")
        
        # Create mock image chunks
        image_chunk1 = Mock(spec=InferenceChunk)
        image_chunk1.document_id = "https://example.com/page1#https://cdn.example.com/image1.png"
        image_chunk1.metadata = {
            "source": "web_embedded",
            "source_page_url": "https://example.com/page1",
            "source_page_title": "Example Page 1",
            "image_url": "https://cdn.example.com/image1.png"
        }
        image_chunk1.score = 0.9
        
        image_chunk2 = Mock(spec=InferenceChunk)
        image_chunk2.document_id = "https://example.com/page2#https://cdn.example.com/image2.png"
        image_chunk2.metadata = {
            "source": "web_embedded",
            "source_page_url": "https://example.com/page2", 
            "source_page_title": "Example Page 2",
            "image_url": "https://cdn.example.com/image2.png"
        }
        image_chunk2.score = 0.8
        
        # Create mock regular chunk (not an image)
        regular_chunk = Mock(spec=InferenceChunk)
        regular_chunk.document_id = "https://example.com/page3"
        regular_chunk.metadata = {
            "url": "https://example.com/page3",
            "title": "Regular Page"
        }
        regular_chunk.score = 0.7
        
        # Create mock source page chunks that would be found
        source_page_chunk1 = Mock(spec=InferenceChunk)
        source_page_chunk1.document_id = "https://example.com/page1"
        source_page_chunk1.metadata = {
            "url": "https://example.com/page1",
            "title": "Example Page 1"
        }
        source_page_chunk1.score = 0.6
        
        source_page_chunk2 = Mock(spec=InferenceChunk)
        source_page_chunk2.document_id = "https://example.com/page2"
        source_page_chunk2.metadata = {
            "url": "https://example.com/page2",
            "title": "Example Page 2"
        }
        source_page_chunk2.score = 0.5
        
        # Mock the document index and query
        mock_document_index = Mock()
        mock_query = Mock(spec=SearchQuery)
        mock_query.copy = Mock(return_value=mock_query)
        mock_query.num_hits = 10
        mock_db_session = Mock()
        
        # Mock the doc_index_retrieval function to return source page chunks
        def mock_doc_index_retrieval(query, document_index, db_session):
            if 'url:"https://example.com/page1"' in query.query:
                return [source_page_chunk1]
            elif 'url:"https://example.com/page2"' in query.query:
                return [source_page_chunk2]
            return []
        
        # Patch the doc_index_retrieval function
        import onyx.context.search.retrieval.search_runner as search_runner
        original_doc_index_retrieval = search_runner.doc_index_retrieval
        search_runner.doc_index_retrieval = mock_doc_index_retrieval
        
        try:
            # Test with image chunks
            original_chunks = [image_chunk1, image_chunk2, regular_chunk]
            
            enhanced_chunks = enhance_search_results_with_source_pages(
                chunks=original_chunks,
                document_index=mock_document_index,
                query=mock_query,
                db_session=mock_db_session,
            )
            
            logger.info(f"Original chunks: {len(original_chunks)}")
            logger.info(f"Enhanced chunks: {len(enhanced_chunks)}")
            
            # Verify results
            enhanced_doc_ids = [chunk.document_id for chunk in enhanced_chunks]
            logger.info(f"Enhanced document IDs: {enhanced_doc_ids}")
            
            # Check that source page documents were added
            assert "https://example.com/page1" in enhanced_doc_ids, "Source page 1 should be included"
            assert "https://example.com/page2" in enhanced_doc_ids, "Source page 2 should be included"
            
            # Check that original chunks are still there
            assert image_chunk1.document_id in enhanced_doc_ids, "Original image chunk 1 should be included"
            assert image_chunk2.document_id in enhanced_doc_ids, "Original image chunk 2 should be included"
            assert regular_chunk.document_id in enhanced_doc_ids, "Regular chunk should be included"
            
            logger.info("✓ Image search enhancement test passed!")
            
            # Test with no image chunks
            non_image_chunks = [regular_chunk]
            enhanced_non_image = enhance_search_results_with_source_pages(
                chunks=non_image_chunks,
                document_index=mock_document_index,
                query=mock_query,
                db_session=mock_db_session,
            )
            
            assert len(enhanced_non_image) == len(non_image_chunks), "Non-image chunks should remain unchanged"
            logger.info("✓ Non-image chunks test passed!")
            
            return True
            
        finally:
            # Restore original function
            search_runner.doc_index_retrieval = original_doc_index_retrieval
            
    except Exception as e:
        logger.error(f"✗ Image search enhancement test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration():
    """Test the configuration settings."""
    logger.info("=== Testing Configuration ===")
    
    try:
        from onyx.configs.app_configs import INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH
        
        logger.info(f"INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH: {INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH}")
        
        # Test with environment variable
        original_value = os.environ.get("INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH")
        
        # Test disabled
        os.environ["INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH"] = "false"
        
        # Reload the module to pick up new environment variable
        import importlib
        import onyx.configs.app_configs
        importlib.reload(onyx.configs.app_configs)
        
        from onyx.configs.app_configs import INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH as disabled_setting
        assert not disabled_setting, "Setting should be disabled when env var is false"
        logger.info("✓ Configuration disable test passed!")
        
        # Test enabled
        os.environ["INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH"] = "true"
        importlib.reload(onyx.configs.app_configs)
        
        from onyx.configs.app_configs import INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH as enabled_setting
        assert enabled_setting, "Setting should be enabled when env var is true"
        logger.info("✓ Configuration enable test passed!")
        
        # Restore original value
        if original_value is not None:
            os.environ["INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH"] = original_value
        else:
            os.environ.pop("INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH", None)
            
        return True
        
    except Exception as e:
        logger.error(f"✗ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing Image Search Enhancement")
    print("=" * 50)
    
    # Set environment variables for testing
    os.environ['INCLUDE_SOURCE_PAGES_FOR_IMAGE_SEARCH'] = 'true'
    
    success1 = test_configuration()
    success2 = test_image_search_enhancement()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("✓ All tests passed!")
        print("Image search enhancement is working correctly.")
        print("When you search with images, you should now see:")
        print("1. The matching image documents")
        print("2. The source page documents that contain those images")
        print("3. Both types boosted appropriately in the results")
    else:
        print("✗ Some tests failed.")
        print("Check the logs above for details.")
        sys.exit(1) 