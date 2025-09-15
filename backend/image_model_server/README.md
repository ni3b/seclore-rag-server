# Seclore Image Model Server

A dedicated microservice for processing images in the Seclore RAG system. This server handles OCR, vision descriptions using Claude Sonnet 4, and image embeddings using CLIP models.

## Features

- **OCR Processing**: Text extraction using EasyOCR or Tesseract
- **Vision Descriptions**: Detailed image descriptions using Claude Sonnet 4
- **Image Embeddings**: Vector embeddings using CLIP models for multimodal search
- **Comprehensive Processing**: Combined OCR, vision, and embedding processing
- **Health Monitoring**: Health check and status endpoints
- **Async Processing**: Full async support for high performance

## Architecture

The Image Model Server follows the same microservices pattern as the main model server:

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│   Main App      │───▶│  Image Model Server  │───▶│  External APIs  │
│   (API Server)  │    │                      │    │  (Claude API)   │
└─────────────────┘    └──────────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────────┐
                       │   Local Models       │
                       │   (CLIP, OCR)        │
                       └──────────────────────┘
```

## API Endpoints

### Management Endpoints

- `GET /api/health` - Health check
- `GET /api/status` - Model status and availability

### Image Processing Endpoints

- `POST /image/process` - Comprehensive image processing
- `POST /image/ocr` - OCR text extraction only
- `POST /image/vision` - Vision description only (requires Claude API key)
- `POST /image/embedding` - Image embedding only
- `POST /image/upload` - Upload and process image file

## Models Used

### OCR Models
1. **EasyOCR** (Primary) - Multi-language OCR with confidence scores
2. **Tesseract** (Fallback) - Traditional OCR engine

### Vision Models
- **Claude Sonnet 4** - Advanced vision descriptions via **Anthropic API** or **AWS Bedrock**
  - Supports both `anthropic` and `bedrock` providers
  - Uses LiteLLM for consistent interface with main application
  - Automatically detects provider configuration from main app

### Embedding Models
1. **CLIP ViT-B-32** (sentence-transformers) - Primary choice
2. **OpenAI CLIP ViT-Base-Patch32** (transformers) - Fallback

## Configuration

### Environment Variables

```bash
# Server Configuration
IMAGE_MODEL_SERVER_HOST=0.0.0.0
IMAGE_MODEL_SERVER_PORT=9001
IMAGE_MODEL_SERVER_TIMEOUT=300

# Claude API Configuration (choose one)
# Option 1: Anthropic Direct API
ANTHROPIC_API_KEY=your_anthropic_api_key

# Option 2: AWS Bedrock
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION_NAME=us-east-1

# Logging
LOG_LEVEL=info
SENTRY_DSN=your_sentry_dsn
```

## Docker Deployment

### Build Image

```bash
cd backend
docker build -f Dockerfile.image_model_server -t onyx-image-model-server .
```

### Run Container

```bash
docker run -p 9001:9001 \
  -e ANTHROPIC_API_KEY=your_key \
  -e LOG_LEVEL=info \
  onyx-image-model-server
```

### Docker Compose

The image model server is included in the main docker-compose configurations:

```yaml
image_model_server:
  image: onyx-image-model-server:latest
  ports:
    - "9001:9001"
  environment:
    - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    - LOG_LEVEL=info
  volumes:
    - image_model_cache_huggingface:/root/.cache/huggingface/
```

## Usage Examples

### Python Client

```python
from onyx.clients.image_model_server import ImageModelServerClient

async def process_image():
    async with ImageModelServerClient() as client:
        with open("image.jpg", "rb") as f:
            # Using Anthropic API
            result = await client.process_image_comprehensive(
                image_file=f,
                file_name="image.jpg",
                include_ocr=True,
                include_description=True,
                include_embedding=True,
                claude_api_key="your_anthropic_key",
                claude_provider="anthropic",
                claude_model="claude-3-5-sonnet-20241022"
            )
            
            # Or using AWS Bedrock
            result_bedrock = await client.process_image_comprehensive(
                image_file=f,
                file_name="image.jpg",
                include_ocr=True,
                include_description=True,
                include_embedding=True,
                claude_api_key="your_aws_key",  # AWS credentials via env vars
                claude_provider="bedrock",
                claude_model="anthropic.claude-3-5-sonnet-20241022-v2:0"
            )
        
        print(f"Extracted text: {result['text']}")
        print(f"Has embedding: {result['has_embedding']}")
```

### Direct API Call

```python
import httpx
import base64

async def call_api():
    with open("image.jpg", "rb") as f:
        image_data = f.read()
    
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = {
        "image_base64": image_base64,
        "file_name": "image.jpg",
        "include_ocr": True,
        "include_description": True,
        "include_embedding": True,
        "claude_api_key": "your_api_key"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:9001/image/process",
            json=payload
        )
        return response.json()
```

## Development

### Local Development

1. Install dependencies:
```bash
pip install -r requirements/image_model_server.txt
```

2. Run the server:
```bash
cd backend
python -m image_model_server.main
```

### Testing

Run the test suite:
```bash
python test_image_server.py
```

### Adding New Models

To add new image processing models:

1. Update `image_model_server/models.py` to initialize your model
2. Add processing logic in `image_model_server/image_processing.py`
3. Update the requirements file if needed
4. Add model download to the Dockerfile

## Performance Considerations

- **Model Loading**: Models are loaded once at startup and cached
- **Async Processing**: All endpoints are async for better concurrency
- **Thread Pool**: CPU-intensive operations run in thread pools
- **Caching**: Hugging Face models are cached between container restarts
- **Resource Limits**: Consider GPU allocation for CLIP models in production

## Monitoring

### Health Checks

```bash
curl http://localhost:9001/api/health
```

### Model Status

```bash
curl http://localhost:9001/api/status
```

### Logs

The server uses structured logging with configurable levels:

```bash
docker logs image_model_server
```

## Troubleshooting

### Common Issues

1. **Models not loading**: Check available memory and disk space
2. **OCR not working**: Ensure Tesseract is installed in the container
3. **Vision API errors**: Verify Claude API key is valid
4. **Timeout errors**: Increase `IMAGE_MODEL_SERVER_TIMEOUT`

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=debug
```

## Integration with Main Application

The main application automatically uses the Image Model Server when available:

1. **Remote Processing**: Primary mode using the dedicated server
2. **Local Fallback**: Falls back to local processing if server unavailable
3. **Transparent Integration**: Existing code works without changes

## Security

- **API Keys**: Claude API keys are passed per request, not stored
- **Input Validation**: All image inputs are validated
- **Resource Limits**: Processing timeouts prevent resource exhaustion
- **Network Security**: Use internal networking in production 