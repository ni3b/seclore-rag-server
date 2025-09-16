"""
Model management for Image Model Server
Handles initialization and lifecycle of image processing models
"""

import asyncio
from typing import Dict, Any, Optional
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Global model storage
_MODELS: Dict[str, Any] = {}
_MODEL_STATUS: Dict[str, Dict[str, Any]] = {}


async def initialize_models():
    """Initialize all image processing models"""
    logger.info("Initializing image processing models...")
    
    # Initialize OCR model
    await _initialize_ocr_model()
    
    # Initialize vision model (Claude Sonnet 4 client)
    await _initialize_vision_model()
    
    # Initialize CLIP models for embeddings
    await _initialize_clip_models()
    
    logger.info("Image model initialization complete")


async def _initialize_ocr_model():
    """Initialize OCR model (Tesseract/EasyOCR)"""
    try:
        # Try EasyOCR first
        try:
            import easyocr
            reader = easyocr.Reader(['en'])
            _MODELS['easyocr'] = reader
            _MODEL_STATUS['easyocr'] = {
                'loaded': True,
                'type': 'ocr',
                'backend': 'easyocr'
            }
            logger.info("EasyOCR model loaded successfully")
            return
        except ImportError:
            logger.debug("EasyOCR not available")
        
        # Fallback to Tesseract
        try:
            import pytesseract
            # Test if tesseract is available
            pytesseract.get_tesseract_version()
            _MODELS['tesseract'] = pytesseract
            _MODEL_STATUS['tesseract'] = {
                'loaded': True,
                'type': 'ocr',
                'backend': 'tesseract'
            }
            logger.info("Tesseract OCR loaded successfully")
            return
        except Exception:
            logger.debug("Tesseract not available")
        
        # No OCR available
        _MODEL_STATUS['ocr'] = {
            'loaded': False,
            'type': 'ocr',
            'error': 'No OCR backend available'
        }
        logger.warning("No OCR model available")
        
    except Exception as e:
        logger.error(f"Failed to initialize OCR model: {str(e)}")
        _MODEL_STATUS['ocr'] = {
            'loaded': False,
            'type': 'ocr',
            'error': str(e)
        }


async def _initialize_vision_model():
    """Initialize vision model client (Claude Sonnet 4)"""
    try:
        # This will be initialized when needed based on API keys
        _MODEL_STATUS['vision'] = {
            'loaded': True,
            'type': 'vision',
            'backend': 'claude-sonnet-4',
            'note': 'Initialized on-demand with API key'
        }
        logger.info("Vision model client ready")
        
    except Exception as e:
        logger.error(f"Failed to initialize vision model: {str(e)}")
        _MODEL_STATUS['vision'] = {
            'loaded': False,
            'type': 'vision',
            'error': str(e)
        }


async def _initialize_clip_models():
    """Initialize CLIP models for image embeddings"""
    try:
        # Try sentence-transformers CLIP first
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('clip-ViT-B-32')
            _MODELS['clip_sentence_transformers'] = model
            _MODEL_STATUS['clip_sentence_transformers'] = {
                'loaded': True,
                'type': 'embedding',
                'backend': 'sentence-transformers',
                'model': 'clip-ViT-B-32'
            }
            logger.info("CLIP model (sentence-transformers) loaded successfully")
            return
        except ImportError:
            logger.debug("sentence-transformers not available")
        
        # Try transformers CLIP
        try:
            from transformers import CLIPModel, CLIPProcessor
            model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            _MODELS['clip_transformers'] = {'model': model, 'processor': processor}
            _MODEL_STATUS['clip_transformers'] = {
                'loaded': True,
                'type': 'embedding',
                'backend': 'transformers',
                'model': 'openai/clip-vit-base-patch32'
            }
            logger.info("CLIP model (transformers) loaded successfully")
            return
        except ImportError:
            logger.debug("transformers not available")
        
        # No CLIP model available
        _MODEL_STATUS['clip'] = {
            'loaded': False,
            'type': 'embedding',
            'error': 'No CLIP backend available'
        }
        logger.warning("No CLIP model available")
        
    except Exception as e:
        logger.error(f"Failed to initialize CLIP models: {str(e)}")
        _MODEL_STATUS['clip'] = {
            'loaded': False,
            'type': 'embedding',
            'error': str(e)
        }


def get_model(model_name: str) -> Optional[Any]:
    """Get a loaded model by name"""
    return _MODELS.get(model_name)


async def get_model_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all models"""
    return _MODEL_STATUS.copy()


def get_available_ocr_model():
    """Get the available OCR model"""
    if 'easyocr' in _MODELS:
        return _MODELS['easyocr'], 'easyocr'
    elif 'tesseract' in _MODELS:
        return _MODELS['tesseract'], 'tesseract'
    return None, None


def get_available_clip_model():
    """Get the available CLIP model"""
    if 'clip_sentence_transformers' in _MODELS:
        return _MODELS['clip_sentence_transformers'], 'sentence_transformers'
    elif 'clip_transformers' in _MODELS:
        return _MODELS['clip_transformers'], 'transformers'
    return None, None 