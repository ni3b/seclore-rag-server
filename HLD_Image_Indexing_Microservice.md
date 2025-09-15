# High-Level Design: Image Indexing Microservice

## 1. System Overview

### 1.1 Purpose
The Image Indexing Microservice enhances the Seclore RAG system with comprehensive image processing capabilities, including OCR text extraction, visual content understanding, and image embeddings for multi-modal search and retrieval.

### 1.2 Scope
- **In Scope**: Image processing, OCR, vision description, image embeddings, microservice architecture
- **Out of Scope**: Video processing, real-time streaming, image generation

### 1.3 Architecture Principles
- **Microservice Architecture**: Isolated, independently scalable service
- **API-First Design**: RESTful APIs for all interactions
- **Fault Tolerance**: Graceful degradation with fallback mechanisms
- **Performance**: Optimized for batch and real-time processing
- **Extensibility**: Pluggable model architecture

## 2. System Architecture

### 2.1 High-Level Architecture
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Seclore RAG System                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  Web Connector  │    │ File Connector  │    │SharePoint Conn. │        │
│  └─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘        │
│            │                      │                      │                │
│            └──────────────────────┼──────────────────────┘                │
│                                   │                                       │
│                          ┌────────▼────────┐                              │
│                          │ Image Client    │                              │
│                          │ (HTTP Client)   │                              │
│                          └────────┬────────┘                              │
└───────────────────────────────────┼────────────────────────────────────────┘
                                    │ HTTP/REST API
                                    │
┌───────────────────────────────────▼────────────────────────────────────────┐
│                     Image Model Server (Port 9001)                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐           │
│  │   OCR Module    │  │  Vision Module  │  │Embedding Module │           │
│  │                 │  │                 │  │                 │           │
│  │ • EasyOCR       │  │ • Claude Sonnet │  │ • CLIP Models   │           │
│  │ • Tesseract     │  │ • LiteLLM       │  │ • Transformers  │           │
│  │ • Text Extract  │  │ • Multi-Provider│  │ • Embeddings    │           │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘           │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Application                             │  │
│  │ • Async Request Handling                                           │  │
│  │ • Model Management & Lifecycle                                     │  │
│  │ • Health Checks & Monitoring                                       │  │
│  │ • Error Handling & Logging                                         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Architecture

#### 2.2.1 Image Model Server Components
```python
image_model_server/
├── main.py                 # FastAPI application entry point
├── models.py              # Model management and lifecycle
├── image_processing.py    # Core image processing endpoints
├── management.py          # Health checks and status endpoints
├── __init__.py           # Package initialization
└── README.md             # Service documentation
```

#### 2.2.2 Integration Components
```python
backend/
├── onyx/clients/
│   └── image_model_server.py    # HTTP client for image server
├── onyx/connectors/
│   ├── web/connector.py         # Web connector integration
│   └── file/connector.py        # File connector integration
└── shared_configs/configs.py    # Configuration management
```

## 3. API Design

### 3.1 Image Processing APIs

#### 3.1.1 Comprehensive Processing
```http
POST /process/comprehensive
Content-Type: multipart/form-data

Parameters:
- file: Image file (required)
- filename: Original filename (optional)
- claude_api_key: API key for vision processing (optional)
- claude_provider: Provider (anthropic|bedrock) (optional)
- claude_model: Model name (optional)

Response:
{
    "text": "Combined OCR and description text",
    "metadata": {
        "has_ocr_text": "true",
        "has_description": "true",
        "ocr_text": "Extracted text content",
        "image_description": "Visual description",
        "processing_method": "comprehensive",
        "vision_model": "claude-3-5-sonnet-20241022"
    },
    "embedding": [0.1, -0.3, 0.8, ...],
    "has_embedding": true
}
```

#### 3.1.2 OCR Processing
```http
POST /process/ocr
Content-Type: multipart/form-data

Parameters:
- file: Image file (required)
- filename: Original filename (optional)

Response:
{
    "text": "Extracted text from image",
    "metadata": {
        "has_ocr_text": "true",
        "processing_method": "ocr_only"
    }
}
```

#### 3.1.3 Vision Processing
```http
POST /process/vision
Content-Type: multipart/form-data

Parameters:
- file: Image file (required)
- filename: Original filename (optional)
- claude_api_key: API key (required)
- claude_provider: Provider (optional, default: anthropic)
- claude_model: Model name (optional)

Response:
{
    "description": "Visual description of the image",
    "metadata": {
        "has_description": "true",
        "vision_model": "claude-3-5-sonnet-20241022",
        "processing_method": "vision_only"
    }
}
```

#### 3.1.4 Embedding Generation
```http
POST /process/embedding
Content-Type: multipart/form-data

Parameters:
- file: Image file (required)
- text: Additional text context (optional)

Response:
{
    "embedding": [0.1, -0.3, 0.8, ...],
    "metadata": {
        "embedding_model": "clip-ViT-B-32",
        "embedding_dim": "512",
        "processing_method": "embedding_only"
    }
}
```

