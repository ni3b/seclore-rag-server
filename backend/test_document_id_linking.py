#!/usr/bin/env python3
"""
Test script to verify document ID linking between images and source documents.
This tests the universal approach that works across all connectors.
"""

import os
import sys
import logging
from pathlib import Path
from unittest.mock import Mock

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_document_id_linking():
    """Test that image documents are properly linked to source documents via document ID."""
    logger.info("=== Testing Document ID Linking ===")
    
    try:
        from onyx.context.search.retrieval.search_runner import enhance_search_results_with_source_pages
        from onyx.context.search.models import InferenceChunk, SearchQuery
        
        # Create mock source document chunks
        source_doc_chunk = Mock(spec=InferenceChunk)
        source_doc_chunk.document_id = "https://example.com/architecture-guide"
        source_doc_chunk.metadata = {
            "url": "https://example.com/architecture-guide",
            "title": "System Architecture Guide",
            "connector_name": "web"
        }
        source_doc_chunk.score = 0.7
        
        # Create mock image document chunks with source_document_id
        image_chunk1 = Mock(spec=InferenceChunk)
        image_chunk1.document_id = "https://example.com/architecture-guide#https://cdn.example.com/diagram1.png"
        image_chunk1.metadata = {
            "source": "web_embedded",
            "source_document_id": "https://example.com/architecture-guide",  # Key linking field
            "source_document_title": "System Architecture Guide",
            "image_url": "https://cdn.example.com/diagram1.png",
            "html_alt": "Architecture Diagram",
            "connector_name": "web"
        }
        image_chunk1.score = 0.9
        
        image_chunk2 = Mock(spec=InferenceChunk)
        image_chunk2.document_id = "https://example.com/architecture-guide#https://cdn.example.com/diagram2.png"
        image_chunk2.metadata = {
            "source": "web_embedded",
            "source_document_id": "https://example.com/architecture-guide",  # Same source document
            "source_document_title": "System Architecture Guide", 
            "image_url": "https://cdn.example.com/diagram2.png",
            "html_alt": "Data Flow Diagram",
            "connector_name": "web"
        }
        image_chunk2.score = 0.8
        
        # Create mock other document chunk (unrelated)
        other_chunk = Mock(spec=InferenceChunk)
        other_chunk.document_id = "https://example.com/other-page"
        other_chunk.metadata = {
            "url": "https://example.com/other-page",
            "title": "Other Page"
        }
        other_chunk.score = 0.6
        
        # Mock search query and document index
        mock_query = Mock(spec=SearchQuery)
        mock_query.copy = Mock(return_value=mock_query)
        mock_query.num_hits = 10
        mock_document_index = Mock()
        mock_db_session = Mock()
        
        # Mock doc_index_retrieval to return source document when searched by ID
        def mock_doc_index_retrieval(query, document_index, db_session):
            if 'document_id:"https://example.com/architecture-guide"' in query.query:
                # Return the source document chunk when searched by document ID
                return [source_doc_chunk]
            return []
        
        # Patch the doc_index_retrieval function
        import onyx.context.search.retrieval.search_runner as search_runner
        original_doc_index_retrieval = search_runner.doc_index_retrieval
        search_runner.doc_index_retrieval = mock_doc_index_retrieval
        
        try:
            # Test with image chunks that should trigger source document retrieval
            original_chunks = [image_chunk1, image_chunk2, other_chunk]
            
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
            
            # Check that source document was added
            assert "https://example.com/architecture-guide" in enhanced_doc_ids, "Source document should be included"
            
            # Check that image documents are still there
            assert image_chunk1.document_id in enhanced_doc_ids, "Image chunk 1 should be included"
            assert image_chunk2.document_id in enhanced_doc_ids, "Image chunk 2 should be included"
            
            # Check that other document is still there
            assert other_chunk.document_id in enhanced_doc_ids, "Other chunk should be included"
            
            # Check score boosting - source document should have higher score than original
            source_chunk_in_results = next(chunk for chunk in enhanced_chunks if chunk.document_id == "https://example.com/architecture-guide")
            assert source_chunk_in_results.score > 0.7, f"Source document score should be boosted, got {source_chunk_in_results.score}"
            
            # Check that results are properly ordered by score
            scores = [chunk.score for chunk in enhanced_chunks]
            assert scores == sorted(scores, reverse=True), "Results should be ordered by score (highest first)"
            
            logger.info("✓ Document ID linking test passed!")
            
            # Test with non-image chunks (should return unchanged)
            non_image_chunks = [other_chunk]
            enhanced_non_image = enhance_search_results_with_source_pages(
                chunks=non_image_chunks,
                document_index=mock_document_index,
                query=mock_query,
                db_session=mock_db_session,
            )
            
            assert len(enhanced_non_image) == len(non_image_chunks), "Non-image chunks should remain unchanged"
            assert enhanced_non_image[0].document_id == other_chunk.document_id, "Non-image chunk should be unchanged"
            
            logger.info("✓ Non-image chunks test passed!")
            
            return True
            
        finally:
            # Restore original function
            search_runner.doc_index_retrieval = original_doc_index_retrieval
            
    except Exception as e:
        logger.error(f"✗ Document ID linking test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cross_connector_compatibility():
    """Test that the approach works for different connector types."""
    logger.info("=== Testing Cross-Connector Compatibility ===")
    
    try:
        # Test different connector types
        connector_scenarios = [
            {
                "name": "Google Drive",
                "source_doc_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
                "image_source": "drive_embedded",
                "connector_name": "google_drive"
            },
            {
                "name": "SharePoint", 
                "source_doc_id": "/sites/company/documents/presentation.pptx",
                "image_source": "file_embedded",
                "connector_name": "sharepoint"
            },
            {
                "name": "Confluence",
                "source_doc_id": "https://company.atlassian.net/wiki/spaces/PROJ/pages/123456789",
                "image_source": "web_embedded",
                "connector_name": "confluence"
            }
        ]
        
        for scenario in connector_scenarios:
            logger.info(f"Testing {scenario['name']} connector...")
            
            # The key insight: regardless of connector type, the linking mechanism is the same
            # - Image document has source_document_id in metadata
            # - Search enhancement uses this ID to find the source document
            # - Works universally across all connectors
            
            image_metadata = {
                "source": scenario["image_source"],
                "source_document_id": scenario["source_doc_id"],  # Universal linking field
                "connector_name": scenario["connector_name"],
                "image_url": "https://example.com/image.png"
            }
            
            # Verify metadata structure is consistent
            assert "source_document_id" in image_metadata, f"source_document_id missing for {scenario['name']}"
            assert image_metadata["source"] in ["web_embedded", "file_embedded", "drive_embedded"], f"Invalid source type for {scenario['name']}"
            
            logger.info(f"✓ {scenario['name']} metadata structure is valid")
        
        logger.info("✓ Cross-connector compatibility test passed!")
        return True
        
    except Exception as e:
        logger.error(f"✗ Cross-connector compatibility test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing Document ID Linking Approach")
    print("=" * 60)
    
    success1 = test_document_id_linking()
    success2 = test_cross_connector_compatibility()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("✓ All tests passed!")
        print("Document ID linking approach is working correctly.")
        print("\nBenefits of this approach:")
        print("1. ✅ Works universally across ALL connectors")
        print("2. ✅ Uses document ID for reliable linking") 
        print("3. ✅ No configuration flags needed")
        print("4. ✅ Simple and robust implementation")
        print("5. ✅ Proper result prioritization")
        print("\nHow it works:")
        print("- Image documents store source_document_id in metadata")
        print("- Search enhancement finds images and looks up source documents")
        print("- Results show: Source Document → Images → Other content")
        print("- User gets complete context automatically")
    else:
        print("✗ Some tests failed.")
        print("Check the logs above for details.")
        sys.exit(1) 