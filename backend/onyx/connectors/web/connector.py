import io
import ipaddress
import socket
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import cast
from typing import Tuple
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from oauthlib.oauth2 import BackendApplicationClient
from playwright.sync_api import BrowserContext
from playwright.sync_api import Playwright
from playwright.sync_api import sync_playwright
from requests_oauthlib import OAuth2Session  # type:ignore
from urllib3.exceptions import MaxRetryError

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.app_configs import WEB_CONNECTOR_OAUTH_CLIENT_ID
from onyx.configs.app_configs import WEB_CONNECTOR_OAUTH_CLIENT_SECRET
from onyx.configs.app_configs import WEB_CONNECTOR_OAUTH_TOKEN_URL
from onyx.configs.app_configs import WEB_CONNECTOR_VALIDATE_URLS
from onyx.configs.constants import DocumentSource
from onyx.connectors.interfaces import GenerateDocumentsOutput
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.models import Document
from onyx.connectors.models import Section
from onyx.file_processing.extract_file_text import read_pdf_file
from onyx.file_processing.extract_file_text import image_to_text
from onyx.file_processing.extract_file_text import is_image_file_extension
from onyx.file_processing.image_processing import process_image_for_indexing
from onyx.file_processing.html_utils import web_html_cleanup
from onyx.utils.logger import setup_logger
from onyx.utils.sitemap import list_pages_for_site
from shared_configs.configs import MULTI_TENANT
from onyx.indexing.embedder import DefaultIndexingEmbedder
from onyx.configs.image_configs import is_image_processing_enabled

logger = setup_logger()


class WEB_CONNECTOR_VALID_SETTINGS(str, Enum):
    # Given a base site, index everything under that path
    RECURSIVE = "recursive"
    # Given a URL, index only the given page
    SINGLE = "single"
    # Given a sitemap.xml URL, parse all the pages in it
    SITEMAP = "sitemap"
    # Given a file upload where every line is a URL, parse all the URLs provided
    UPLOAD = "upload"


def protected_url_check(url: str) -> None:
    """Couple considerations:
    - DNS mapping changes over time so we don't want to cache the results
    - Fetching this is assumed to be relatively fast compared to other bottlenecks like reading
      the page or embedding the contents
    - To be extra safe, all IPs associated with the URL must be global
    - This is to prevent misuse and not explicit attacks
    """
    if not WEB_CONNECTOR_VALIDATE_URLS:
        return

    parse = urlparse(url)
    if parse.scheme != "http" and parse.scheme != "https":
        raise ValueError("URL must be of scheme https?://")

    if not parse.hostname:
        raise ValueError("URL must include a hostname")

    try:
        # This may give a large list of IP addresses for domains with extensive DNS configurations
        # such as large distributed systems of CDNs
        info = socket.getaddrinfo(parse.hostname, None)
    except socket.gaierror as e:
        raise ConnectionError(f"DNS resolution failed for {parse.hostname}: {e}")

    for address in info:
        ip = address[4][0]
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError(
                f"Non-global IP address detected: {ip}, skipping page {url}. "
                f"The Web Connector is not allowed to read loopback, link-local, or private ranges"
            )


def check_internet_connection(url: str) -> None:
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': url  # Some CDNs require referer
        }
        response = requests.get(url, timeout=3, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # Extract status code from the response, defaulting to -1 if response is None
        status_code = e.response.status_code if e.response is not None else -1
        error_msg = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
        }.get(status_code, "HTTP Error")
        raise Exception(f"{error_msg} ({status_code}) for {url} - {e}")
    except requests.exceptions.SSLError as e:
        cause = (
            e.args[0].reason
            if isinstance(e.args, tuple) and isinstance(e.args[0], MaxRetryError)
            else e.args
        )
        raise Exception(f"SSL error {str(cause)}")
    except (requests.RequestException, ValueError) as e:
        raise Exception(f"Unable to reach {url} - check your internet connection: {e}")


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def get_internal_links(
    base_url: str, url: str, soup: BeautifulSoup, should_ignore_pound: bool = True
) -> set[str]:
    internal_links = set()
    for link in cast(list[dict[str, Any]], soup.find_all("a")):
        href = cast(str | None, link.get("href"))
        if not href:
            continue

        # Account for malformed backslashes in URLs
        href = href.replace("\\", "/")

        if should_ignore_pound and "#" in href:
            href = href.split("#")[0]

        if not is_valid_url(href):
            # Relative path handling
            href = urljoin(url, href)

        if urlparse(href).netloc == urlparse(url).netloc and base_url in href:
            internal_links.add(href)
        
    return internal_links