### 3.2 Management APIs

#### 3.2.1 Health Check
```http
GET /health

Response:
{
    "status": "healthy",
    "timestamp": "2025-01-25T10:30:00Z",
    "version": "1.0.0"
}
```

#### 3.2.2 Service Status
```http
GET /status

Response:
{
    "service": "image_model_server",
    "version": "1.0.0",
    "models": {
        "ocr": {
            "easyocr": {
                "status": "loaded",
                "languages": ["en", "es", "fr"]
            },
            "tesseract": {
                "status": "available"
            }
        },
        "vision": {
            "claude": {
                "status": "configured",
                "providers": ["anthropic", "bedrock"]
            }
        },
        "embedding": {
            "clip_sentence_transformers": {
                "status": "loaded",
                "model": "clip-ViT-B-32"
            },
            "clip_transformers": {
                "status": "loaded",
                "model": "openai/clip-vit-base-patch32"
            }
        }
    },
    "memory_usage": "2.1GB",
    "uptime": "24h 15m 30s"
}
```

## 4. Data Models

### 4.1 Internal Data Structures

#### 4.1.1 Image Processing Result
```python
class ImageProcessingResult(BaseModel):
    text: str
    metadata: Dict[str, str]
    embedding: Optional[List[float]] = None
    has_embedding: bool = False
```

#### 4.1.2 Model Status
```python
class ModelStatus(BaseModel):
    name: str
    status: Literal["loading", "loaded", "error", "not_available"]
    error_message: Optional[str] = None
    memory_usage: Optional[str] = None
    last_used: Optional[datetime] = None
```

### 4.2 Configuration Models

#### 4.2.1 Server Configuration
```python
class ImageServerConfig(BaseModel):
    host: str = "localhost"
    port: int = 9001
    timeout: int = 300
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    supported_formats: List[str] = ["jpg", "jpeg", "png", "gif", "bmp", "tiff"]
```

#### 4.2.2 Claude Configuration
```python
class ClaudeConfig(BaseModel):
    provider: Literal["anthropic", "bedrock"] = "anthropic"
    model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 1000
    timeout: int = 60
```

## 5. Integration Design

### 5.1 Client Integration

#### 5.1.1 HTTP Client Implementation
```python
class ImageModelServerClient:
    def __init__(self, host: str, port: int, timeout: int = 300):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = httpx.AsyncClient(timeout=timeout)
    
    async def process_image_comprehensive(
        self, 
        file: IO[Any], 
        filename: str,
        claude_api_key: Optional[str] = None,
        claude_provider: str = "anthropic",
        claude_model: str = "claude-3-5-sonnet-20241022"
    ) -> Dict[str, Any]:
        # Implementation details...
```

#### 5.1.2 Connector Integration Pattern
```python
# In Web/File Connectors
async def process_image_for_indexing(file: IO[Any], filename: str) -> Dict[str, Any]:
    processor = get_image_processor(use_remote_server=True)
    
    try:
        # Try remote server first
        return await processor.process_image(file, filename)
    except Exception as e:
        logger.warning(f"Remote processing failed: {e}")
        # Fallback to local processing
        processor_local = get_image_processor(use_remote_server=False)
        return await processor_local.process_image(file, filename)
```

### 5.2 Metadata Conversion

#### 5.2.1 Type Conversion Layer
```python
def convert_metadata_for_document(raw_metadata: Dict[str, Any]) -> Dict[str, Union[str, List[str]]]:
    """Convert image processing metadata to Document-compatible format"""
    metadata = {}
    for key, value in raw_metadata.items():
        if isinstance(value, bool):
            metadata[key] = str(value).lower()
        elif isinstance(value, (int, float)):
            metadata[key] = str(value)
        elif isinstance(value, list):
            metadata[key] = [str(item) for item in value]
        elif value is None:
            metadata[key] = ""
        else:
            metadata[key] = str(value)
    return metadata
```

## 6. Deployment Architecture

### 6.1 Docker Configuration

#### 6.1.1 Image Model Server Dockerfile
```dockerfile
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements/image_model_server.txt .
RUN pip install -r image_model_server.txt

# Pre-download models
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('clip-ViT-B-32')"

# Application code
COPY backend/image_model_server /app/image_model_server
WORKDIR /app

# Run server
CMD ["uvicorn", "image_model_server.main:app", "--host", "0.0.0.0", "--port", "9001"]
```

