#!/usr/bin/env python3
"""
Test script for enhanced web connector with embedded image extraction.
This script tests the new functionality to extract and process images from HTML pages.
"""

import sys
import os
import io
from typing import List

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from onyx.connectors.web.connector import WebConnector, extract_images_from_html, process_embedded_image
from bs4 import BeautifulSoup
import requests

def test_image_extraction_from_html():
    """Test extracting images from HTML content."""
    print("=== Testing Image Extraction from HTML ===")
    
    # Sample HTML with various image types
    html_content = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Test Page with Images</h1>
        <img src="https://example.com/image1.jpg" alt="Test Image 1" title="Image Title 1" width="100" height="200" class="main-image" id="img1">
        <img src="/relative/path/image2.png" alt="Relative Image" class="thumb">
        <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt="Data URL Image">
        <img src="https://example.com/logo.svg" alt="SVG Logo">
        <img src="not-an-image.txt" alt="Invalid Image">
        <img alt="No src attribute">
    </body>
    </html>
    """
    
    soup = BeautifulSoup(html_content, "html.parser")
    base_url = "https://example.com/test-page"
    
    images = extract_images_from_html(soup, base_url)
    
    print(f"  Found {len(images)} valid images:")
    for i, img in enumerate(images, 1):
        print(f"    {i}. URL: {img['url']}")
        print(f"       Alt: {img['alt']}")
        print(f"       Title: {img['title']}")
        print(f"       Class: {img['class']}")
        print(f"       ID: {img['id']}")
        print()
    
    return images

def test_web_connector_with_image_extraction():
    """Test the enhanced web connector with a real webpage."""
    print("=== Testing Enhanced Web Connector ===")
    
    # Test with a simple webpage that likely has images
    test_url = "https://httpbin.org/html"  # Simple test page
    
    try:
        connector = WebConnector(
            base_url=test_url,
            web_connector_type="single"
        )
        
        print(f"  Testing with URL: {test_url}")
        
        # Get the first batch of documents
        document_batches = connector.load_from_state()
        first_batch = next(document_batches)
        
        print(f"  Indexed {len(first_batch)} documents:")
        
        for i, doc in enumerate(first_batch, 1):
            print(f"    {i}. ID: {doc.id}")
            print(f"       Semantic ID: {doc.semantic_identifier}")
            print(f"       Source: {doc.source}")
            print(f"       Text length: {len(doc.sections[0].text) if doc.sections else 0} chars")
            
            # Check if it's an embedded image
            if doc.id.startswith("embedded_image:"):
                print(f"       📸 EMBEDDED IMAGE DETECTED!")
                print(f"       Image URL: {doc.metadata.get('image_url', 'N/A')}")
                print(f"       Source Page: {doc.metadata.get('source_page_url', 'N/A')}")
                print(f"       Alt Text: {doc.metadata.get('html_alt', 'N/A')}")
                print(f"       Has OCR: {doc.metadata.get('has_ocr_text', 'N/A')}")
                print(f"       Has Description: {doc.metadata.get('has_description', 'N/A')}")
                print(f"       Has Embedding: {doc.metadata.get('has_image_embedding', 'N/A')}")
            
            print()
        
        return first_batch
        
    except Exception as e:
        print(f"  Error testing web connector: {e}")
        return []

def test_seclore_help_center():
    """Test with the actual Seclore help center URL."""
    print("=== Testing Seclore Help Center URL ===")
    
    seclore_url = "https://irm.seclore.com/policyserver/portal/pages/help/en/eum/default.htm"
    
    try:
        connector = WebConnector(
            base_url=seclore_url,
            web_connector_type="single"
        )
        
        print(f"  Testing with Seclore URL: {seclore_url}")
        
        # Get the first batch of documents
        document_batches = connector.load_from_state()
        first_batch = next(document_batches)
        
        print(f"  Indexed {len(first_batch)} documents:")
        
        main_page_count = 0
        embedded_image_count = 0
        
        for i, doc in enumerate(first_batch, 1):
            print(f"    {i}. ID: {doc.id}")
            print(f"       Semantic ID: {doc.semantic_identifier}")
            print(f"       Source: {doc.source}")
            
            if doc.id.startswith("embedded_image:"):
                embedded_image_count += 1
                print(f"       📸 EMBEDDED IMAGE!")
                print(f"       Image URL: {doc.metadata.get('image_url', 'N/A')}")
                print(f"       Alt Text: {doc.metadata.get('html_alt', 'N/A')}")
                print(f"       Has OCR: {doc.metadata.get('has_ocr_text', 'N/A')}")
                print(f"       Has Description: {doc.metadata.get('has_description', 'N/A')}")
            else:
                main_page_count += 1
                print(f"       📄 MAIN PAGE")
            
            print()
        
        print(f"  Summary:")
        print(f"    Main pages: {main_page_count}")
        print(f"    Embedded images: {embedded_image_count}")
        print(f"    Total documents: {len(first_batch)}")
        
        return first_batch
        
    except Exception as e:
        print(f"  Error testing Seclore help center: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_image_processing_fallback():
    """Test the image processing fallback mechanism."""
    print("=== Testing Image Processing Fallback ===")
    
    # Test with a simple image info
    image_info = {
        "url": "https://httpbin.org/image/png",  # Returns a simple PNG
        "alt": "Test PNG Image",
        "title": "HTTPBin PNG",
        "width": "100",
        "height": "100",
        "class": "test-image",
        "id": "test-png"
    }
    
    try:
        doc = process_embedded_image(
            image_info, 
            "https://httpbin.org/html", 
            "HTTPBin Test Page"
        )
        
        if doc:
            print(f"  ✅ Successfully processed test image:")
            print(f"     ID: {doc.id}")
            print(f"     Semantic ID: {doc.semantic_identifier}")
            print(f"     Text length: {len(doc.sections[0].text) if doc.sections else 0} chars")
            print(f"     Image URL: {doc.metadata.get('image_url', 'N/A')}")
            print(f"     Source Page: {doc.metadata.get('source_page_url', 'N/A')}")
            print(f"     Alt Text: {doc.metadata.get('html_alt', 'N/A')}")
            print(f"     Has OCR: {doc.metadata.get('has_ocr_text', 'N/A')}")
            print(f"     Has Description: {doc.metadata.get('has_description', 'N/A')}")
            print(f"     Has Embedding: {doc.metadata.get('has_image_embedding', 'N/A')}")
        else:
            print(f"  ❌ Failed to process test image")
            
    except Exception as e:
        print(f"  Error in image processing test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run all tests."""
    print("🚀 Testing Enhanced Web Connector with Embedded Image Extraction\n")
    
    # Test 1: HTML parsing
    test_image_extraction_from_html()
    print()
    
    # Test 2: Image processing
    test_image_processing_fallback()
    print()
    
    # Test 3: Simple web page
    test_web_connector_with_image_extraction()
    print()
    
    # Test 4: Seclore help center
    test_seclore_help_center()
    print()
    
    print("✅ All tests completed!")

if __name__ == "__main__":
    main() 