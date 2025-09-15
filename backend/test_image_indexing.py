#!/usr/bin/env python3
"""
Test script for comprehensive image indexing functionality.
Tests OCR, Claude Sonnet 4 descriptions, and embeddings.
"""

import io
import os
from pathlib import Path

def test_image_extensions():
    """Test that image file extensions are properly recognized."""
    print("=== Testing Image Extension Recognition ===")
    
    from onyx.file_processing.extract_file_text import (
        get_file_ext, is_image_file_extension, is_valid_file_ext, IMAGE_FILE_EXTENSIONS
    )
    
    test_files = [
        "test.jpg", "test.jpeg", "test.png", "test.gif", 
        "test.bmp", "test.tiff", "test.webp", "test.svg",
        "test.avif", "test.heic"
    ]
    
    for file_name in test_files:
        ext = get_file_ext(file_name)
        is_image = is_image_file_extension(file_name)
        is_valid = is_valid_file_ext(ext)
        print(f"  {file_name}: extension={ext}, is_image={is_image}, is_valid={is_valid}")
    
    print(f"  Supported image extensions: {IMAGE_FILE_EXTENSIONS}")
    print()


def test_comprehensive_processing():
    """Test comprehensive image processing."""
    print("=== Testing Comprehensive Image Processing ===")
    
    from onyx.file_processing.extract_file_text import process_image_comprehensive
    
    # Create a mock image file
    mock_image_data = b"mock image data for testing"
    mock_file = io.BytesIO(mock_image_data)
    
    try:
        combined_text, metadata = process_image_comprehensive(mock_file, "test.jpg")
        print(f"  Combined text: '{combined_text}'")
        print(f"  Has OCR text: {metadata.get('has_ocr_text', False)}")
        print(f"  Has description: {metadata.get('has_description', False)}")
        print(f"  Vision model: {metadata.get('vision_model', 'none')}")
        print(f"  Processing method: {metadata.get('processing_method', 'unknown')}")
        
    except Exception as e:
        print(f"  Expected error (mock data): {e}")
    
    print()


def test_full_indexing():
    """Test full image indexing with embeddings."""
    print("=== Testing Full Image Indexing ===")
    
    from onyx.file_processing.image_processing import process_image_for_indexing
    
    # Create a mock image file
    mock_image_data = b"mock image data for testing"
    mock_file = io.BytesIO(mock_image_data)
    
    try:
        result = process_image_for_indexing(mock_file, "test.jpg")
        
        print(f"  Text: '{result.get('text', '')}'")
        print(f"  Has embedding: {result.get('has_embedding', False)}")
        
        metadata = result.get('metadata', {})
        print(f"  Vision model: {metadata.get('vision_model', 'none')}")
        print(f"  Embedding model: {metadata.get('embedding_model', 'none')}")
        print(f"  Embedding dimension: {metadata.get('embedding_dim', 0)}")
        print(f"  Has image embedding: {metadata.get('has_image_embedding', False)}")
        
    except Exception as e:
        print(f"  Expected error (mock data): {e}")
    
    print()


def test_file_connector():
    """Test file connector integration."""
    print("=== Testing File Connector Integration ===")
    
    try:
        from onyx.connectors.file.connector import _process_file
        from onyx.file_processing.extract_file_text import is_image_file_extension
        
        # Create a mock image file
        mock_image_data = b"mock image data for testing"
        mock_file = io.BytesIO(mock_image_data)
        
        # Test if image files are recognized
        test_filename = "test_image.jpg"
        is_image = is_image_file_extension(test_filename)
        print(f"  File '{test_filename}' recognized as image: {is_image}")
        
        # Test processing (will fail with mock data but shows the flow)
        try:
            documents = _process_file(test_filename, mock_file, {})
            print(f"  Processed {len(documents)} documents")
        except Exception as e:
            print(f"  Expected processing error (mock data): {e}")
            
    except Exception as e:
        print(f"  Integration test error: {e}")
    
    print()


def test_web_connector():
    """Test web connector integration."""
    print("=== Testing Web Connector Integration ===")
    
    try:
        from onyx.connectors.web.connector import is_image_file_extension
        
        # Test image detection for web URLs
        test_urls = [
            "https://example.com/image.jpg",
            "https://example.com/photo.png",
            "https://example.com/document.pdf",
            "https://example.com/page.html"
        ]
        
        for url in test_urls:
            file_extension = url.split(".")[-1].lower()
            is_image = is_image_file_extension(f"dummy.{file_extension}")
            print(f"  URL '{url}' -> extension '{file_extension}' -> is_image: {is_image}")
            
    except Exception as e:
        print(f"  Web connector test error: {e}")
    
    print()


def main():
    """Run all tests."""
    print("=== Image Indexing Test Suite ===\n")
    
    test_image_extensions()
    test_comprehensive_processing()
    test_full_indexing()
    test_file_connector()
    test_web_connector()
    
    print("=== Test Complete ===")
    print("\nNotes:")
    print("- For full functionality, ensure UNSTRUCTURED_API_KEY is set for OCR")
    print("- Claude Sonnet 4 should be configured as the default LLM for image descriptions")
    print("- For image embeddings, install: pip install sentence-transformers torch transformers pillow")
    print("- Mock data tests show the processing flow but won't extract real content")


if __name__ == "__main__":
    main() 