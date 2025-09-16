import os
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import IO

from sqlalchemy.orm import Session

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.cross_connector_utils.miscellaneous_utils import time_str_to_utc
from onyx.connectors.interfaces import GenerateDocumentsOutput
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.models import BasicExpertInfo
from onyx.connectors.models import Document
from onyx.connectors.models import Section
from onyx.db.engine import get_session_with_tenant
from onyx.file_processing.extract_file_text import detect_encoding
from onyx.file_processing.extract_file_text import extract_file_text
from onyx.file_processing.extract_file_text import get_file_ext
from onyx.file_processing.extract_file_text import is_text_file_extension
from onyx.file_processing.extract_file_text import is_image_file_extension
from onyx.file_processing.extract_file_text import is_valid_file_ext
from onyx.file_processing.extract_file_text import load_files_from_zip
from onyx.file_processing.extract_file_text import read_pdf_file
from onyx.file_processing.extract_file_text import read_text_file
from onyx.file_processing.image_processing import process_image_for_indexing
from onyx.file_store.file_store import get_default_file_store
from onyx.utils.logger import setup_logger
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA
from shared_configs.contextvars import CURRENT_TENANT_ID_CONTEXTVAR

logger = setup_logger()


def _read_files_and_metadata(
    file_name: str,
    db_session: Session,
) -> Iterator[tuple[str, IO, dict[str, Any]]]:
    """Reads the file into IO, in the case of a zip file, yields each individual
    file contained within, also includes the metadata dict if packaged in the zip"""
    extension = get_file_ext(file_name)
    metadata: dict[str, Any] = {}
    directory_path = os.path.dirname(file_name)

    file_content = get_default_file_store(db_session).read_file(file_name, mode="b")

    if extension == ".zip":
        for file_info, file, metadata in load_files_from_zip(
            file_content, ignore_dirs=True
        ):
            yield os.path.join(directory_path, file_info.filename), file, metadata
    elif is_valid_file_ext(extension):
        yield file_name, file_content, metadata
    else:
        logger.warning(f"Skipping file '{file_name}' with extension '{extension}'")