def extract_images_from_html(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    """Extract all image URLs from HTML content with metadata."""
    images = []
    
    for img_tag in soup.find_all("img"):
        src = img_tag.get("src")
        if not src:
            continue
        
        # Convert relative URLs to absolute URLs
        if not is_valid_url(src):
            src = urljoin(base_url, src)
        
        # Check if it's a valid image URL
        parsed_url = urlparse(src)
        if not parsed_url.scheme or not parsed_url.netloc:
            continue
        
        # Extract image metadata from HTML attributes
        image_info = {
            "url": src,
            "alt": img_tag.get("alt", ""),
            "title": img_tag.get("title", ""),
            "width": img_tag.get("width", ""),
            "height": img_tag.get("height", ""),
            "class": " ".join(img_tag.get("class", [])),
            "id": img_tag.get("id", ""),
        }
        
        # Check for image URLs with traditional extensions
        has_traditional_extension = any(ext in src.lower() for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'))
        
        # Check for data URLs
        is_data_url = src.startswith('data:image/')
        
        # Check for CDN URLs that might not have extensions (common patterns)
        is_cdn_url = any(cdn in src.lower() for cdn in [
            'cdn-cgi/imagedelivery',
            'images.spr.so',
            'cdn.',
            'images.',
            'img.',
            'static.',
            'assets.',
            'media.',
            'uploads/',
            '/images/',
            '/img/',
            '/media/',
            '/assets/',
            '/static/'
        ])
        
        # Additional checks for image-like URLs without extensions
        # Check for common image URL patterns in CDNs
        has_image_patterns = any(pattern in src.lower() for pattern in [
            'quality=',
            'fit=',
            'w=',
            'h=',
            'format=',
            'type=image',
            'image/',
            'photo',
            'picture'
        ])
        
        # Include images with traditional extensions, data URLs, CDN patterns, or image-like patterns
        if has_traditional_extension or is_data_url or is_cdn_url or has_image_patterns:
            # Add debug info about why this image was included
            reason = []
            if has_traditional_extension:
                reason.append("traditional_extension")
            if is_data_url:
                reason.append("data_url")
            if is_cdn_url:
                reason.append("cdn_url")
            if has_image_patterns:
                reason.append("image_patterns")
            
            image_info["extraction_reason"] = ", ".join(reason)
            images.append(image_info)
    
    return images


def start_playwright() -> Tuple[Playwright, BrowserContext]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)

    context = browser.new_context()

    if (
        WEB_CONNECTOR_OAUTH_CLIENT_ID
        and WEB_CONNECTOR_OAUTH_CLIENT_SECRET
        and WEB_CONNECTOR_OAUTH_TOKEN_URL
    ):
        client = BackendApplicationClient(client_id=WEB_CONNECTOR_OAUTH_CLIENT_ID)
        oauth = OAuth2Session(client=client)
        token = oauth.fetch_token(
            token_url=WEB_CONNECTOR_OAUTH_TOKEN_URL,
            client_id=WEB_CONNECTOR_OAUTH_CLIENT_ID,
            client_secret=WEB_CONNECTOR_OAUTH_CLIENT_SECRET,
        )
        context.set_extra_http_headers(
            {"Authorization": "Bearer {}".format(token["access_token"])}
        )

    return playwright, context


def extract_urls_from_sitemap(sitemap_url: str) -> list[str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': sitemap_url  # Some CDNs require referer
    }
    response = requests.get(sitemap_url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    urls = [
        _ensure_absolute_url(sitemap_url, loc_tag.text)
        for loc_tag in soup.find_all("loc")
    ]

    if len(urls) == 0 and len(soup.find_all("urlset")) == 0:
        # the given url doesn't look like a sitemap, let's try to find one
        urls = list_pages_for_site(sitemap_url)

    if len(urls) == 0:
        raise ValueError(
            f"No URLs found in sitemap {sitemap_url}. Try using the 'single' or 'recursive' scraping options instead."
        )

    return urls


def _ensure_absolute_url(source_url: str, maybe_relative_url: str) -> str:
    if not urlparse(maybe_relative_url).netloc:
        return urljoin(source_url, maybe_relative_url)
    return maybe_relative_url


def _ensure_valid_url(url: str) -> str:
    if "://" not in url:
        return "https://" + url
    return url


def _read_urls_file(location: str) -> list[str]:
    with open(location, "r") as f:
        urls = [_ensure_valid_url(line.strip()) for line in f if line.strip()]
    return urls


def _get_datetime_from_last_modified_header(last_modified: str) -> datetime | None:
    try:
        return datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None


class WebConnector(LoadConnector):

    # attribute to store the connector name in instantiate_connector()
    name: str | None = None

    def __init__(
        self,
        base_url: str,  # Can't change this without disrupting existing users
        web_connector_type: str = WEB_CONNECTOR_VALID_SETTINGS.RECURSIVE.value,
        mintlify_cleanup: bool = True,  # Mostly ok to apply to other websites as well
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.mintlify_cleanup = mintlify_cleanup
        self.batch_size = batch_size
        self.recursive = False
        self.name = "web"

        if web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.RECURSIVE.value:
            self.recursive = True
            self.to_visit_list = [_ensure_valid_url(base_url)]
            return

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.SINGLE.value:
            self.to_visit_list = [_ensure_valid_url(base_url)]

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.SITEMAP:
            self.to_visit_list = extract_urls_from_sitemap(_ensure_valid_url(base_url))

        elif web_connector_type == WEB_CONNECTOR_VALID_SETTINGS.UPLOAD:
            # Explicitly check if running in multi-tenant mode to prevent potential security risks
            if MULTI_TENANT:
                raise ValueError(
                    "Upload input for web connector is not supported in cloud environments"
                )

            logger.warning(
                "This is not a UI supported Web Connector flow, "
                "are you sure you want to do this?"
            )
            self.to_visit_list = _read_urls_file(base_url)

        else:
            raise ValueError(
                "Invalid Web Connector Config, must choose a valid type between: " ""
            )

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        if credentials:
            logger.warning("Unexpected credentials provided for Web Connector")
        return None

    def load_from_state(self) -> GenerateDocumentsOutput:
        """Traverses through all pages found on the website
        and converts them into documents"""
        # Log image processing status for debugging
        image_processing_status = "enabled" if is_image_processing_enabled() else "disabled"
        logger.info(f"WebConnector starting with image processing {image_processing_status}")
        
        visited_links: set[str] = set()
        to_visit: list[str] = self.to_visit_list

        if not to_visit:
            raise ValueError("No URLs to visit")

        base_url = to_visit[0]  # For the recursive case
        doc_batch: list[Document] = []

        # Needed to report error
        at_least_one_doc = False
        last_error = None

        playwright, context = start_playwright()
        restart_playwright = False
        while to_visit:
            current_url = to_visit.pop()
            if current_url in visited_links:
                continue
            visited_links.add(current_url)

            try:
                protected_url_check(current_url)
            except Exception as e:
                last_error = f"Invalid URL {current_url} due to {e}"
                logger.warning(last_error)
                continue

            logger.info(f"Visiting {current_url}")

            try:
                check_internet_connection(current_url)
                if restart_playwright:
                    playwright, context = start_playwright()
                    restart_playwright = False

                file_extension = current_url.split(".")[-1].lower()
                
                if file_extension == "pdf":
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (compatible) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': current_url  # Some CDNs require referer
                    }
                    # PDF files are processed with PDF reader
                    response = requests.get(current_url, headers=headers)
                    page_text, metadata = read_pdf_file(
                        file=io.BytesIO(response.content)
                    )
                    last_modified = response.headers.get("Last-Modified")

                    doc_batch.append(
                        Document(
                            id=current_url,
                            sections=[Section(link=current_url, text=page_text)],
                            source=DocumentSource.WEB,
                            semantic_identifier=current_url.split("/")[-1],
                            metadata=metadata,
                            doc_updated_at=_get_datetime_from_last_modified_header(
                                last_modified
                            )
                            if last_modified
                            else None,
                        )
                    )
                    continue
                
                elif is_image_file_extension(f"dummy.{file_extension}"):
                    # Check if image processing is enabled before processing direct image files
                    if not is_image_processing_enabled():
                        logger.info(f"Image processing is disabled, skipping image file {current_url}")
                        continue
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (compatible) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': current_url  # Some CDNs require referer
                    }
                    # Image files are processed with comprehensive image processing (Claude Sonnet 4)
                    response = requests.get(current_url, headers=headers)
                    last_modified = response.headers.get("Last-Modified")
                    
                    try:
                        # Use comprehensive image processing (includes Claude Sonnet 4 vision)
                        image_result = process_image_for_indexing(
                            io.BytesIO(response.content), 
                            current_url.split("/")[-1]
                        )
                        page_text = image_result["text"]
                        raw_metadata = image_result["metadata"]
                        
                        # Convert metadata to Document-compatible format (str | list[str] only)
                        metadata = {}
                        for key, value in raw_metadata.items():
                            if isinstance(value, bool):
                                metadata[key] = str(value).lower()
                            elif isinstance(value, (int, float)):
                                metadata[key] = str(value)
                            elif isinstance(value, list):
                                # Convert list elements to strings
                                metadata[key] = [str(item) for item in value]
                            elif value is None:
                                metadata[key] = ""
                            else:
                                metadata[key] = str(value)
                        
                        # Add web-specific metadata
                        metadata.update({
                            "image_url": current_url,
                            "source": "web",
                            "file_extension": file_extension
                        })
                        
                        # Store image embedding separately if available (don't put in metadata due to size)
                        if image_result.get("has_embedding") and image_result.get("embedding"):
                            metadata["has_image_embedding"] = "true"
                            metadata["embedding_model"] = raw_metadata.get("embedding_model", "unknown")
                            metadata["embedding_dim"] = str(len(image_result["embedding"]))
                            # Note: We don't store the actual embedding in metadata due to Document model constraints
                        
                        logger.info(f"Successfully processed web image {current_url} with OCR: {metadata.get('has_ocr_text', 'false')}, Description: {metadata.get('has_description', 'false')}, Embedding: {image_result.get('has_embedding', False)}")
                        
                    except Exception as e:
                        logger.warning(f"Comprehensive image processing failed for {current_url}, falling back to basic OCR: {str(e)}")
                        # Fallback to basic OCR
                        page_text = image_to_text(io.BytesIO(response.content))
                        metadata = {
                            "image_url": current_url,
                            "file_type": "image",
                            "file_extension": file_extension,
                            "processing_fallback": "true"
                        }

                    doc_batch.append(
                        Document(
                            id=current_url,
                            sections=[Section(link=current_url, text=page_text)],
                            source=DocumentSource.WEB,
                            semantic_identifier=current_url.split("/")[-1],
                            metadata=metadata,
                            doc_updated_at=_get_datetime_from_last_modified_header(
                                last_modified
                            )
                            if last_modified
                            else None,
                        )
                    )
                    continue

                page = context.new_page()
                page_response = page.goto(current_url)
                last_modified = (
                    page_response.header_value("Last-Modified")
                    if page_response
                    else None
                )
                final_page = page.url
                if final_page != current_url:
                    logger.info(f"Redirected to {final_page}")
                    protected_url_check(final_page)
                    current_url = final_page
                    if current_url in visited_links:
                        logger.info("Redirected page already indexed")
                        continue
                    visited_links.add(current_url)

                content = page.content()
                soup = BeautifulSoup(content, "html.parser")

                if self.recursive:
                    internal_links = get_internal_links(base_url, current_url, soup)
                    for link in internal_links:
                        if link not in visited_links:
                            to_visit.append(link)

                if page_response and str(page_response.status)[0] in ("4", "5"):
                    last_error = f"Skipped indexing {current_url} due to HTTP {page_response.status} response"
                    logger.info(last_error)
                    continue

                parsed_html = web_html_cleanup(soup, self.mintlify_cleanup)

                # create a metadata dict for the document
                metadata_dict={
                    "title": parsed_html.title,
                    "url": current_url,
                    "connector_name": self.name,
                }

                # Extract and process embedded images from the HTML page
                images = extract_images_from_html(soup, current_url)
                
                # Add debug logging for image extraction
                if images:
                    logger.debug(f"Extracted {len(images)} images from {current_url}")
                    for i, img in enumerate(images[:3]):  # Log first 3 images for debugging
                        reason = img.get('extraction_reason', 'unknown')
                        logger.debug(f"  Image {i+1}: {img['url']} (alt: {img.get('alt', 'N/A')}, reason: {reason})")
                    if len(images) > 3:
                        logger.debug(f"  ... and {len(images) - 3} more images")
                else:
                    logger.debug(f"No images found in {current_url}")
                
                # Process images and add their content to the main document text
                image_content_parts = []
                if images and is_image_processing_enabled():
                    logger.info(f"Found {len(images)} embedded images in {current_url}, processing and embedding content")
                    
                    for i, image_info in enumerate(images, 1):
                        try:
                            image_url = image_info["url"]
                            
                            # Skip data URLs for now (base64 encoded images)
                            if image_url.startswith('data:'):
                                logger.debug(f"Skipping data URL image from {current_url}")
                                continue
                            
                            # Download the image
                            try:
                                headers = {
                                    'User-Agent': 'Mozilla/5.0 (compatible) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                    'Referer': current_url  # Some CDNs require referer
                                }
                                response = requests.get(image_url, timeout=15, headers=headers)
                                response.raise_for_status()
                            except requests.exceptions.RequestException as e:
                                logger.debug(f"Failed to download image {image_url}: {e}")
                                continue
                            
                            # Check if the response is actually an image
                            content_type = response.headers.get('content-type', '').lower()
                            if not content_type.startswith('image/'):
                                logger.debug(f"Skipping non-image content: {image_url} (content-type: {content_type})")
                                continue
                            
                            # Get file extension and filename - improved to handle images without extensions
                            file_extension = "jpg"  # default fallback
                            
                            # Try to get extension from URL first
                            if "." in image_url:
                                url_extension = image_url.split(".")[-1].lower()
                                if "?" in url_extension:
                                    url_extension = url_extension.split("?")[0]
                                # Check if it's a valid image extension
                                if url_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'svg']:
                                    file_extension = url_extension
            
                            # If no valid extension in URL, try to determine from content-type
                            if file_extension == "jpg":  # still default
                                if 'jpeg' in content_type or 'jpg' in content_type:
                                    file_extension = 'jpg'
                                elif 'png' in content_type:
                                    file_extension = 'png'
                                elif 'gif' in content_type:
                                    file_extension = 'gif'
                                elif 'webp' in content_type:
                                    file_extension = 'webp'
                                elif 'svg' in content_type:
                                    file_extension = 'svg'
                                elif 'bmp' in content_type:
                                    file_extension = 'bmp'
                                elif 'tiff' in content_type:
                                    file_extension = 'tiff'
                            
                            # Generate filename
                            filename = image_url.split("/")[-1] if "/" in image_url else f"image.{file_extension}"
                            if "?" in filename:
                                filename = filename.split("?")[0]
                            
                            # If filename doesn't have an extension, add one
                            if "." not in filename:
                                filename = f"{filename}.{file_extension}"
                            
                            logger.debug(f"Processing image {image_url} as {filename} (content-type: {content_type})")
                            
                            try:
                                # Use comprehensive image processing (includes Claude Sonnet 4 vision)
                                image_result = process_image_for_indexing(
                                    io.BytesIO(response.content), 
                                    filename
                                )
                                image_text = image_result["text"]
                                image_metadata = image_result["metadata"]
                                image_embedding = image_result.get("embedding")
                                
                                # Store image embedding for semantic search
                                if image_embedding is not None:
                                    # Image embedding will be handled by the standard embedding pipeline
                                    logger.debug(f"Image embedding available for {image_url}")
                                
                                # Create a formatted section for this image
                                image_section = []
                                image_section.append(f"\n--- Image {i}: {filename} ---")
                                image_section.append(f"Image URL: {image_url}")
                                
                                # Add HTML context if available
                                if image_info.get("alt"):
                                    image_section.append(f"Alt text: {image_info['alt']}")
                                if image_info.get("title"):
                                    image_section.append(f"Title: {image_info['title']}")
                                
                                # Add the processed image content
                                if image_text and image_text.strip():
                                    image_section.append(f"Image content: {image_text}")
                                
                                # Add processing metadata info
                                if image_metadata.get("has_ocr_text") == "true":
                                    image_section.append("[Contains OCR text]")
                                if image_metadata.get("has_description") == "true":
                                    image_section.append("[Contains AI-generated description]")
                                if image_embedding is not None:
                                    image_section.append("[Contains image embedding for semantic search]")
                                
                                image_section.append("--- End Image ---\n")
                                
                                image_content_parts.append("\n".join(image_section))
                                
                                # Create separate image document with source document relationship
                                image_doc_metadata = {
                                    "image_url": image_url,
                                    "source": "web_embedded",
                                    "source_document_id": current_url,  # Key: Link to source document
                                    "source_document_title": parsed_html.title or current_url,
                                    "file_extension": file_extension,
                                    "html_alt": image_info.get("alt", ""),
                                    "html_title": image_info.get("title", ""),
                                    "connector_name": self.name,
                                }
                                
                                # Add image processing metadata
                                for key, value in image_metadata.items():
                                    if isinstance(value, bool):
                                        image_doc_metadata[key] = str(value).lower()
                                    elif isinstance(value, (int, float)):
                                        image_doc_metadata[key] = str(value)
                                    elif isinstance(value, list):
                                        image_doc_metadata[key] = [str(item) for item in value]
                                    elif value is None:
                                        image_doc_metadata[key] = ""
                                    else:
                                        image_doc_metadata[key] = str(value)
                                
                                # Create separate image document for vector search
                                image_doc = Document(
                                    id=f"{current_url}#{image_url}",  # Unique ID for image
                                    sections=[Section(link=image_url, text=image_text)],
                                    source=DocumentSource.WEB,
                                    semantic_identifier=f"Image from {parsed_html.title or current_url}: {image_info.get('alt', filename)}",
                                    metadata=image_doc_metadata,
                                )
                                
                                doc_batch.append(image_doc)
                                logger.debug(f"Created separate image document: {image_url}")
                                
                                logger.debug(f"Successfully processed and embedded image {i}: {image_url}")
                                
                            except Exception as e:
                                logger.warning(f"Comprehensive image processing failed for {image_url}, falling back to basic OCR: {str(e)}")
                                # Fallback to basic OCR
                                try:
                                    image_text = image_to_text(io.BytesIO(response.content))
                                    if image_text and image_text.strip():
                                        image_section = []
                                        image_section.append(f"\n--- Image {i}: {filename} (OCR only) ---")
                                        image_section.append(f"Image URL: {image_url}")
                                        if image_info.get("alt"):
                                            image_section.append(f"Alt text: {image_info['alt']}")
                                        image_section.append(f"Image content: {image_text}")
                                        image_section.append("--- End Image ---\n")
                                        image_content_parts.append("\n".join(image_section))
                                        logger.debug(f"Added OCR content for image {i}: {image_url}")
                                except Exception as ocr_e:
                                    logger.error(f"Basic OCR also failed for {image_url}: {ocr_e}")
                                    continue
                                    
                        except Exception as e:
                            logger.warning(f"Failed to process embedded image {image_info.get('url', 'unknown')}: {str(e)}")
                            continue
                    
                    if image_content_parts:
                        logger.info(f"Successfully processed {len(image_content_parts)} images from {current_url}")
                        # Add image processing info to metadata
                        metadata_dict["embedded_images_count"] = str(len(image_content_parts))
                        metadata_dict["contains_image_content"] = "true"
                elif images and not is_image_processing_enabled():
                    logger.info(f"Image processing is disabled, skipping {len(images)} embedded images from {current_url}")
                    metadata_dict["embedded_images_count"] = str(len(images))
                    metadata_dict["contains_image_content"] = "false"
                else:
                    logger.debug(f"No embedded images found in {current_url}")

                # Combine the main page text with image content
                combined_text = parsed_html.cleaned_text
                if image_content_parts:
                    combined_text += "\n\n=== EMBEDDED IMAGES ===\n" + "\n".join(image_content_parts)

                # Add the main HTML document with embedded image content
                doc_batch.append(
                    Document(
                        id=current_url,
                        sections=[
                            Section(link=current_url, text=combined_text)
                        ],
                        source=DocumentSource.WEB,
                        semantic_identifier=parsed_html.title or current_url,
                        metadata=metadata_dict,
                        doc_updated_at=_get_datetime_from_last_modified_header(
                            last_modified
                        )
                        if last_modified
                        else None,
                    )
                )

                page.close()
            except Exception as e:
                last_error = f"Failed to fetch '{current_url}': {e}"
                logger.exception(last_error)
                playwright.stop()
                restart_playwright = True
                continue

            if len(doc_batch) >= self.batch_size:
                playwright.stop()
                restart_playwright = True
                at_least_one_doc = True
                yield doc_batch
                doc_batch = []

        if doc_batch:
            playwright.stop()
            at_least_one_doc = True
            yield doc_batch

        if not at_least_one_doc:
            if last_error:
                raise RuntimeError(last_error)
            raise RuntimeError("No valid pages found.")


if __name__ == "__main__":
    connector = WebConnector("https://docs.onyx.app/")
    document_batches = connector.load_from_state(connector.name)
    print(next(document_batches))
