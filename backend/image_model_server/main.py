"""
Main FastAPI application for Image Model Server
Handles image processing, OCR, vision descriptions, and embeddings
"""

import os
import sentry_sdk
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from image_model_server import __version__
from image_model_server.image_processing import router as image_processing_router
from image_model_server.management import router as management_router
from onyx.utils.logger import setup_logger
from shared_configs.configs import SENTRY_DSN

logger = setup_logger()

# Configuration
IMAGE_MODEL_SERVER_HOST = os.environ.get("IMAGE_MODEL_SERVER_HOST") or "0.0.0.0"
IMAGE_MODEL_SERVER_PORT = int(os.environ.get("IMAGE_MODEL_SERVER_PORT") or "9001")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Image Model Server...")
    logger.info(f"Image Model Server Version: {__version__}")
    
    # Initialize models on startup
    try:
        from image_model_server.models import initialize_models
        await initialize_models()
        logger.info("Image models initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize image models: {str(e)}")
        # Continue startup even if models fail to load
    
    yield
    
    logger.info("Shutting down Image Model Server...")


def get_image_model_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    application = FastAPI(
        title="Seclore Image Model Server", 
        version=__version__, 
        lifespan=lifespan,
        description="Image processing server for OCR, vision descriptions, and embeddings"
    )
    
    # Initialize Sentry if configured
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialized for Image Model Server")
    else:
        logger.debug("Sentry DSN not provided, skipping Sentry initialization")

    # Include routers
    application.include_router(management_router)
    application.include_router(image_processing_router)

    return application


app = get_image_model_app()


if __name__ == "__main__":
    logger.notice(
        f"Starting Seclore Image Model Server on http://{IMAGE_MODEL_SERVER_HOST}:{IMAGE_MODEL_SERVER_PORT}/"
    )
    logger.notice(f"Image Model Server Version: {__version__}")
    uvicorn.run(app, host=IMAGE_MODEL_SERVER_HOST, port=IMAGE_MODEL_SERVER_PORT) 