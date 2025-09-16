# Cross-Region Bedrock Inference Setup

This document outlines the steps taken to enable cross-region inference for Claude Sonnet 4 in the Seclore RAG server.

## ✅ **Completed Steps**

### 1. **Verified Inference Profile Availability**
- ✅ Checked available inference profiles in `us-east-1`
- ✅ Confirmed `us.anthropic.claude-sonnet-4-20250514-v1:0` is ACTIVE
- ✅ Profile routes between `us-east-1`, `us-east-2`, and `us-west-2`

### 2. **Updated Model Configuration**
- ✅ Modified `backend/onyx/llm/llm_provider_options.py`
- ✅ Changed default Bedrock model to use cross-region inference profile
- ✅ Updated both `default_model` and `default_fast_model`

### 3. **Created Environment Configuration**
- ✅ Created `deployment/docker_compose/env.cross-region-bedrock`
- ✅ Configured AWS region settings
- ✅ Added cross-region inference flags

### 4. **Created Test Script**
- ✅ Created `test_cross_region_bedrock.py`
- ✅ Includes inference profile verification
- ✅ Tests actual cross-region API calls

## 🔧 **Configuration Changes**

### **Model Configuration Update**
```python
# Before
default_model="anthropic.claude-3-5-sonnet-20241022-v2:0"

# After  
default_model="us.anthropic.claude-sonnet-4-20250514-v1:0"
```

### **Environment Variables**
```bash
# Cross-region inference configuration
AWS_REGION_NAME=us-east-1
BEDROCK_DEFAULT_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0
ENABLE_CROSS_REGION_INFERENCE=true
```

## 🌐 **How Cross-Region Inference Works**

### **Routing Logic**
1. **Primary Region**: `us-east-1` (your configured region)
2. **Fallback Regions**: `us-east-2`, `us-west-2`
3. **Automatic Routing**: Based on capacity and latency

### **Inference Profile Details**
- **Name**: "US Claude Sonnet 4"
- **Description**: "Routes requests to Claude Sonnet 4 in us-east-1, us-east-2 and us-west-2"
- **Status**: ACTIVE
- **Type**: SYSTEM_DEFINED

## 🚀 **Testing**

### **Run the Test Script**
```bash
python test_cross_region_bedrock.py
```

### **Expected Output**
```
🚀 Testing Cross-Region Bedrock Inference
==================================================

📋 Inference Profile Details:
Name: US Claude Sonnet 4
Description: Routes requests to Claude Sonnet 4 in us-east-1, us-east-2 and us-west-2
Status: ACTIVE
Type: SYSTEM_DEFINED

🌍 Available Regions:
  - us-east-1
  - us-east-2
  - us-west-2

==================================================
Testing cross-region inference at 2025-01-27 10:30:00
Model: us.anthropic.claude-sonnet-4-20250514-v1:0
Region: us-east-1
Prompt: Hello! Please respond with a short message...
--------------------------------------------------
✅ SUCCESS: Cross-region inference working!
Response: Hello! I received your request successfully.
Model ARN: arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0
📍 Local region routing (us-east-1)

✅ Cross-region inference is properly configured!
```

## 📊 **Monitoring Cross-Region Usage**

### **CloudTrail Logs**
Monitor these events to see cross-region routing:
- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`

### **CloudWatch Metrics**
- `Invocations` - Total API calls
- `ModelLatency` - Response time
- `InvocationsPerSecond` - Throughput

## 🔍 **Troubleshooting**

### **Common Issues**

1. **Model Not Found Error**
   ```bash
   # Check if model is available in your region
   aws bedrock list-foundation-models --region us-east-1
   ```

2. **Permission Denied**
   ```bash
   # Verify IAM permissions
   aws iam get-user
   aws sts get-caller-identity
   ```

3. **Cross-Region Not Working**
   ```bash
   # Check inference profile status
   aws bedrock get-inference-profile --inference-profile-id us.anthropic.claude-sonnet-4-20250514-v1:0
   ```

## 📈 **Benefits**

### **Performance**
- **Reduced Latency**: Automatic routing to closest region
- **Higher Availability**: Fallback to multiple regions
- **Load Balancing**: Distributed across regions

### **Reliability**
- **Fault Tolerance**: If one region fails, others continue
- **Capacity Management**: Automatic scaling across regions
- **Disaster Recovery**: Built-in regional redundancy

## 🔄 **Next Steps**

1. **Deploy Changes**: Rebuild Docker containers with new configuration
2. **Monitor Performance**: Track latency and throughput improvements
3. **Update Documentation**: Inform team about cross-region capabilities
4. **Set Up Alerts**: Monitor for cross-region routing events

## 📝 **Notes**

- Cross-region inference is **reactive** - it only routes when needed
- **No additional cost** for cross-region inference
- **Automatic fallback** to local region when possible
- **Transparent to applications** - no code changes needed beyond model ID 