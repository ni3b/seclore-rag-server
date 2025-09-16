"""
Image processing API endpoints
Handles OCR, vision descriptions, and image embeddings
"""

import base64
import io
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from PIL import Image

from image_model_server.models import get_available_ocr_model, get_available_clip_model
from onyx.utils.logger import setup_logger

logger = setup_logger()

router = APIRouter(prefix="/image")


class ImageProcessingRequest(BaseModel):
    """Request model for image processing"""
    image_base64: str
    file_name: str = "image"
    include_ocr: bool = True
    include_description: bool = True
    include_embedding: bool = True
    claude_api_key: Optional[str] = None
    claude_provider: str = "anthropic"  # "anthropic" or "bedrock"
    claude_model: str = "claude-3-5-sonnet-20241022"


class ImageProcessingResponse(BaseModel):
    """Response model for image processing"""
    text: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
    has_embedding: bool = False


class OCRRequest(BaseModel):
    """Request model for OCR only"""
    image_base64: str
    file_name: str = "image"


class OCRResponse(BaseModel):
    """Response model for OCR"""
    text: str
    confidence: Optional[float] = None
    metadata: Dict[str, Any]


class VisionRequest(BaseModel):
    """Request model for vision description"""
    image_base64: str
    file_name: str = "image"
    claude_api_key: str
    claude_provider: str = "anthropic"  # "anthropic" or "bedrock"
    claude_model: str = "claude-3-5-sonnet-20241022"


class VisionResponse(BaseModel):
    """Response model for vision description"""
    description: str
    metadata: Dict[str, Any]


class EmbeddingRequest(BaseModel):
    """Request model for image embedding"""
    image_base64: str
    file_name: str = "image"


class EmbeddingResponse(BaseModel):
    """Response model for image embedding"""
    embedding: List[float]
    model_name: str
    metadata: Dict[str, Any]


@router.post("/process", response_model=ImageProcessingResponse)
async def process_image_comprehensive(request: ImageProcessingRequest) -> ImageProcessingResponse:
    """
    Comprehensive image processing including OCR, vision description, and embeddings
    """
    try:
        # Decode base64 image
        image_data = base64.b64decode(request.image_base64)
        image_file = io.BytesIO(image_data)
        
        # Validate image
        try:
            img = Image.open(image_file)
            img.verify()
            image_file.seek(0)  # Reset after verify
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")
        
        combined_text = ""
        metadata = {
            "file_name": request.file_name,
            "file_type": "image",
            "processing_steps": []
        }
        embedding = None
        
        # OCR Processing
        if request.include_ocr:
            try:
                ocr_result = await _process_ocr(image_file)
                if ocr_result["text"]:
                    combined_text += f"Text content: {ocr_result['text']}"
                    metadata.update(ocr_result["metadata"])
                    metadata["processing_steps"].append("ocr")
            except Exception as e:
                logger.warning(f"OCR processing failed: {str(e)}")
                metadata["ocr_error"] = str(e)
        
        # Vision Description
        if request.include_description and request.claude_api_key:
            try:
                vision_result = await _process_vision(
                    image_file, 
                    request.claude_api_key, 
                    request.claude_provider, 
                    request.claude_model
                )
                if vision_result["description"]:
                    if combined_text:
                        combined_text += " | "
                    combined_text += f"Visual content: {vision_result['description']}"
                    metadata.update(vision_result["metadata"])
                    metadata["processing_steps"].append("vision")
            except Exception as e:
                logger.warning(f"Vision processing failed: {str(e)}")
                metadata["vision_error"] = str(e)
        
        # Image Embedding
        if request.include_embedding:
            try:
                embedding_result = await _process_embedding(image_file)
                embedding = embedding_result["embedding"]
                metadata.update(embedding_result["metadata"])
                metadata["processing_steps"].append("embedding")
            except Exception as e:
                logger.warning(f"Embedding processing failed: {str(e)}")
                metadata["embedding_error"] = str(e)
        
        return ImageProcessingResponse(
            text=combined_text or f"Image file ({request.file_name})",
            metadata=metadata,
            embedding=embedding,
            has_embedding=embedding is not None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")


@router.post("/ocr", response_model=OCRResponse)
async def extract_text_ocr(request: OCRRequest) -> OCRResponse:
    """Extract text from image using OCR"""
    try:
        image_data = base64.b64decode(request.image_base64)
        image_file = io.BytesIO(image_data)
        
        result = await _process_ocr(image_file)
        
        return OCRResponse(
            text=result["text"],
            confidence=result.get("confidence"),
            metadata=result["metadata"]
        )
        
    except Exception as e:
        logger.error(f"OCR processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@router.post("/vision", response_model=VisionResponse)
async def generate_vision_description(request: VisionRequest) -> VisionResponse:
    """Generate image description using Claude via LiteLLM (supports Bedrock and Anthropic)"""
    try:
        image_data = base64.b64decode(request.image_base64)
        image_file = io.BytesIO(image_data)
        
        result = await _process_vision(
            image_file, 
            request.claude_api_key, 
            request.claude_provider, 
            request.claude_model
        )
        
        return VisionResponse(
            description=result["description"],
            metadata=result["metadata"]
        )
        
    except Exception as e:
        logger.error(f"Vision processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Vision processing failed: {str(e)}")


@router.post("/embedding", response_model=EmbeddingResponse)
async def generate_image_embedding(request: EmbeddingRequest) -> EmbeddingResponse:
    """Generate image embedding using CLIP"""
    try:
        image_data = base64.b64decode(request.image_base64)
        image_file = io.BytesIO(image_data)
        
        result = await _process_embedding(image_file)
        
        return EmbeddingResponse(
            embedding=result["embedding"],
            model_name=result["model_name"],
            metadata=result["metadata"]
        )
        
    except Exception as e:
        logger.error(f"Embedding processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Embedding processing failed: {str(e)}")


async def _process_ocr(image_file: io.BytesIO) -> Dict[str, Any]:
    """Process OCR on image"""
    ocr_model, ocr_type = get_available_ocr_model()
    
    if not ocr_model:
        return {
            "text": "",
            "metadata": {"has_ocr_text": False, "ocr_error": "No OCR model available"}
        }
    
    try:
        image_file.seek(0)
        img = Image.open(image_file)
        
        if ocr_type == 'easyocr':
            # EasyOCR processing
            import numpy as np
            img_array = np.array(img)
            results = ocr_model.readtext(img_array)
            
            # Extract text and confidence
            text_parts = []
            confidences = []
            for (bbox, text, confidence) in results:
                if confidence > 0.5:  # Filter low confidence results
                    text_parts.append(text)
                    confidences.append(confidence)
            
            extracted_text = " ".join(text_parts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                "text": extracted_text,
                "confidence": avg_confidence,
                "metadata": {
                    "has_ocr_text": bool(extracted_text),
                    "ocr_backend": "easyocr",
                    "ocr_confidence": avg_confidence
                }
            }
            
        elif ocr_type == 'tesseract':
            # Tesseract processing
            import pytesseract
            extracted_text = pytesseract.image_to_string(img).strip()
            
            return {
                "text": extracted_text,
                "metadata": {
                    "has_ocr_text": bool(extracted_text),
                    "ocr_backend": "tesseract"
                }
            }
    
    except Exception as e:
        logger.error(f"OCR processing error: {str(e)}")
        return {
            "text": "",
            "metadata": {"has_ocr_text": False, "ocr_error": str(e)}
        }


async def _process_vision(image_file: io.BytesIO, api_key: str, provider: str = "anthropic", model_name: str = "claude-3-5-sonnet-20241022") -> Dict[str, Any]:
    """Process vision description using Claude via LiteLLM (supports Bedrock and Anthropic)"""
    try:
        import litellm
        
        # Convert image to base64 for Claude
        image_file.seek(0)
        image_data = image_file.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Determine image format
        image_file.seek(0)
        img = Image.open(image_file)
        img_format = img.format.lower() if img.format else 'jpeg'
        if img_format == 'jpeg':
            img_format = 'jpg'
        
        # Prepare the vision message
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{img_format};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Describe this image in detail. Include any text visible in the image, objects, people, settings, and any other relevant visual information that would be useful for search and retrieval."
                    }
                ]
            }
        ]
        
        # Use LiteLLM for provider flexibility
        response = litellm.completion(
            model=f"{provider}/{model_name}",
            messages=messages,
            api_key=api_key,
            max_tokens=1000,
            timeout=60
        )
        
        description = response.choices[0].message.content if response.choices else ""
        
        return {
            "description": description,
            "metadata": {
                "has_description": bool(description),
                "vision_backend": f"{provider}/{model_name}",
                "image_format": img_format,
                "provider": provider
            }
        }
        
    except Exception as e:
        logger.error(f"Vision processing error: {str(e)}")
        return {
            "description": "",
            "metadata": {"has_description": False, "vision_error": str(e)}
        }


