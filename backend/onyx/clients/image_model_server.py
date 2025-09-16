"""
Client for communicating with the Image Model Server
"""

import base64
import httpx
from typing import Dict, Any, List, Optional, IO
from onyx.utils.logger import setup_logger
from shared_configs.configs import (
    IMAGE_MODEL_SERVER_HOST,
    IMAGE_MODEL_SERVER_PORT,
    IMAGE_MODEL_SERVER_TIMEOUT
)

logger = setup_logger()


class ImageModelServerClient:
    """Client for the Image Model Server"""
    
    def __init__(
        self,
        host: str = IMAGE_MODEL_SERVER_HOST,
        port: int = IMAGE_MODEL_SERVER_PORT,
        timeout: int = IMAGE_MODEL_SERVER_TIMEOUT
    ):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def health_check(self) -> bool:
        """Check if the image model server is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/api/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Image model server health check failed: {str(e)}")
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """Get the status of image models"""
        try:
            response = await self.client.get(f"{self.base_url}/api/status")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get image model server status: {str(e)}")
            raise
    
    async def process_image_comprehensive(
        self,
        image_file: IO[Any],
        file_name: str = "image",
        include_ocr: bool = True,
        include_description: bool = True,
        include_embedding: bool = True,
        claude_api_key: Optional[str] = None,
        claude_provider: str = "anthropic",
        claude_model: str = "claude-3-5-sonnet-20241022"
    ) -> Dict[str, Any]:
        """
        Process image with OCR, vision description, and embeddings
        Supports both Anthropic and Bedrock Claude providers
        """
        try:
            # Read and encode image
            image_file.seek(0)
            image_data = image_file.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "image_base64": image_base64,
                "file_name": file_name,
                "include_ocr": include_ocr,
                "include_description": include_description,
                "include_embedding": include_embedding,
                "claude_api_key": claude_api_key,
                "claude_provider": claude_provider,
                "claude_model": claude_model
            }
            
            response = await self.client.post(
                f"{self.base_url}/image/process",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")
            raise
    
    async def extract_text_ocr(
        self,
        image_file: IO[Any],
        file_name: str = "image"
    ) -> Dict[str, Any]:
        """Extract text from image using OCR"""
        try:
            image_file.seek(0)
            image_data = image_file.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "image_base64": image_base64,
                "file_name": file_name
            }
            
            response = await self.client.post(
                f"{self.base_url}/image/ocr",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"OCR processing failed: {str(e)}")
            raise
    
    async def generate_vision_description(
        self,
        image_file: IO[Any],
        claude_api_key: str,
        file_name: str = "image",
        claude_provider: str = "anthropic",
        claude_model: str = "claude-3-5-sonnet-20241022"
    ) -> Dict[str, Any]:
        """Generate image description using Claude via LiteLLM (supports Bedrock and Anthropic)"""
        try:
            image_file.seek(0)
            image_data = image_file.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "image_base64": image_base64,
                "file_name": file_name,
                "claude_api_key": claude_api_key,
                "claude_provider": claude_provider,
                "claude_model": claude_model
            }
            
            response = await self.client.post(
                f"{self.base_url}/image/vision",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Vision processing failed: {str(e)}")
            raise
    
    async def generate_image_embedding(
        self,
        image_file: IO[Any],
        file_name: str = "image"
    ) -> Dict[str, Any]:
        """Generate image embedding using CLIP"""
        try:
            image_file.seek(0)
            image_data = image_file.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            payload = {
                "image_base64": image_base64,
                "file_name": file_name
            }
            
            response = await self.client.post(
                f"{self.base_url}/image/embedding",
                json=payload
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise


# Global client instance
_image_model_client: Optional[ImageModelServerClient] = None


def get_image_model_client() -> ImageModelServerClient:
    """Get the global image model client instance"""
    global _image_model_client
    if _image_model_client is None:
        _image_model_client = ImageModelServerClient()
    return _image_model_client


async def process_image_for_indexing_remote(
    file: IO[Any], 
    file_name: str = "image",
    claude_api_key: Optional[str] = None,
    claude_provider: Optional[str] = None,
    claude_model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Remote version of process_image_for_indexing using the Image Model Server
    Automatically detects Claude provider settings from main application if not specified
    """
    # If provider/model not specified, try to get from main app's LLM configuration
    if not claude_provider or not claude_model or not claude_api_key:
        try:
            from onyx.llm.factory import get_default_llm
            from onyx.db.engine import get_session_context_manager
            from onyx.db.llm import fetch_default_provider
            
            with get_session_context_manager() as db_session:
                llm_provider = fetch_default_provider(db_session)
                
                if llm_provider and "claude" in llm_provider.default_model_name.lower():
                    claude_provider = claude_provider or llm_provider.provider
                    claude_model = claude_model or llm_provider.default_model_name
                    claude_api_key = claude_api_key or llm_provider.api_key
                    
                    logger.info(f"Using main app's Claude config: {claude_provider}/{claude_model}")
        except Exception as e:
            logger.debug(f"Could not get Claude config from main app: {str(e)}")
    
    # Fallback defaults
    claude_provider = claude_provider or "anthropic"
    claude_model = claude_model or "claude-3-5-sonnet-20241022"
    
    async with ImageModelServerClient() as client:
        return await client.process_image_comprehensive(
            image_file=file,
            file_name=file_name,
            include_ocr=True,
            include_description=True,
            include_embedding=True,
            claude_api_key=claude_api_key,
            claude_provider=claude_provider,
            claude_model=claude_model
        ) 