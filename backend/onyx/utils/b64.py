import base64
import logging

logger = logging.getLogger(__name__)


def get_image_type_from_bytes(raw_b64_bytes: bytes) -> str:
    """
    Detect image type from raw bytes using magic numbers.
    Returns the MIME type or a default if the format is unsupported.
    """
    if len(raw_b64_bytes) < 12:
        logger.warning("Image data too short to determine format, defaulting to image/jpeg")
        return "image/jpeg"
    
    magic_number = raw_b64_bytes[:4]
    extended_magic = raw_b64_bytes[:12]

    # PNG format
    if magic_number.startswith(b"\x89PNG"):
        return "image/png"
    
    # JPEG format (multiple variations)
    elif magic_number.startswith(b"\xFF\xD8"):
        return "image/jpeg"
    
    # GIF format (GIF87a or GIF89a)
    elif magic_number.startswith(b"GIF8"):
        return "image/gif"
    
    # WebP format
    elif magic_number.startswith(b"RIFF") and raw_b64_bytes[8:12] == b"WEBP":
        return "image/webp"
    
    # BMP format
    elif magic_number.startswith(b"BM"):
        return "image/bmp"
    
    # TIFF format (Intel and Motorola byte order)
    elif magic_number.startswith(b"II*\x00") or magic_number.startswith(b"MM\x00*"):
        return "image/tiff"
    
    # ICO format
    elif magic_number.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    
    # SVG format (check for XML and SVG)
    elif raw_b64_bytes.startswith(b"<?xml") or raw_b64_bytes.startswith(b"<svg"):
        return "image/svg+xml"
    
    # AVIF format
    elif extended_magic[4:8] == b"ftyp" and (b"avif" in extended_magic or b"avis" in extended_magic):
        return "image/avif"
    
    # HEIC/HEIF format
    elif extended_magic[4:8] == b"ftyp" and (b"heic" in extended_magic or b"mif1" in extended_magic):
        return "image/heic"
    
    else:
        # Log the unknown format for debugging
        logger.warning(
            f"Unknown image format detected. Magic number: {magic_number.hex()[:16]}... "
            f"Defaulting to image/jpeg"
        )
        # Return a default MIME type instead of raising an exception
        return "image/jpeg"


def get_image_type(raw_b64_string: str) -> str:
    try:
        binary_data = base64.b64decode(raw_b64_string)
        return get_image_type_from_bytes(binary_data)
    except Exception as e:
        logger.error(f"Failed to decode base64 image data: {e}")
        return "image/jpeg"