async def _process_embedding(image_file: io.BytesIO) -> Dict[str, Any]:
    """Process image embedding using CLIP"""
    clip_model, clip_type = get_available_clip_model()
    
    if not clip_model:
        raise ValueError("No CLIP model available for embedding generation")
    
    try:
        image_file.seek(0)
        img = Image.open(image_file).convert('RGB')
        
        if clip_type == 'sentence_transformers':
            # Sentence Transformers CLIP
            embedding = clip_model.encode(img)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
            model_name = "clip-ViT-B-32"
            
        elif clip_type == 'transformers':
            # Transformers CLIP
            import torch
            
            inputs = clip_model['processor'](images=img, return_tensors="pt")
            
            with torch.no_grad():
                image_features = clip_model['model'].get_image_features(**inputs)
                # Normalize the features
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            
            embedding_list = image_features.squeeze().tolist()
            model_name = "openai/clip-vit-base-patch32"
        
        else:
            raise ValueError(f"Unknown CLIP type: {clip_type}")
        
        return {
            "embedding": embedding_list,
            "model_name": model_name,
            "metadata": {
                "has_image_embedding": True,
                "embedding_model": model_name,
                "embedding_dim": len(embedding_list),
                "clip_backend": clip_type
            }
        }
        
    except Exception as e:
        logger.error(f"Embedding processing error: {str(e)}")
        raise ValueError(f"Embedding generation failed: {str(e)}")


@router.post("/upload", response_model=ImageProcessingResponse)
async def upload_and_process_image(
    file: UploadFile = File(...),
    include_ocr: bool = True,
    include_description: bool = True,
    include_embedding: bool = True,
    claude_api_key: Optional[str] = None,
    claude_provider: str = "anthropic",
    claude_model: str = "claude-3-5-sonnet-20241022"
) -> ImageProcessingResponse:
    """
    Upload and process image file with configurable Claude provider
    """
    try:
        # Read file content
        content = await file.read()
        
        # Convert to base64
        image_base64 = base64.b64encode(content).decode('utf-8')
        
        # Create request
        request = ImageProcessingRequest(
            image_base64=image_base64,
            file_name=file.filename or "uploaded_image",
            include_ocr=include_ocr,
            include_description=include_description,
            include_embedding=include_embedding,
            claude_api_key=claude_api_key,
            claude_provider=claude_provider,
            claude_model=claude_model
        )
        
        return await process_image_comprehensive(request)
        
    except Exception as e:
        logger.error(f"File upload processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File upload processing failed: {str(e)}") 