def _process_file(
    file_name: str,
    file: IO[Any],
    metadata: dict[str, Any] | None = None,
    pdf_pass: str | None = None,
) -> list[Document]:
    extension = get_file_ext(file_name)
    if not is_valid_file_ext(extension):
        logger.warning(f"Skipping file '{file_name}' with extension '{extension}'")
        return []

    file_metadata: dict[str, Any] = {}

    if is_text_file_extension(file_name):
        encoding = detect_encoding(file)
        file_content_raw, file_metadata = read_text_file(
            file, encoding=encoding, ignore_onyx_metadata=False
        )

    # Using the PDF reader function directly to pass in password cleanly
    elif extension == ".pdf" and pdf_pass is not None:
        file_content_raw, file_metadata = read_pdf_file(file=file, pdf_pass=pdf_pass)

    # Handle image files with comprehensive processing
    elif is_image_file_extension(file_name):
        try:
            # Use comprehensive image processing (includes Claude Sonnet 4 vision)
            image_result = process_image_for_indexing(file, file_name)
            file_content_raw = image_result["text"]
            raw_metadata = image_result["metadata"]
            
            # Convert metadata to Document-compatible format (str | list[str] only)
            file_metadata = {}
            for key, value in raw_metadata.items():
                if isinstance(value, bool):
                    file_metadata[key] = str(value).lower()
                elif isinstance(value, (int, float)):
                    file_metadata[key] = str(value)
                elif isinstance(value, list):
                    # Convert list elements to strings
                    file_metadata[key] = [str(item) for item in value]
                elif value is None:
                    file_metadata[key] = ""
                else:
                    file_metadata[key] = str(value)
            
            # Store image embedding separately if available (don't put in metadata due to size)
            if image_result.get("has_embedding") and image_result.get("embedding"):
                file_metadata["has_image_embedding"] = "true"
                file_metadata["embedding_model"] = raw_metadata.get("embedding_model", "unknown")
                file_metadata["embedding_dim"] = str(len(image_result["embedding"]))
                # Note: We don't store the actual embedding in metadata due to Document model constraints
            
            logger.info(f"Successfully processed image {file_name} with OCR: {file_metadata.get('has_ocr_text', 'false')}, Description: {file_metadata.get('has_description', 'false')}, Embedding: {image_result.get('has_embedding', False)}")
            
        except Exception as e:
            logger.warning(f"Comprehensive image processing failed for {file_name}, falling back to basic processing: {str(e)}")
            # Fallback to basic text extraction
            file_content_raw = extract_file_text(
                file=file,
                file_name=file_name,
                break_on_unprocessable=True,
            )
            file_metadata = {"file_type": "image", "processing_fallback": "true"}

    else:
        file_content_raw = extract_file_text(
            file=file,
            file_name=file_name,
            break_on_unprocessable=True,
        )

    all_metadata = {**metadata, **file_metadata} if metadata else file_metadata

    # add a prefix to avoid conflicts with other connectors
    doc_id = f"FILE_CONNECTOR__{file_name}"
    if metadata:
        doc_id = metadata.get("document_id") or doc_id

    # If this is set, we will show this in the UI as the "name" of the file
    file_display_name = all_metadata.get("file_display_name") or os.path.basename(
        file_name
    )
    title = (
        all_metadata["title"] or "" if "title" in all_metadata else file_display_name
    )

    time_updated = all_metadata.get("time_updated", datetime.now(timezone.utc))
    if isinstance(time_updated, str):
        time_updated = time_str_to_utc(time_updated)

    dt_str = all_metadata.get("doc_updated_at")
    final_time_updated = time_str_to_utc(dt_str) if dt_str else time_updated

    # Metadata tags separate from the Seclore specific fields
    metadata_tags = {
        k: v
        for k, v in all_metadata.items()
        if k
        not in [
            "document_id",
            "time_updated",
            "doc_updated_at",
            "link",
            "primary_owners",
            "secondary_owners",
            "filename",
            "file_display_name",
            "title",
            "connector_type",
        ]
    }

    source_type_str = all_metadata.get("connector_type")
    source_type = DocumentSource(source_type_str) if source_type_str else None

    p_owner_names = all_metadata.get("primary_owners")
    s_owner_names = all_metadata.get("secondary_owners")
    p_owners = (
        [BasicExpertInfo(display_name=name) for name in p_owner_names]
        if p_owner_names
        else None
    )
    s_owners = (
        [BasicExpertInfo(display_name=name) for name in s_owner_names]
        if s_owner_names
        else None
    )

    return [
        Document(
            id=doc_id,
            sections=[
                Section(link=all_metadata.get("link"), text=file_content_raw.strip())
            ],
            source=source_type or DocumentSource.FILE,
            semantic_identifier=file_display_name,
            title=title,
            doc_updated_at=final_time_updated,
            primary_owners=p_owners,
            secondary_owners=s_owners,
            # currently metadata just houses tags, other stuff like owners / updated at have dedicated fields
            metadata=metadata_tags,
        )
    ]


