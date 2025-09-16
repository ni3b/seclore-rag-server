"""
Configuration settings for image processing in the RAG system.
"""

import os
from typing import Optional

# Image processing settings
ENABLE_IMAGE_PROCESSING = os.environ.get("ENABLE_IMAGE_PROCESSING", "true").lower() == "true"
ENABLE_IMAGE_DESCRIPTIONS = os.environ.get("ENABLE_IMAGE_DESCRIPTIONS", "true").lower() == "true"
ENABLE_IMAGE_EMBEDDINGS = os.environ.get("ENABLE_IMAGE_EMBEDDINGS", "true").lower() == "true"

# Vision model settings - defaults to Claude Sonnet 4 which is the project default
VISION_MODEL_PROVIDER = os.environ.get("VISION_MODEL_PROVIDER", "anthropic")  # anthropic (Claude), openai, etc.
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME", "claude-3-sonnet-20240229")

# Image embedding settings
IMAGE_EMBEDDING_MODEL = os.environ.get("IMAGE_EMBEDDING_MODEL", "clip-ViT-B-32")
USE_CLIP_EMBEDDINGS = os.environ.get("USE_CLIP_EMBEDDINGS", "true").lower() == "true"

# Image processing limits
MAX_IMAGE_SIZE_MB = int(os.environ.get("MAX_IMAGE_SIZE_MB", "20"))
IMAGE_DESCRIPTION_MAX_TOKENS = int(os.environ.get("IMAGE_DESCRIPTION_MAX_TOKENS", "500"))

# Fallback settings
FALLBACK_TO_OCR_ONLY = os.environ.get("FALLBACK_TO_OCR_ONLY", "true").lower() == "true"
FALLBACK_TO_TEXT_EMBEDDING = os.environ.get("FALLBACK_TO_TEXT_EMBEDDING", "true").lower() == "true"

def get_vision_model_config() -> dict:
    """Get vision model configuration."""
    return {
        "provider": VISION_MODEL_PROVIDER,
        "model_name": VISION_MODEL_NAME,
        "max_tokens": IMAGE_DESCRIPTION_MAX_TOKENS
    }

def get_embedding_model_config() -> dict:
    """Get image embedding model configuration."""
    return {
        "model_name": IMAGE_EMBEDDING_MODEL,
        "use_clip": USE_CLIP_EMBEDDINGS,
        "fallback_to_text": FALLBACK_TO_TEXT_EMBEDDING
    }

def is_image_processing_enabled() -> bool:
    """Check if image processing is enabled."""
    return ENABLE_IMAGE_PROCESSING

def is_image_descriptions_enabled() -> bool:
    """Check if image descriptions are enabled."""
    return ENABLE_IMAGE_DESCRIPTIONS and ENABLE_IMAGE_PROCESSING

def is_image_embeddings_enabled() -> bool:
    """Check if image embeddings are enabled."""
    return ENABLE_IMAGE_EMBEDDINGS and ENABLE_IMAGE_PROCESSING 