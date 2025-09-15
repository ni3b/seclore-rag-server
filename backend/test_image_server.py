#!/usr/bin/env python3
"""
Test script for Image Model Server
"""

import asyncio
import base64
import io
from PIL import Image, ImageDraw
import httpx
import os

# Configuration
IMAGE_MODEL_SERVER_URL = "http://localhost:9001"


async def test_health_check():
    """Test health check endpoint"""
    print("Testing health check...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{IMAGE_MODEL_SERVER_URL}/api/health")
            print(f"Health check status: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Health check failed: {str(e)}")
            return False


async def test_status():
    """Test status endpoint"""
    print("Testing status endpoint...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{IMAGE_MODEL_SERVER_URL}/api/status")
            print(f"Status response: {response.json()}")
            return True
        except Exception as e:
            print(f"Status check failed: {str(e)}")
            return False


def create_test_image():
    """Create a simple test image with text"""
    # Create a 400x200 white image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    
    # Add some text
    draw.text((10, 10), "Hello World!", fill='black')
    draw.text((10, 50), "This is a test image", fill='blue')
    draw.text((10, 90), "for OCR and vision", fill='red')
    
    # Add some shapes
    draw.rectangle([10, 130, 100, 180], outline='green', width=2)
    draw.ellipse([120, 130, 200, 180], outline='purple', width=2)
    
    # Convert to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()


async def test_ocr():
    """Test OCR endpoint"""
    print("Testing OCR endpoint...")
    
    # Create test image
    image_data = create_test_image()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "image_base64": image_base64,
        "file_name": "test_image.png"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{IMAGE_MODEL_SERVER_URL}/image/ocr",
                json=payload
            )
            result = response.json()
            print(f"OCR result: {result}")
            return True
        except Exception as e:
            print(f"OCR test failed: {str(e)}")
            return False


async def test_embedding():
    """Test embedding endpoint"""
    print("Testing embedding endpoint...")
    
    # Create test image
    image_data = create_test_image()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "image_base64": image_base64,
        "file_name": "test_image.png"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{IMAGE_MODEL_SERVER_URL}/image/embedding",
                json=payload
            )
            result = response.json()
            print(f"Embedding result: Model={result.get('model_name')}, Dim={len(result.get('embedding', []))}")
            return True
        except Exception as e:
            print(f"Embedding test failed: {str(e)}")
            return False


async def test_comprehensive():
    """Test comprehensive image processing"""
    print("Testing comprehensive image processing...")
    
    # Create test image
    image_data = create_test_image()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "image_base64": image_base64,
        "file_name": "test_image.png",
        "include_ocr": True,
        "include_description": False,  # Skip vision since it requires API key
        "include_embedding": True,
        "claude_api_key": None,
        "claude_provider": "anthropic",  # Can be "anthropic" or "bedrock"
        "claude_model": "claude-3-5-sonnet-20241022"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{IMAGE_MODEL_SERVER_URL}/image/process",
                json=payload
            )
            result = response.json()
            print(f"Comprehensive processing result:")
            print(f"  Text: {result.get('text', '')[:100]}...")
            print(f"  Has embedding: {result.get('has_embedding')}")
            print(f"  Processing steps: {result.get('metadata', {}).get('processing_steps', [])}")
            return True
        except Exception as e:
            print(f"Comprehensive test failed: {str(e)}")
            return False


async def test_vision_with_provider(provider: str = "anthropic"):
    """Test vision processing with specific provider"""
    print(f"Testing vision with {provider} provider...")
    
    # This test requires an API key - skip if not provided
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        print(f"Skipping {provider} vision test - no API key provided")
        return True
    
    # Create test image
    image_data = create_test_image()
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "image_base64": image_base64,
        "file_name": "test_image.png",
        "claude_api_key": api_key,
        "claude_provider": provider,
        "claude_model": "claude-3-5-sonnet-20241022"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{IMAGE_MODEL_SERVER_URL}/image/vision",
                json=payload
            )
            result = response.json()
            print(f"Vision result ({provider}): {result.get('description', '')[:100]}...")
            return True
        except Exception as e:
            print(f"Vision test with {provider} failed: {str(e)}")
            return False


async def main():
    """Run all tests"""
    print("=" * 50)
    print("Image Model Server Test Suite")
    print("=" * 50)
    
    tests = [
        ("Health Check", test_health_check),
        ("Status Check", test_status),
        ("OCR Test", test_ocr),
        ("Embedding Test", test_embedding),
        ("Comprehensive Test", test_comprehensive),
        ("Vision Test (Anthropic)", lambda: test_vision_with_provider("anthropic")),
        ("Vision Test (Bedrock)", lambda: test_vision_with_provider("bedrock")),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'-' * 30}")
        result = await test_func()
        results.append((test_name, result))
        print(f"{test_name}: {'PASS' if result else 'FAIL'}")
    
    print(f"\n{'=' * 50}")
    print("Test Results Summary:")
    print("=" * 50)
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name:.<30} {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\nOverall: {passed}/{total} tests passed")


if __name__ == "__main__":
    asyncio.run(main()) 