class LocalFileConnector(LoadConnector):
    def __init__(
        self,
        file_locations: list[Path | str],
        tenant_id: str = POSTGRES_DEFAULT_SCHEMA,
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.file_locations = [Path(file_location) for file_location in file_locations]
        self.batch_size = batch_size
        self.tenant_id = tenant_id
        self.pdf_pass: str | None = None

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self.pdf_pass = credentials.get("pdf_password")
        return None

    def load_from_state(self) -> GenerateDocumentsOutput:
        documents: list[Document] = []
        token = CURRENT_TENANT_ID_CONTEXTVAR.set(self.tenant_id)

        with get_session_with_tenant(self.tenant_id) as db_session:
            for file_path in self.file_locations:
                current_datetime = datetime.now(timezone.utc)
                files = _read_files_and_metadata(
                    file_name=str(file_path), db_session=db_session
                )

                for file_name, file, metadata in files:
                    metadata["time_updated"] = metadata.get(
                        "time_updated", current_datetime
                    )
                    documents.extend(
                        _process_file(file_name, file, metadata, self.pdf_pass)
                    )

                    if len(documents) >= self.batch_size:
                        yield documents
                        documents = []

            if documents:
                yield documents

        CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


if __name__ == "__main__":
    connector = LocalFileConnector(file_locations=[os.environ["TEST_FILE"]])
    connector.load_credentials({"pdf_password": os.environ["PDF_PASSWORD"]})

    document_batches = connector.load_from_state()
    print(next(document_batches))

import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import IO

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.configs.constants import FileOrigin
from onyx.connectors.cross_connector_utils.miscellaneous_utils import (
    process_onyx_metadata,
)
from onyx.connectors.interfaces import GenerateDocumentsOutput
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.models import Document
from onyx.connectors.models import ImageSection
from onyx.connectors.models import TextSection
from onyx.file_processing.extract_file_text import extract_text_and_images
from onyx.file_processing.extract_file_text import get_file_ext
from onyx.file_processing.extract_file_text import is_accepted_file_ext
from onyx.file_processing.extract_file_text import OnyxExtensionType
from onyx.file_processing.image_utils import store_image_and_create_section
from onyx.file_store.file_store import get_default_file_store
from onyx.utils.logger import setup_logger


logger = setup_logger()


def _create_image_section(
    image_data: bytes,
    parent_file_name: str,
    display_name: str,
    link: str | None = None,
    idx: int = 0,
) -> tuple[ImageSection, str | None]:
    """
    Creates an ImageSection for an image file or embedded image.
    Stores the image in FileStore but does not generate a summary.

    Args:
        image_data: Raw image bytes
        db_session: Database session
        parent_file_name: Name of the parent file (for embedded images)
        display_name: Display name for the image
        idx: Index for embedded images

    Returns:
        Tuple of (ImageSection, stored_file_name or None)
    """
    # Create a unique identifier for the image
    file_id = f"{parent_file_name}_embedded_{idx}" if idx > 0 else parent_file_name

    # Store the image and create a section
    try:
        section, stored_file_name = store_image_and_create_section(
            image_data=image_data,
            file_id=file_id,
            display_name=display_name,
            link=link,
            file_origin=FileOrigin.CONNECTOR,
        )
        return section, stored_file_name
    except Exception as e:
        logger.error(f"Failed to store image {display_name}: {e}")
        raise e


def _process_file(
    file_id: str,
    file_name: str,
    file: IO[Any],
    metadata: dict[str, Any] | None,
    pdf_pass: str | None,
    file_type: str | None,
) -> list[Document]:
    """
    Process a file and return a list of Documents.
    For images, creates ImageSection objects without summarization.
    For documents with embedded images, extracts and stores the images.
    """
    if metadata is None:
        metadata = {}

    # Get file extension and determine file type
    extension = get_file_ext(file_name)

    if not is_accepted_file_ext(extension, OnyxExtensionType.All):
        logger.warning(
            f"Skipping file '{file_name}' with unrecognized extension '{extension}'"
        )
        return []

    # If a zip is uploaded with a metadata file, we can process it here
    onyx_metadata, custom_tags = process_onyx_metadata(metadata)
    file_display_name = onyx_metadata.file_display_name or os.path.basename(file_name)
    time_updated = onyx_metadata.doc_updated_at or datetime.now(timezone.utc)
    primary_owners = onyx_metadata.primary_owners
    secondary_owners = onyx_metadata.secondary_owners
    link = onyx_metadata.link

    # These metadata items are not settable by the user
    source_type_str = metadata.get("connector_type")
    source_type = (
        DocumentSource(source_type_str) if source_type_str else DocumentSource.FILE
    )

    doc_id = f"FILE_CONNECTOR__{file_id}"
    title = metadata.get("title") or file_display_name

    # 1) If the file itself is an image, handle that scenario quickly
    if extension in LoadConnector.IMAGE_EXTENSIONS:
        # Read the image data
        image_data = file.read()
        if not image_data:
            logger.warning(f"Empty image file: {file_name}")
            return []

        # Create an ImageSection for the image
        try:
            section, _ = _create_image_section(
                image_data=image_data,
                parent_file_name=file_id,
                display_name=title,
            )

            return [
                Document(
                    id=doc_id,
                    sections=[section],
                    source=source_type,
                    semantic_identifier=file_display_name,
                    title=title,
                    doc_updated_at=time_updated,
                    primary_owners=primary_owners,
                    secondary_owners=secondary_owners,
                    metadata=custom_tags,
                )
            ]
        except Exception as e:
            logger.error(f"Failed to process image file {file_name}: {e}")
            return []

    # 2) Otherwise: text-based approach. Possibly with embedded images.
    file.seek(0)

    # Extract text and images from the file
    extraction_result = extract_text_and_images(
        file=file,
        file_name=file_name,
        pdf_pass=pdf_pass,
        content_type=file_type,
    )

    # Each file may have file-specific ONYX_METADATA https://docs.onyx.app/connectors/file
    # If so, we should add it to any metadata processed so far
    if extraction_result.metadata:
        logger.debug(
            f"Found file-specific metadata for {file_name}: {extraction_result.metadata}"
        )
        onyx_metadata, more_custom_tags = process_onyx_metadata(
            extraction_result.metadata
        )

        # Add file-specific tags
        custom_tags.update(more_custom_tags)

        # File-specific metadata overrides metadata processed so far
        source_type = onyx_metadata.source_type or source_type
        primary_owners = onyx_metadata.primary_owners or primary_owners
        secondary_owners = onyx_metadata.secondary_owners or secondary_owners
        time_updated = onyx_metadata.doc_updated_at or time_updated
        file_display_name = onyx_metadata.file_display_name or file_display_name
        title = onyx_metadata.title or onyx_metadata.file_display_name or title
        link = onyx_metadata.link or link

    # Build sections: first the text as a single Section
    sections: list[TextSection | ImageSection] = []
    if extraction_result.text_content.strip():
        logger.debug(f"Creating TextSection for {file_name} with link: {link}")
        sections.append(
            TextSection(link=link, text=extraction_result.text_content.strip())
        )

    # Then any extracted images from docx, PDFs, etc.
    for idx, (img_data, img_name) in enumerate(
        extraction_result.embedded_images, start=1
    ):
        # Store each embedded image as a separate file in FileStore
        # and create a section with the image reference
        try:
            image_section, stored_file_name = _create_image_section(
                image_data=img_data,
                parent_file_name=file_id,
                display_name=f"{title} - image {idx}",
                idx=idx,
            )
            sections.append(image_section)
            logger.debug(
                f"Created ImageSection for embedded image {idx} "
                f"in {file_name}, stored as: {stored_file_name}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to process embedded image {idx} in {file_name}: {e}"
            )

    return [
        Document(
            id=doc_id,
            sections=sections,
            source=source_type,
            semantic_identifier=file_display_name,
            title=title,
            doc_updated_at=time_updated,
            primary_owners=primary_owners,
            secondary_owners=secondary_owners,
            metadata=custom_tags,
        )
    ]


class LocalFileConnector(LoadConnector):
    """
    Connector that reads files from Postgres and yields Documents, including
    embedded image extraction without summarization.

    file_locations are S3/Filestore UUIDs
    file_names are the names of the files
    """

    # Note: file_names is a required parameter, but should not break backwards compatibility.
    # If add_file_names migration is not run, old file connector configs will not have file_names.
    # file_names is only used for display purposes in the UI and file_locations is used as a fallback.
    def __init__(
        self,
        file_locations: list[Path | str],
        file_names: list[str] | None = None,
        zip_metadata: dict[str, Any] | None = None,
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        self.file_locations = [str(loc) for loc in file_locations]
        self.batch_size = batch_size
        self.pdf_pass: str | None = None
        self.zip_metadata = zip_metadata or {}

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        self.pdf_pass = credentials.get("pdf_password")

        return None

    def _get_file_metadata(self, file_name: str) -> dict[str, Any]:
        return self.zip_metadata.get(file_name, {}) or self.zip_metadata.get(
            os.path.basename(file_name), {}
        )

    def load_from_state(self) -> GenerateDocumentsOutput:
        """
        Iterates over each file path, fetches from Postgres, tries to parse text
        or images, and yields Document batches.
        """
        documents: list[Document] = []

        for file_id in self.file_locations:
            file_store = get_default_file_store()
            file_record = file_store.read_file_record(file_id=file_id)
            if not file_record:
                # typically an unsupported extension
                logger.warning(f"No file record found for '{file_id}' in PG; skipping.")
                continue

            metadata = self._get_file_metadata(file_record.display_name)
            file_io = file_store.read_file(file_id=file_id, mode="b")
            new_docs = _process_file(
                file_id=file_id,
                file_name=file_record.display_name,
                file=file_io,
                metadata=metadata,
                pdf_pass=self.pdf_pass,
                file_type=file_record.file_type,
            )
            documents.extend(new_docs)

            if len(documents) >= self.batch_size:
                yield documents

                documents = []

        if documents:
            yield documents


if __name__ == "__main__":
    connector = LocalFileConnector(
        file_locations=[os.environ["TEST_FILE"]],
        file_names=[os.environ["TEST_FILE"]],
        zip_metadata={},
    )
    connector.load_credentials({"pdf_password": os.environ.get("PDF_PASSWORD")})
    doc_batches = connector.load_from_state()
    for batch in doc_batches:
        print("BATCH:", batch)
