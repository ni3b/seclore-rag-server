"""
Management endpoints for Image Model Server
Health checks and model status
"""

from fastapi import APIRouter
from fastapi import Response
from typing import Dict, Any

from image_model_server.models import get_model_status
from onyx.utils.logger import setup_logger

logger = setup_logger()

router = APIRouter(prefix="/api")


@router.get("/health")
async def healthcheck() -> Response:
    """Health check endpoint"""
    return Response(status_code=200)


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """Get model status and availability"""
    try:
        status = await get_model_status()
        return {
            "status": "healthy",
            "models": status,
            "server": "image_model_server"
        }
    except Exception as e:
        logger.error(f"Error getting model status: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "server": "image_model_server"
        } 