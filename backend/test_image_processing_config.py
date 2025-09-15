#!/usr/bin/env python3
"""
Test script to verify image processing configuration in WebConnector.
This helps debug issues with complete reindexing not fetching images.
"""

import os
import sys
import logging
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from onyx.configs.image_configs import (
    is_image_processing_enabled,
    is_image_descriptions_enabled,
    is_image_embeddings_enabled,
    ENABLE_IMAGE_PROCESSING,
    ENABLE_IMAGE_DESCRIPTIONS,
    ENABLE_IMAGE_EMBEDDINGS
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_image_processing_config():
    """Test the image processing configuration."""
    logger.info("=== Image Processing Configuration Test ===")
    
    # Check environment variables
    logger.info("Environment Variables:")
    logger.info(f"  ENABLE_IMAGE_PROCESSING: {os.environ.get('ENABLE_IMAGE_PROCESSING', 'not set')}")
    logger.info(f"  ENABLE_IMAGE_DESCRIPTIONS: {os.environ.get('ENABLE_IMAGE_DESCRIPTIONS', 'not set')}")
    logger.info(f"  ENABLE_IMAGE_EMBEDDINGS: {os.environ.get('ENABLE_IMAGE_EMBEDDINGS', 'not set')}")
    
    # Check configuration values
    logger.info("Configuration Values:")
    logger.info(f"  ENABLE_IMAGE_PROCESSING: {ENABLE_IMAGE_PROCESSING}")
    logger.info(f"  ENABLE_IMAGE_DESCRIPTIONS: {ENABLE_IMAGE_DESCRIPTIONS}")
    logger.info(f"  ENABLE_IMAGE_EMBEDDINGS: {ENABLE_IMAGE_EMBEDDINGS}")
    
    # Check configuration functions
    logger.info("Configuration Functions:")
    logger.info(f"  is_image_processing_enabled(): {is_image_processing_enabled()}")
    logger.info(f"  is_image_descriptions_enabled(): {is_image_descriptions_enabled()}")
    logger.info(f"  is_image_embeddings_enabled(): {is_image_embeddings_enabled()}")
    
    # Test WebConnector import and initialization
    try:
        from onyx.connectors.web.connector import WebConnector
        logger.info("✓ WebConnector imported successfully")
        
        # Test creating a WebConnector instance
        connector = WebConnector("https://example.com")
        logger.info("✓ WebConnector instantiated successfully")
        
    except Exception as e:
        logger.error(f"✗ Error with WebConnector: {e}")
        return False
    
    # Provide recommendations
    logger.info("=== Recommendations ===")
    if not is_image_processing_enabled():
        logger.warning("⚠️  Image processing is DISABLED")
        logger.info("To enable image processing during complete reindexing:")
        logger.info("  export ENABLE_IMAGE_PROCESSING=true")
        logger.info("  export ENABLE_IMAGE_DESCRIPTIONS=true")
        logger.info("  export ENABLE_IMAGE_EMBEDDINGS=true")
    else:
        logger.info("✓ Image processing is ENABLED")
        logger.info("Images should be processed during complete reindexing")
    
    return True

def test_with_different_configs():
    """Test with different configuration settings."""
    logger.info("=== Testing Different Configurations ===")
    
    # Test with image processing disabled
    os.environ['ENABLE_IMAGE_PROCESSING'] = 'false'
    
    # Reload the module to pick up new environment variable
    import importlib
    import onyx.configs.image_configs
    importlib.reload(onyx.configs.image_configs)
    
    from onyx.configs.image_configs import is_image_processing_enabled
    logger.info(f"With ENABLE_IMAGE_PROCESSING=false: {is_image_processing_enabled()}")
    
    # Test with image processing enabled
    os.environ['ENABLE_IMAGE_PROCESSING'] = 'true'
    importlib.reload(onyx.configs.image_configs)
    from onyx.configs.image_configs import is_image_processing_enabled
    logger.info(f"With ENABLE_IMAGE_PROCESSING=true: {is_image_processing_enabled()}")

if __name__ == "__main__":
    print("Testing Image Processing Configuration for WebConnector")
    print("=" * 60)
    
    success = test_image_processing_config()
    
    if success:
        print("\n" + "=" * 60)
        print("Configuration test completed successfully!")
        print("If you're still having issues with complete reindexing not fetching images:")
        print("1. Ensure ENABLE_IMAGE_PROCESSING=true in your environment")
        print("2. Check the logs for 'WebConnector starting with image processing enabled'")
        print("3. Look for 'Found X embedded images' messages in the logs")
        print("4. Verify that image processing services are running")
    else:
        print("\n" + "=" * 60)
        print("Configuration test failed. Please check the errors above.")
        sys.exit(1) 