#### 6.1.2 Docker Compose Integration
```yaml
services:
  image_model_server:
    build:
      context: ../../../
      dockerfile: backend/Dockerfile.image_model_server
    ports:
      - "9001:9001"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
    volumes:
      - huggingface_cache:/root/.cache/huggingface
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9001/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  api_server:
    depends_on:
      - image_model_server
    environment:
      - IMAGE_MODEL_SERVER_HOST=image_model_server
      - IMAGE_MODEL_SERVER_PORT=9001
```

### 6.2 Environment Configuration

#### 6.2.1 Production Environment
```bash
# Image Model Server
IMAGE_MODEL_SERVER_HOST=image-model-server
IMAGE_MODEL_SERVER_PORT=9001
IMAGE_MODEL_SERVER_TIMEOUT=300

# Claude API Configuration
ANTHROPIC_API_KEY=sk-ant-xxxxx
AWS_ACCESS_KEY_ID=AKIAXXXXX
AWS_SECRET_ACCESS_KEY=xxxxx
AWS_DEFAULT_REGION=us-east-1

# Model Configuration
CLIP_MODEL_NAME=clip-ViT-B-32
CLAUDE_MODEL_NAME=claude-3-5-sonnet-20241022
CLAUDE_DEFAULT_PROVIDER=anthropic
```

#### 6.2.2 Development Environment
```bash
# Local development
IMAGE_MODEL_SERVER_HOST=localhost
IMAGE_MODEL_SERVER_PORT=9001
IMAGE_MODEL_SERVER_TIMEOUT=300

# Development API keys
ANTHROPIC_API_KEY=sk-ant-dev-xxxxx
```

## 7. Error Handling & Resilience

### 7.1 Error Categories

#### 7.1.1 Client Errors (4xx)
- **400 Bad Request**: Invalid image format, missing parameters
- **413 Payload Too Large**: Image file exceeds size limit
- **415 Unsupported Media Type**: Unsupported image format

#### 7.1.2 Server Errors (5xx)
- **500 Internal Server Error**: Model processing failures
- **503 Service Unavailable**: Models not loaded, resource exhaustion
- **504 Gateway Timeout**: Processing timeout exceeded

### 7.2 Fallback Mechanisms

#### 7.2.1 Remote to Local Fallback
```python
async def process_image_with_fallback(file: IO[Any], filename: str) -> Dict[str, Any]:
    try:
        # Try remote server
        return await remote_client.process_comprehensive(file, filename)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.warning(f"Remote server unavailable: {e}")
        # Fallback to local processing
        return await local_processor.process_image(file, filename)
    except Exception as e:
        logger.error(f"Remote processing failed: {e}")
        # Basic OCR fallback
        return {"text": basic_ocr(file), "metadata": {"processing_fallback": "true"}}
```

#### 7.2.2 Graceful Degradation
```python
def process_with_degradation(file: IO[Any]) -> Dict[str, Any]:
    result = {"text": "", "metadata": {}, "embedding": None, "has_embedding": False}
    
    # Try OCR
    try:
        result["text"] = extract_ocr_text(file)
        result["metadata"]["has_ocr_text"] = "true"
    except Exception:
        result["metadata"]["has_ocr_text"] = "false"
    
    # Try vision (optional)
    try:
        description = generate_description(file)
        result["text"] += f"\n\nImage Description: {description}"
        result["metadata"]["has_description"] = "true"
    except Exception:
        result["metadata"]["has_description"] = "false"
    
    return result
```

## 8. Performance & Scalability

### 8.1 Performance Targets
- **Processing Time**: <5 seconds per image (typical size)
- **Throughput**: 10 concurrent requests
- **Memory Usage**: <4GB per instance
- **Startup Time**: <60 seconds (including model loading)

### 8.2 Optimization Strategies

#### 8.2.1 Model Optimization
- **Pre-loading**: Load models at startup
- **Model Caching**: Keep models in memory
- **Batch Processing**: Process multiple images together when possible
- **GPU Acceleration**: Optional GPU support for faster inference

#### 8.2.2 Resource Management
```python
# Resource limits and pooling
class ResourceManager:
    def __init__(self):
        self.ocr_semaphore = asyncio.Semaphore(3)  # Max 3 concurrent OCR
        self.vision_semaphore = asyncio.Semaphore(2)  # Max 2 concurrent vision
        self.embedding_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent embeddings
    
    async def process_with_limits(self, process_func, semaphore, *args):
        async with semaphore:
            return await process_func(*args)
```

### 8.3 Scaling Strategies

#### 8.3.1 Horizontal Scaling
- **Load Balancer**: Multiple image server instances
- **Service Discovery**: Dynamic instance registration
- **Health Checks**: Automatic failover for unhealthy instances

#### 8.3.2 Vertical Scaling
- **Memory Scaling**: Increase memory for larger models
- **CPU Scaling**: More cores for concurrent processing
- **GPU Scaling**: GPU instances for faster inference

## 9. Monitoring & Observability

### 9.1 Metrics Collection

