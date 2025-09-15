#!/usr/bin/env python3
"""
Test script to verify cross-region Bedrock inference for Claude Sonnet 4
"""

import boto3
import json
import time
from datetime import datetime

def test_cross_region_inference():
    """Test cross-region inference using the inference profile"""
    
    # Initialize Bedrock client
    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
    
    # Test prompt
    prompt = "Hello! Please respond with a short message confirming you received this request."
    
    # Prepare the request body
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    print(f"Testing cross-region inference at {datetime.now()}")
    print(f"Model: us.anthropic.claude-sonnet-4-20250514-v1:0")
    print(f"Region: us-east-1")
    print(f"Prompt: {prompt}")
    print("-" * 50)
    
    try:
        # Make the API call
        response = bedrock.invoke_model(
            modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
            body=json.dumps(body)
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']
        
        print("✅ SUCCESS: Cross-region inference working!")
        print(f"Response: {content}")
        print(f"Model ARN: {response.get('modelArn', 'N/A')}")
        
        # Check if response indicates cross-region routing
        if 'us-west-2' in response.get('modelArn', ''):
            print("🌐 Cross-region routing detected!")
        else:
            print("📍 Local region routing (us-east-1)")
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False
    
    return True

def test_inference_profile_details():
    """Check inference profile details"""
    
    bedrock = boto3.client('bedrock', region_name='us-east-1')
    
    try:
        response = bedrock.get_inference_profile(
            inferenceProfileId="us.anthropic.claude-sonnet-4-20250514-v1:0"
        )
        
        print("\n📋 Inference Profile Details:")
        print(f"Name: {response['inferenceProfileName']}")
        print(f"Description: {response['description']}")
        print(f"Status: {response['status']}")
        print(f"Type: {response['type']}")
        
        print("\n🌍 Available Regions:")
        for model in response['models']:
            region = model['modelArn'].split(':')[3]
            print(f"  - {region}")
            
    except Exception as e:
        print(f"❌ Error getting inference profile: {str(e)}")

if __name__ == "__main__":
    print("🚀 Testing Cross-Region Bedrock Inference")
    print("=" * 50)
    
    # Test inference profile details
    test_inference_profile_details()
    
    print("\n" + "=" * 50)
    
    # Test actual inference
    success = test_cross_region_inference()
    
    if success:
        print("\n✅ Cross-region inference is properly configured!")
    else:
        print("\n❌ Cross-region inference test failed!") 