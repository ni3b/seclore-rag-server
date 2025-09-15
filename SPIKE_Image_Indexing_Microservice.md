# SPIKE: Image Indexing Microservice for Seclore RAG System

## Overview
This spike explores the implementation of a dedicated Image Indexing Microservice to enhance the RAG system's capability to process, understand, and index images from various sources (web pages, file uploads, SharePoint, etc.).

## Problem Statement
Currently, the Seclore RAG system has limited image processing capabilities:
- Basic OCR text extraction only
- No visual understanding of image content
- No image-specific embeddings
- Monolithic processing within the main application
- Resource contention between text and image processing

## Proposed Solution
Implement a dedicated **Image Model Server** microservice that provides:
1. **OCR Text Extraction** - Extract text content from images
2. **Visual Description** - Generate semantic descriptions using vision models
3. **Image Embeddings** - Create vector representations for similarity search
4. **Scalable Architecture** - Separate container for resource isolation

## Technical Architecture

### 1. Microservice Components
```
┌─────────────────────────────────────────────────────────────┐
│                 Image Model Server                          │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Application (Port 9001)                           │
│  ├── OCR Processing (EasyOCR, Tesseract)                  │
│  ├── Vision Description (Claude Sonnet 4)                 │
│  ├── Image Embeddings (CLIP Models)                       │
│  └── Model Management & Health Checks                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 Main RAG Application                        │
├─────────────────────────────────────────────────────────────┤
│  ├── Web Connector (calls Image Server)                   │
│  ├── File Connector (calls Image Server)                  │
│  ├── SharePoint Connector (calls Image Server)            │
│  └── Image Client (HTTP communication)                    │
└─────────────────────────────────────────────────────────────┘
```

### 2. API Design
```python
# Image Processing Endpoints
POST /process/comprehensive  # Full image processing pipeline
POST /process/ocr           # OCR text extraction only
POST /process/vision        # Visual description only
POST /process/embedding     # Image embedding generation only

# Management Endpoints
GET /health                 # Health check
GET /status                 # Model status and metrics
```

### 3. Data Flow
```
Image Input → Image Server → {
    OCR Text: "Financial Report Q3 2024"
    Description: "A bar chart showing revenue growth..."
    Embedding: [0.1, -0.3, 0.8, ...]
    Metadata: {
        has_ocr_text: true,
        has_description: true,
        processing_method: "comprehensive",
        vision_model: "claude-sonnet-4"
    }
}
```

## Technical Implementation

### 1. Models and Technologies
- **OCR**: EasyOCR, Tesseract OCR
- **Vision**: Claude Sonnet 4 (via LiteLLM - supports Anthropic + AWS Bedrock)
- **Embeddings**: CLIP models (sentence-transformers, transformers)
- **Framework**: FastAPI with async support
- **Container**: Docker with GPU support (optional)

### 2. Integration Points
- **Web Connector**: Process images from web crawling
- **File Connector**: Process uploaded image files
- **SharePoint Connector**: Process images from SharePoint
- **Document Model**: Metadata type conversion for compatibility

### 3. Configuration
```yaml
# Environment Variables
IMAGE_MODEL_SERVER_HOST=localhost
IMAGE_MODEL_SERVER_PORT=9001
IMAGE_MODEL_SERVER_TIMEOUT=300
ANTHROPIC_API_KEY=sk-xxx
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
```

## Benefits

### 1. Performance & Scalability
- **Resource Isolation**: Dedicated resources for image processing
- **Horizontal Scaling**: Scale image processing independently
- **Async Processing**: Non-blocking image operations
- **Model Caching**: Pre-loaded models for faster inference

### 2. Feature Enhancement
- **Rich Image Understanding**: Beyond OCR to semantic understanding
- **Visual Search**: Image embeddings enable similarity search
- **Multi-modal RAG**: Combine text and visual information
- **Provider Flexibility**: Support multiple Claude providers (Anthropic, Bedrock)

### 3. Maintainability
- **Separation of Concerns**: Isolated image processing logic
- **Independent Deployment**: Deploy image features separately
- **Technology Stack**: Dedicated dependencies for image processing
- **Testing**: Isolated testing of image capabilities

## Risks and Mitigation

### 1. Technical Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| API Latency | High | Async processing, local fallback |
| Model Loading Time | Medium | Pre-load models at startup |
| Memory Usage | High | Model optimization, resource limits |
| Network Failures | Medium | Retry logic, fallback to local processing |

### 2. Integration Risks
| Risk | Impact | Mitigation |
|------|--------|------------|
| Metadata Type Mismatch | High | Type conversion layer implemented |
| Backward Compatibility | Medium | Graceful fallback to existing OCR |
| Docker Dependencies | Low | Multi-stage builds, dependency management |

## Success Criteria
1. **Functional**: Successfully process images with OCR + vision + embeddings
2. **Performance**: <5s processing time for typical images
3. **Reliability**: 99% uptime with graceful fallback
4. **Integration**: Seamless integration with existing connectors
5. **Scalability**: Handle concurrent image processing requests

## Alternative Approaches Considered

### 1. In-Process Integration
- **Pros**: Simpler deployment, no network calls
- **Cons**: Resource contention, harder to scale, dependency conflicts
- **Decision**: Rejected due to scalability concerns

### 2. Async Queue-Based Processing
- **Pros**: Fully decoupled, better for batch processing
- **Cons**: Complex state management, delayed results
- **Decision**: Future enhancement for batch scenarios

### 3. Third-Party Image APIs
- **Pros**: No infrastructure management
- **Cons**: Vendor lock-in, cost, data privacy concerns
- **Decision**: Rejected due to data sensitivity

## Implementation Phases

### Phase 1: Core Infrastructure (2 days)
- Docker container setup
- FastAPI application structure
- Basic health checks and model loading
- Docker Compose integration

### Phase 2: Image Processing Pipeline (2 days)
- OCR integration (EasyOCR, Tesseract)
- Claude Sonnet 4 vision integration
- CLIP embedding generation
- Comprehensive processing endpoint

### Phase 3: Client Integration (1 day)
- HTTP client implementation
- Web connector integration
- File connector integration
- Error handling and fallbacks

### Phase 4: Testing & Optimization (1 day)
- Unit tests for image processing
- Integration tests with connectors
- Performance optimization
- Documentation and deployment guides

## Conclusion
The Image Indexing Microservice provides a scalable, maintainable solution for enhanced image processing in the Seclore RAG system. The microservice architecture enables independent scaling, better resource management, and rich multi-modal capabilities while maintaining backward compatibility.

**Recommendation**: Proceed with implementation following the proposed architecture and phased approach. 