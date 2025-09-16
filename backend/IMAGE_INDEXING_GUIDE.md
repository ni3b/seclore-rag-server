# Image Indexing Guide for RAG System

This guide explains the comprehensive image indexing capabilities added to the RAG server, enabling multimodal search and retrieval with Claude Sonnet 4 vision integration.

## Overview

The image indexing system provides three main capabilities:

1. **OCR Text Extraction** - Extract text content from images using Unstructured API
2. **Image Description Generation** - Generate semantic descriptions using Claude Sonnet 4 vision capabilities
3. **Image Vectorization** - Create embeddings for semantic image search

## Features

### 🔹 Multimodal Processing Types

| Type | Description | Use Case | Models Used |
|------|-------------|----------|-------------|
| **OCR Extraction** | Extract text from images | Document scanning, text-heavy images | Unstructured API |
| **Image Description** | Generate semantic descriptions | Visual search, content understanding | Claude Sonnet 4, CLIP |
| **Image Embedding** | Vector representations | Similarity search, visual retrieval | CLIP, Sentence-Transformers |
| **Hybrid Indexing** | Combined text + visual | Comprehensive search | All above |

### 🔹 Supported Image Formats

- **JPEG/JPG** - Standard photo format
- **PNG** - Lossless compression, transparency support
- **GIF** - Animated and static images
- **BMP** - Bitmap images
- **TIFF/TIF** - High-quality images
- **WebP** - Modern web format
- **SVG** - Vector graphics
- **AVIF** - Next-gen format
- **HEIC/HEIF** - Apple formats

## Configuration

### Environment Variables

```bash
# Enable/disable image processing features
ENABLE_IMAGE_PROCESSING=true
ENABLE_IMAGE_DESCRIPTIONS=true
ENABLE_IMAGE_EMBEDDINGS=true

# Vision model configuration (defaults to Claude Sonnet 4)
VISION_MODEL_PROVIDER=anthropic
VISION_MODEL_NAME=claude-3-sonnet-20240229
IMAGE_DESCRIPTION_MAX_TOKENS=500

# Embedding model configuration
IMAGE_EMBEDDING_MODEL=clip-ViT-B-32
USE_CLIP_EMBEDDINGS=true

# Processing limits
MAX_IMAGE_SIZE_MB=20

# Fallback settings
FALLBACK_TO_OCR_ONLY=true
FALLBACK_TO_TEXT_EMBEDDING=true

# Required API keys
UNSTRUCTURED_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here  # For Claude Sonnet 4 vision descriptions
```

### Optional Dependencies

Install additional packages for enhanced functionality:

```bash
pip install -r requirements/image_processing.txt
```

## Usage Examples

### Basic Usage

```python
from onyx.file_processing.image_processing import process_image_for_indexing

# Process an image file
with open("document.jpg", "rb") as f:
    result = process_image_for_indexing(f, "document.jpg")
    
print(f"Extracted text: {result['text']}")
print(f"Has embedding: {result['has_embedding']}")
print(f"Vision model: {result['metadata']['vision_model']}")
print(f"Metadata: {result['metadata']}")
```

### File Connector Integration

Images uploaded via the file connector are automatically processed with:

- OCR text extraction
- Image description generation using Claude Sonnet 4
- Embedding generation (if enabled)
- Comprehensive metadata storage

### Web Connector Integration

The web connector now supports indexing images from websites:

```python
from onyx.connectors.web.connector import WebConnector

# This will now process images found on websites using Claude Sonnet 4
connector = WebConnector("https://example.com/")
documents = connector.load_from_state()
```

## Processing Pipeline

### 1. Image Detection
```
File Extension Check → Image Format Validation → Size Validation
```

### 2. OCR Processing
```
Unstructured API → Text Extraction → OCR Metadata
```

### 3. Description Generation  
```
Claude Sonnet 4 Vision → Image Analysis → Semantic Description
```

### 4. Embedding Generation
```
CLIP Model → Image Encoding → Vector Embedding
```

### 5. Index Storage
```
Combined Text + Metadata + Embedding → Document Index
```

## Search Capabilities

### Text-to-Image Search
Search for images using text queries:
```
Query: "document with charts"
→ Matches images containing charts based on Claude Sonnet 4 descriptions
```

### Image-to-Image Search  
Find similar images using embeddings:
```
Upload image → Generate embedding → Find similar vectors
```

### Hybrid Search
Combine text and visual similarity:
```
Query: "financial report" + visual similarity
→ Comprehensive multimodal matching
```

## Metadata Structure

Processed images include rich metadata:

```json
{
  "file_type": "image",
  "has_ocr_text": true,
  "has_description": true,
  "ocr_text": "Extracted text content...",
  "image_description": "A chart showing quarterly results...",
  "processing_method": "comprehensive_image_processing",
  "vision_model": "claude-sonnet-4",
  "embedding_model": "clip-ViT-B-32",
  "embedding_dim": 512,
  "has_image_embedding": true,
  "image_embedding": [0.1, 0.2, ...],
  "file_extension": "jpg"
}
```

## Performance Considerations

### Processing Speed
- **OCR**: ~2-5 seconds per image (via Unstructured API)
- **Description**: ~3-8 seconds per image (via Claude Sonnet 4)
- **Embedding**: ~1-2 seconds per image (local CLIP)

### Storage Requirements
- **Text**: Minimal (few KB per image)
- **Embeddings**: ~2KB per image (512-dim float vectors)
- **Metadata**: ~1KB per image

### Scaling Recommendations
- Use batch processing for large image collections
- Consider embedding caching for repeated processing
- Monitor API rate limits for external services

## Troubleshooting

### Common Issues

1. **No OCR Text Extracted**
   - Verify UNSTRUCTURED_API_KEY is set
   - Check image quality and text visibility
   - Ensure supported image format

2. **No Image Descriptions**
   - Verify ANTHROPIC_API_KEY is set for Claude Sonnet 4
   - Check ENABLE_IMAGE_DESCRIPTIONS=true
   - Verify Claude Sonnet 4 is configured as default LLM

3. **No Image Embeddings**
   - Install: `pip install sentence-transformers torch`
   - Check ENABLE_IMAGE_EMBEDDINGS=true
   - Verify CLIP model download

4. **Processing Failures**
   - Check image file size (< MAX_IMAGE_SIZE_MB)
   - Verify image format support
   - Check API quotas and rate limits

### Testing

Run the test suite to verify functionality:

```bash
cd backend
python test_image_indexing.py
```

## Advanced Configuration

### Custom Vision Models

The system uses Claude Sonnet 4 by default, but you can modify the `_generate_image_description_with_sonnet` function in `extract_file_text.py` to use different vision models.

### Custom Embedding Models

To use different embedding models, update the `ImageProcessor` class in `image_processing.py`.

### Performance Tuning

- Adjust batch sizes for bulk processing
- Configure concurrent processing limits
- Optimize embedding model selection

## API Integration

The image processing integrates seamlessly with existing RAG endpoints:

- **File Upload**: Automatic image processing with Claude Sonnet 4
- **Search**: Multimodal query support  
- **Retrieval**: Combined text and visual matching

## Future Enhancements

Planned improvements include:

- Support for additional vision models (GPT-4V, Gemini Vision)
- Advanced image segmentation and region analysis
- Video frame extraction and processing
- Enhanced multilingual OCR support
- Custom embedding fine-tuning capabilities

## Support

For issues or questions:

1. Check the troubleshooting section
2. Run the test suite for diagnostics
3. Review logs for detailed error information
4. Verify all dependencies and API keys are configured 