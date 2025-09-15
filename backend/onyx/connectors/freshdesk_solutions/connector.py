import json
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
from datetime import timedelta
import time
from typing import List

import requests

from onyx.configs.constants import DocumentSource
from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.connectors.interfaces import GenerateDocumentsOutput
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.interfaces import PollConnector
from onyx.connectors.interfaces import SecondsSinceUnixEpoch
from onyx.connectors.models import ConnectorMissingCredentialError
from onyx.connectors.models import Document
from onyx.connectors.models import Section
from onyx.utils.logger import setup_logger
from onyx.file_processing.html_utils import parse_html_page_basic_less_strict
from onyx.configs.chat_configs import FRESHDESK_MAX_RETRIES, FRESHDESK_RETRY_INTERVAL

logger = setup_logger()

_FRESHDESK_SOLUTIONS_ID_PREFIX = "FRESHDESK_SOLUTIONS_"

def _create_metadata_from_article(article: dict, current_url: str, name: str) -> dict:
    metadata: dict[str, str | list[str]] = {}
    # Add the important fields to the metadata
    metadata["id"] = str(article.get("id", "NA"))
    metadata["agent_id"] = str(article.get("agent_id", "NA"))
    metadata["created_at"] = str(article.get("created_at", "NA"))
    metadata["updated_at"] = str(article.get("updated_at", "NA"))
    metadata["category_id"] = str(article.get("category_id", "NA"))
    metadata["folder_id"] = str(article.get("folder_id", "NA"))

    # if tags exist, add them to the metadata
    if article["tags"]:
        metadata["tags"] = article.get("tags", "NA")

    metadata["title"] = article.get("title","NA")
    metadata["current_url"] = current_url
    metadata["connector_name"] = name

    return metadata


def _create_doc_from_article(category, folder, article: dict, domain: str, name: str) -> Document:   

    logger.info(f"indexing the article id : {article['id']}")

    category_name = category.get("name", "NA")
    folder_name = folder.get("name", "NA")
    article_title = article.get("title", "NA")
    article_description = article.get("description_text", 'No content available')
    
    # adding tags in the content
    text = ''
    if article["tags"]:
        tags = article.get("tags")
        tag_string = ", ".join(tags)   #take all tags in comma seperated string
        text += f"tags : {parse_html_page_basic_less_strict(tag_string)}, "

    # adding modified date in the content
    updated_at = article.get("updated_at", None)
    if updated_at is not None:
        updated_at = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        updated_at = updated_at.strftime("%Y-%m-%d %H:%M:%S")
        text += f"modified_date : {parse_html_page_basic_less_strict(updated_at)}, "

    # add the required details in text content
    text += (
        f"category_name : {parse_html_page_basic_less_strict(category_name)}, "
        f"folder_name : {parse_html_page_basic_less_strict(folder_name)}, " 
        f"title : {parse_html_page_basic_less_strict(article_title)}, "
        f"description: {parse_html_page_basic_less_strict(article_description)}"
    )

    # This is also used in the ID because it is more unique than the just the ticket ID
    link = f"https://{domain}.freshdesk.com/a/solutions/articles/{article['id']}"
    
     # Create the metadata for the document
    metadata = _create_metadata_from_article(article, link, name)

    return Document(
        id=_FRESHDESK_SOLUTIONS_ID_PREFIX + link,
        sections=[
            Section(
                link=link,
                text=text,
            )
        ],
        source=DocumentSource.FRESHDESK_SOLUTIONS,
        semantic_identifier=article.get("title", "NA"),
        metadata=metadata,
        doc_updated_at=datetime.fromisoformat(
            article["updated_at"].replace("Z", "+00:00")
        ),
    )


