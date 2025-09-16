"""
Image processing module for comprehensive image indexing in RAG systems.
Supports OCR, image descriptions with Claude Sonnet 4, and image embeddings for multimodal search.
"""

import base64
import io
import asyncio
from typing import Any, Dict, List, Optional, Tuple, IO
import numpy as np

from onyx.utils.logger import setup_logger
from onyx.file_processing.extract_file_text import process_image_comprehensive

logger = setup_logger()


class ImageProcessor:
    """
    Comprehensive image processor that handles:
    1. OCR text extraction
    2. Image description generation using Claude Sonnet 4
    3. Image embedding generation for vector search
    
    Now with support for remote Image Model Server
    """
    
    def __init__(self, use_remote_server: bool = True):
        self.use_remote_server = use_remote_server
        self.vision_model = None
        self.embedding_model = None
        if not use_remote_server:
            self._initialize_models()
    
    def _initialize_models(self):
        """Initialize vision and embedding models for local processing."""
        try:
            # Try to initialize CLIP or similar multimodal embedding model
            self._initialize_embedding_model()
        except Exception as e:
            logger.warning(f"Failed to initialize image embedding model: {str(e)}")
    
    def _initialize_embedding_model(self):
        """Initialize the image embedding model (CLIP, etc.)."""
        try:
            # Try to use sentence-transformers with CLIP
            try:
                from sentence_transformers import SentenceTransformer
                # Use a multimodal model that can embed both text and images
                self.embedding_model = SentenceTransformer('clip-ViT-B-32')
                logger.info("Initialized CLIP embedding model")
                return
            except ImportError:
                logger.debug("sentence-transformers not available")
            
            # Fallback: Try to use OpenAI's CLIP via transformers
            try:
                from transformers import CLIPModel, CLIPProcessor
                import torch
                
                self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                logger.info("Initialized transformers CLIP model")
                return
            except ImportError:
                logger.debug("transformers not available")
            
            # If no embedding model available, we'll use text embeddings of descriptions
            logger.warning("No image embedding model available. Will use text embeddings of image descriptions.")
            
        except Exception as e:
            logger.warning(f"Failed to initialize embedding model: {str(e)}")
    
    async def process_image(self, file: IO[Any], file_name: str = "image") -> Dict[str, Any]:
        """
        Process an image comprehensively for RAG indexing.
        
        Returns:
            Dict containing:
            - text: Combined OCR and description text
            - metadata: Image metadata
            - embedding: Image embedding vector (if available)
        """
        # Try remote server first
        if self.use_remote_server:
            try:
                return await self._process_image_remote(file, file_name)
            except Exception as e:
                logger.warning(f"Remote image processing failed, falling back to local: {str(e)}")
                # Fall back to local processing
        
        # Local processing fallback
        return await self._process_image_local(file, file_name)
    
    async def _process_image_remote(self, file: IO[Any], file_name: str) -> Dict[str, Any]:
        """Process image using remote Image Model Server"""
        try:
            from onyx.clients.image_model_server import process_image_for_indexing_remote
            
            # Get Claude API key from environment or configuration
            claude_api_key = self._get_claude_api_key()
            
            result = await process_image_for_indexing_remote(
                file=file,
                file_name=file_name,
                claude_api_key=claude_api_key
            )
            
            logger.info(f"Successfully processed image {file_name} using remote server")
            return result
            
        except Exception as e:
            logger.error(f"Remote image processing failed: {str(e)}")
            raise
    
    async def _process_image_local(self, file: IO[Any], file_name: str) -> Dict[str, Any]:
        """Process image using local models (fallback)"""
        try:
            # Get comprehensive text processing (includes Claude Sonnet 4 vision)
            combined_text, metadata = process_image_comprehensive(file, file_name)
            
            # Generate image embedding
            file.seek(0)
            embedding = await self._generate_image_embedding_local(file, combined_text)
            
            result = {
                "text": combined_text,
                "metadata": metadata,
                "embedding": embedding,
                "has_embedding": embedding is not None
            }
            
            # Add embedding metadata
            if embedding is not None:
                result["metadata"]["embedding_model"] = self._get_embedding_model_name()
                result["metadata"]["embedding_dim"] = len(embedding) if embedding is not None else 0
                result["metadata"]["has_image_embedding"] = True
            
            logger.info(f"Successfully processed image {file_name} using local models")
            return result
            
        except Exception as e:
            logger.error(f"Failed to process image locally: {str(e)}")
            return {
                "text": "",
                "metadata": {"error": str(e), "file_type": "image"},
                "embedding": None,
                "has_embedding": False
            }
    
    def _get_claude_api_key(self) -> Optional[str]:
        """Get Claude API key from environment or configuration"""
        import os
        return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
    
    async def _generate_image_embedding_local(self, file: IO[Any], text_description: str = "") -> Optional[List[float]]:
        """Generate embedding for the image using local models."""
        try:
            # Method 1: Use CLIP model directly on image
            if hasattr(self, 'clip_model') and hasattr(self, 'clip_processor'):
                return await self._generate_clip_embedding_local(file)
            
            # Method 2: Use sentence-transformers CLIP
            if self.embedding_model and hasattr(self.embedding_model, 'encode'):
                try:
                    from PIL import Image
                    file.seek(0)
                    image = Image.open(file)
                    # Run in thread pool since encode is CPU-bound
                    embedding = await asyncio.get_event_loop().run_in_executor(
                        None, self.embedding_model.encode, image
                    )
                    return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                except Exception as e:
                    logger.debug(f"Direct image embedding failed: {str(e)}")
            
            # Method 3: Fallback to text embedding of image description
            if text_description.strip():
                return await self._generate_text_embedding_fallback(text_description)
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to generate image embedding: {str(e)}")
            return None
    
    async def _generate_clip_embedding_local(self, file: IO[Any]) -> Optional[List[float]]:
        """Generate CLIP embedding using transformers."""
        try:
            from PIL import Image
            import torch
            
            file.seek(0)
            image = Image.open(file).convert('RGB')
            
            # Process image
            inputs = self.clip_processor(images=image, return_tensors="pt")
            
            # Generate embedding in thread pool
            def _generate():
                with torch.no_grad():
                    image_features = self.clip_model.get_image_features(**inputs)
                    # Normalize the features
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                return image_features.squeeze().tolist()
            
            return await asyncio.get_event_loop().run_in_executor(None, _generate)
            
        except Exception as e:
            logger.warning(f"CLIP embedding generation failed: {str(e)}")
            return None
    
    async def _generate_text_embedding_fallback(self, text: str) -> Optional[List[float]]:
        """Generate text embedding as fallback for image embedding."""
        try:
            # Use the existing embedding infrastructure
            from onyx.indexing.embedder import DefaultIndexingEmbedder
            from onyx.db.engine import get_session_with_tenant
            from onyx.db.search_settings import get_current_search_settings
            
            # Get current search settings and embedder
            with get_session_with_tenant() as db_session:
                search_settings = get_current_search_settings(db_session)
                embedder = DefaultIndexingEmbedder.from_db_search_settings(search_settings)
                
                # Generate embedding for the text description
                embedding = embedder.embed([text])[0]
                return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
                
        except Exception as e:
            logger.warning(f"Text embedding fallback failed: {str(e)}")
            return None
    
    def _get_embedding_model_name(self) -> str:
        """Get the name of the embedding model being used."""
        if hasattr(self, 'clip_model'):
            return "clip-vit-base-patch32"
        elif self.embedding_model:
            return "clip-ViT-B-32"
        else:
            return "text-embedding-fallback"
    
    async def generate_image_summary(self, file: IO[Any], file_name: str = "image") -> str:
        """Generate a summary of the image for indexing."""
        try:
            if self.use_remote_server:
                try:
                    result = await self._process_image_remote(file, file_name)
                    return result.get("text", f"Image file ({file_name})")
                except Exception:
                    pass  # Fall back to local processing
            
            # Local processing
            combined_text, metadata = process_image_comprehensive(file, file_name)
            
            # Create a structured summary
            summary_parts = []
            
            if metadata.get("has_ocr_text"):
                summary_parts.append(f"Text content: {metadata.get('ocr_text', '')}")
            
            if metadata.get("has_description"):
                summary_parts.append(f"Visual content: {metadata.get('image_description', '')}")
            
            if not summary_parts:
                summary_parts.append("Image file (no text or description extracted)")
            
            return " | ".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Failed to generate image summary: {str(e)}")
            return f"Image file ({file_name})"


# Global image processor instance
_image_processor = None

def get_image_processor(use_remote_server: bool = True) -> ImageProcessor:
    """Get the global image processor instance."""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor(use_remote_server=use_remote_server)
    return _image_processor


def process_image_for_indexing(file: IO[Any], file_name: str = "image") -> Dict[str, Any]:
    """
    Main function to process an image for RAG indexing.
    
    Returns comprehensive image processing results including:
    - OCR text extraction
    - Image description using Claude Sonnet 4
    - Image embeddings
    - Metadata
    
    This function now supports both remote and local processing.
    """
    processor = get_image_processor(use_remote_server=True)
    
    # Since this is called from sync context, we need to handle async
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, processor.process_image(file, file_name))
                return future.result()
        else:
            return asyncio.run(processor.process_image(file, file_name))
    except RuntimeError:
        # Fallback to sync processing if async doesn't work
        processor_local = get_image_processor(use_remote_server=False)
        return asyncio.run(processor_local.process_image(file, file_name)) 