#### 9.1.1 Application Metrics
```python
# Prometheus metrics
processing_time = Histogram('image_processing_duration_seconds')
request_count = Counter('image_processing_requests_total')
error_count = Counter('image_processing_errors_total')
model_memory_usage = Gauge('model_memory_usage_bytes')
```

#### 9.1.2 Business Metrics
- **Processing Success Rate**: % of successful image processing
- **Feature Usage**: OCR vs Vision vs Embedding usage
- **Performance Distribution**: Processing time percentiles
- **Error Categories**: Breakdown of error types

### 9.2 Logging Strategy

#### 9.2.1 Structured Logging
```python
logger.info(
    "Image processed successfully",
    extra={
        "filename": filename,
        "processing_time": duration,
        "has_ocr": metadata.get("has_ocr_text"),
        "has_description": metadata.get("has_description"),
        "has_embedding": result.get("has_embedding"),
        "file_size": file_size,
        "image_dimensions": f"{width}x{height}"
    }
)
```

#### 9.2.2 Log Levels
- **DEBUG**: Model loading, detailed processing steps
- **INFO**: Request processing, successful operations
- **WARNING**: Fallback scenarios, degraded performance
- **ERROR**: Processing failures, API errors
- **CRITICAL**: Service unavailable, model loading failures

## 10. Security Considerations

### 10.1 Input Validation
- **File Type Validation**: Strict image format checking
- **File Size Limits**: Prevent resource exhaustion
- **Content Scanning**: Basic malware detection
- **Rate Limiting**: Prevent abuse

### 10.2 API Security
- **Authentication**: API key validation
- **Authorization**: Role-based access control
- **HTTPS**: Encrypted communication
- **Input Sanitization**: Prevent injection attacks

### 10.3 Data Privacy
- **No Persistence**: Images not stored permanently
- **Memory Cleanup**: Secure memory disposal
- **Audit Logging**: Track image processing requests
- **Compliance**: GDPR, SOC2 compliance considerations

## 11. Testing Strategy

### 11.1 Unit Testing
```python
class TestImageProcessing:
    def test_ocr_extraction(self):
        # Test OCR functionality with known images
        
    def test_vision_description(self):
        # Test Claude vision with mock responses
        
    def test_embedding_generation(self):
        # Test CLIP embedding generation
        
    def test_metadata_conversion(self):
        # Test type conversion for Document compatibility
```

### 11.2 Integration Testing
```python
class TestImageServerIntegration:
    def test_comprehensive_processing_endpoint(self):
        # Test full processing pipeline
        
    def test_fallback_mechanisms(self):
        # Test remote to local fallback
        
    def test_connector_integration(self):
        # Test web and file connector integration
```

### 11.3 Performance Testing
- **Load Testing**: Concurrent request handling
- **Stress Testing**: Resource exhaustion scenarios
- **Memory Testing**: Memory leak detection
- **Timeout Testing**: Processing time limits

## 12. Deployment & Operations

### 12.1 Deployment Pipeline
1. **Build**: Docker image creation
2. **Test**: Automated testing suite
3. **Deploy**: Rolling deployment strategy
4. **Verify**: Health check validation
5. **Monitor**: Performance monitoring

### 12.2 Operational Procedures

#### 12.2.1 Health Monitoring
```bash
# Health check commands
curl -f http://localhost:9001/health
curl -f http://localhost:9001/status

# Log monitoring
docker logs image_model_server --tail=100 -f
```

#### 12.2.2 Troubleshooting Guide
- **High Memory Usage**: Model optimization, instance scaling
- **Slow Processing**: GPU acceleration, batch optimization
- **API Timeouts**: Timeout configuration, fallback mechanisms
- **Model Loading Failures**: Dependency verification, cache clearing

## 13. Future Enhancements

### 13.1 Short-term (Next 3 months)
- **Batch Processing**: Multiple image processing
- **Caching Layer**: Redis-based result caching
- **GPU Support**: CUDA acceleration
- **Model Updates**: Latest CLIP and vision models

### 13.2 Long-term (6-12 months)
- **Video Processing**: Frame extraction and analysis
- **Custom Models**: Domain-specific image models
- **Real-time Processing**: WebSocket-based streaming
- **Multi-language OCR**: Extended language support

## 14. Conclusion

The Image Indexing Microservice provides a robust, scalable solution for comprehensive image processing in the Seclore RAG system. The microservice architecture ensures:

- **Scalability**: Independent scaling of image processing capabilities
- **Reliability**: Fault-tolerant design with multiple fallback mechanisms
- **Performance**: Optimized processing pipeline with resource management
- **Maintainability**: Clean separation of concerns and modular architecture
- **Extensibility**: Plugin-based model architecture for future enhancements

The implementation follows industry best practices for microservice design, API development, and operational excellence, ensuring a production-ready solution that enhances the RAG system's multi-modal capabilities. 