class FreshdeskSolutionsConnector(PollConnector, LoadConnector):
    
    # attribute to store the connector name in instantiate_connector()
    name: str | None = None

    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self.name = 'freshdesk_solutions'

    def load_credentials(self, credentials: dict[str, str | int]) -> None:
        api_key = credentials.get("freshdesk_solution_api_key")
        domain = credentials.get("freshdesk_solution_domain")
        password = credentials.get("freshdesk_solution_password")

        if not all(isinstance(cred, str) for cred in [domain, api_key, password]):
            raise ConnectorMissingCredentialError(
                "All Freshdesk solutions credentials must be strings"
            )

        self.api_key = str(api_key)
        self.domain = str(domain)
        self.password = str(password)

    def _fetch_categories(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> Iterator[List[dict]]:
        if self.api_key is None or self.domain is None or self.password is None:
            raise ConnectorMissingCredentialError("freshdesk_solutions")

        base_url = f"https://{self.domain}.freshdesk.com/api/v2/solutions/categories"
       
        # Add a delay to avoid hitting the API too quickly
        time.sleep(2)
        category_response = requests.get(
            base_url, auth=(self.api_key, self.password)
        )
        category_response.raise_for_status()

        if category_response.status_code == 204:
            logger.error("No data returned from Freshdesk API")    #no data

        categories = json.loads(category_response.content)
        logger.info(f"Fetched {len(categories)} categories from Freshdesk API (Page)")
        yield categories


    def _fetch_folders(
        self, category: dict, start: datetime | None = None, end: datetime | None = None
    ) -> Iterator[List[dict]]:
        if self.api_key is None or self.domain is None or self.password is None:
            raise ConnectorMissingCredentialError("freshdesk_solutions")

        folder_url = f"https://{self.domain}.freshdesk.com/api/v2/solutions/categories/{category['id']}/folders"
    
        max_retries = FRESHDESK_MAX_RETRIES
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                folder_response = requests.get(
                    folder_url, auth=(self.api_key, self.password))
                
                if folder_response.status_code == 429:
                    retry_after = int(folder_response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                    logger.error(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                elif folder_response.status_code == 500:
                    retry_after = int(folder_response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                    logger.error(f"Unknown error occurred. Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                else:
                    folder_response.raise_for_status()
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching folders: {e}")
                time.sleep(FRESHDESK_RETRY_INTERVAL)
                retry_count += 1
                continue
        
        # If we've exhausted all retries, raise an exception
        if retry_count >= max_retries:
            raise Exception(f"Failed to fetch folders after {max_retries} retries")

        if folder_response.status_code == 204:
            logger.error("No data returned from Freshdesk API")

        folders = json.loads(folder_response.content)
        logger.info(f"Fetched {len(folders)} Folders from Freshdesk API (Page)")
        yield folders


    def _fetch_articles(
        self, folder: dict, start: datetime | None = None, end: datetime | None = None, hitCount: int = 0
    ) -> Iterator[List[dict]]:
        if self.api_key is None or self.domain is None or self.password is None:
            raise ConnectorMissingCredentialError("freshdesk_solutions")

        if hitCount == 100:
            time.sleep(61)
            logger.info("waited for 1 minute to avoid rate limit after 100 hit")  # Sleep for 1 minute if hit count is 100
            hitCount = 0

        article_url = f"https://{self.domain}.freshdesk.com/api/v2/solutions/folders/{folder['id']}/articles"
        params: dict[str, int | str] = {
            "per_page": 100,
            "page": 1,
        }
       
        while True:

            articles_response = requests.get(
                article_url, auth=(self.api_key, self.password), params=params
            )
            
            # Handle rate limiting
            if articles_response.status_code == 429:
                retry_after = int(articles_response.headers.get("Retry-After", 5))
                logger.error(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            elif articles_response.status_code == 204:
                logger.error("No article data returned from Freshdesk API")
            else:
                articles_response.raise_for_status()

            # parse the articles response
            articles = json.loads(articles_response.content)
            logger.info(f"Fetched {len(articles)} article from Freshdesk API (Page )")
        
            time.sleep(60)            
            yield articles

            if len(articles) < int(params["per_page"]):
                break

            # increment the page number
            params["page"] = int(params["page"]) + 1
        

    def _process_articles(self, start: datetime | None = None, end: datetime | None = None) -> GenerateDocumentsOutput:
        doc_batch: List[Document] = []
        hitCount: int = -1
        totalCount: int = 0

        # Fetch all categories first
        all_categories = []
        for categoryList in self._fetch_categories(start, end):
            all_categories.extend(categoryList)

        # Iterate over the categories and fetch folders
        all_folders = []
        for category in all_categories:
            folder_count = 0  # Count folders for the category
            for folderList in self._fetch_folders(category, start, end):
                all_folders.extend(folderList)
                folder_count += len(folderList)
                            
            # Log the total number of folders in the category
            logger.info(f"Total number of folders in category '{category['name']}': {folder_count}")

        # Iterate over the folders and fetch articles
        all_articles = []
        for folder in all_folders:                
            article_count = 0  # Count articles for the folder
            for articles in self._fetch_articles(folder, start, end, hitCount + 1):
                all_articles.extend(articles)
                article_count += len(articles)
            
            # Log the total number of articles in the folder
            logger.info(f"Total number of articles in folder '{folder['name']}': {article_count}")

        # Process articles
        for article in all_articles:
            updated_at_time = datetime.strptime(article['updated_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            if updated_at_time < start:  # skip articles updated before start date
                continue
            
            # Create document for the article
            document = _create_doc_from_article(category, folder, article, self.domain, self.name)
            doc_batch.append(document)
            totalCount += 1

            # If batch size is reached, yield the batch and reset
            if len(doc_batch) >= self.batch_size:
                yield doc_batch
                doc_batch = []

        # Yield the final batch if there are any remaining documents
        if doc_batch:
            yield doc_batch

        # log total count of articles fetched
        logger.info(f"Total number of articles fetched: {totalCount}")


    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._process_articles()
    

    def poll_source(self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch) -> GenerateDocumentsOutput:
        logger.info("Polling Freshdesk Solutions........started")

        # Convert the start and end timestamps to datetime objects
        start_datetime = datetime.fromtimestamp(start, tz=timezone.utc)
        end_datetime = datetime.fromtimestamp(end, tz=timezone.utc)
        logger.info(f"start time : {start_datetime} and end_datetime : {end_datetime}")

        # Call the _process_articles method
        yield from self._process_articles(start_datetime, end_datetime)