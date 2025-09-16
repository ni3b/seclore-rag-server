import json
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
import re
import time
from typing import List

import requests

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.interfaces import GenerateDocumentsOutput
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.interfaces import PollConnector
from onyx.connectors.interfaces import SecondsSinceUnixEpoch
from onyx.connectors.models import ConnectorMissingCredentialError
from onyx.connectors.models import Document
from onyx.connectors.models import Section
from onyx.connectors.freshdesk_solutions.connector import FreshdeskSolutionsConnector
from onyx.file_processing.html_utils import parse_html_page_basic_less_strict
from onyx.utils.logger import setup_logger
from onyx.configs.chat_configs import FRESHDESK_RETRY_INTERVAL

logger = setup_logger()

_FRESHDESK_ID_PREFIX = "FRESHDESK_"


_TICKET_FIELDS_TO_INCLUDE = {
    "fr_escalated",
    "spam",
    "priority",
    "source",
    "status",
    "type",
    "is_escalated",
    "tags",
    "nr_due_by",
    "nr_escalated",
    "cc_emails",
    "fwd_emails",
    "reply_cc_emails",
    "ticket_cc_emails",
    "support_email",
    "to_emails",
}

_SOURCE_NUMBER_TYPE_MAP: dict[int, str] = {
    1: "Email",
    2: "Portal",
    3: "Phone",
    7: "Chat",
    9: "Feedback Widget",
    10: "Outbound Email",
}

_PRIORITY_NUMBER_TYPE_MAP: dict[int, str] = {
    1: "low",
    2: "medium",
    3: "high",
    4: "urgent",
}

_STATUS_NUMBER_TYPE_MAP: dict[int, str] = {
    2: "open",
    3: "pending",
    4: "resolved",
    5: "closed",
    17: "Pending with CSM",
    19: "Pending with Cloud",
    18: "Pending with Customer",
    16: "Work in Progress"
}


def _fetch_all_conversations(ticket_id: int, domain: str, api_key: str, password: str) -> str:
    """
    Fetch all conversations for a ticket with pagination support.
    Returns a formatted string containing all conversations.
    """
    base_url = f"https://{domain}.freshdesk.com/api/v2/tickets/{ticket_id}/conversations"
    params = {
        "per_page": 100,  # Maximum conversations per page
        "page": 1,
    }
    
    all_conversations = []
    
    while True:
        while True:
            response = requests.get(
                base_url, auth=(api_key, password), params=params
            )
            retry_after = int(response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
            if response.status_code == 429:
                logger.info(f"Rate limit exceeded for conversations. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            elif response.status_code == 500:
                logger.info(f"Internal server error for conversations. Retrying after 5 seconds...")
                time.sleep(retry_after)
            else:
                response.raise_for_status()
                break
        
        conversations = response.json()
        
        if not conversations:  # No more conversations
            break
            
        all_conversations.extend(conversations)
        logger.info(f"Fetched {len(conversations)} conversations from page {params['page']} for ticket {ticket_id}")
        
        # If we got less than the maximum per page, we've reached the end
        if len(conversations) < params["per_page"]:
            break
            
        params["page"] += 1
    
    # Format conversations into a string
    if all_conversations:
        conversation_text = ""
        include_text = ""
        for count, conversation in enumerate(all_conversations, start=1):
            if conversation.get('private') == False:
                include_text = ""
            else:
                include_text = " (Private Note)"    
            conversation_text += f" Conversation {count}{include_text}: {parse_html_page_basic_less_strict(conversation.get('body_text', 'No content available'))}"
        return conversation_text
    else:
        return " No conversations available."


def _create_metadata_from_ticket(ticket: dict,custom_field: dict, current_url: str, name: str) -> dict:
    metadata: dict[str, str | list[str]] = {}
    # Combine all emails into a list so there are no repeated emails
    email_data: set[str] = set()

    for key, value in ticket.items():
        # Skip fields that aren't useful for embedding
        if key not in _TICKET_FIELDS_TO_INCLUDE:
            continue

        # Skip empty fields
        if not value or value == "[]":
            continue

        # Convert strings or lists to strings
        stringified_value: str | list[str]
        if isinstance(value, list):
            stringified_value = [str(item) for item in value]
        else:
            stringified_value = str(value)

        if "email" in key:
            if isinstance(stringified_value, list):
                email_data.update(stringified_value)
            else:
                email_data.add(stringified_value)
        else:
            metadata[key] = stringified_value

    if email_data:
        metadata["emails"] = list(email_data)

    # Convert source numbers to human-parsable string
    if source_number := ticket.get("source"):
        metadata["source"] = _SOURCE_NUMBER_TYPE_MAP.get(
            source_number, "Unknown Source Type"
        )

    # Convert priority numbers to human-parsable string
    if priority_number := ticket.get("priority"):
        metadata["priority"] = _PRIORITY_NUMBER_TYPE_MAP.get(
            priority_number, "Unknown Priority"
        )

    # Convert status to human-parsable string
    if status_number := ticket.get("status"):
        metadata["status"] = _STATUS_NUMBER_TYPE_MAP.get(
            status_number, "Unknown Status"
        )

  # Convert id to human-parsable string
    if id := ticket.get("id"):
        metadata["id"] = str(id)

    metadata["created_at"] = ticket.get('created_at', '')
    metadata["updated_at"] = ticket.get('updated_at', '')
    metadata["subject"] = ticket.get('subject', '')

    
    due_by = datetime.fromisoformat(ticket["due_by"].replace("Z", "+00:00"))
    metadata["overdue"] = str(datetime.now(timezone.utc) > due_by)


    metadata["title"] = str(custom_field.get('ticket_summary', ''))
    metadata["current_url"] = current_url
    metadata["connector_name"] = name

    return metadata


def _create_doc_from_ticket(ticket: dict, domain: str,api_key, password, name: str) -> Document:
    
    base_url = f"https://{domain}.freshdesk.com/api/v2/tickets/{ticket['id']}?include=conversations"
    logger.info(f"indexing the ticket : {ticket['id']}")
    while True:
        response = requests.get(
                    base_url, auth=(api_key, password)
                )
        
        if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                print(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
        else:
            response.raise_for_status()
            break

    indv_ticket = response.json()

    priority = ""
    # Use the ticket description as the text
    if priority_number := ticket.get("priority"):
        priority = _PRIORITY_NUMBER_TYPE_MAP.get(
            priority_number, "Unknown Priority"
        )

    status = ""
    # Convert status to human-parsable string
    if status_number := ticket.get("status"):
        status = _STATUS_NUMBER_TYPE_MAP.get(
            status_number, "Unknown Status"
        )
    
    text = (
        f"Ticket ID: {ticket.get('id', '')}, Status: {status}, Priority: {priority}, "
    )
    # Fetching custom fields
    custom_field = indv_ticket.get('custom_fields', None)

    if custom_field is not None:
        component = custom_field.get('cf_components', '')
        kb_articles_referred = custom_field.get('cf_kb_articles_referred', '')
        kb_category = custom_field.get('cf_kb_category', '')
        product_category = custom_field.get('cf_product_category', '')
        resolution_type = custom_field.get('cf_resolution_type', '')
        region = custom_field.get('cf_region', '')
        customer = custom_field.get('cf_sd_customer', '')
        severity = custom_field.get('severity', '')
        solution_provided = custom_field.get('solution_provided', '')
        ticket_summary = custom_field.get('ticket_summary', '') 

        text += (
            f"Component: {component}, KB Articles Referred: {kb_articles_referred}, KB Category: {kb_category}, "
            f"Product Category: {product_category}, Resolution Type: {resolution_type}, Region: {region}, "
            f"Customer: {customer}, Severity: {severity}, Solution Provided: {solution_provided}, "
            f"Ticket Summary: {ticket_summary}"
        )

    description_text = indv_ticket.get('description_text', '')
    text += f"Ticket Description : {parse_html_page_basic_less_strict(description_text)}"

    # Adding conversations with pagination support
    text += " Conversations:"
    text += _fetch_all_conversations(ticket['id'], domain, api_key, password)
    

    # Checking and adding custom fields
    solution_provided = custom_field.get('solution_provided')
    if solution_provided:  # Avoid unnecessary checks for None
        text += f" Solution Provided: {parse_html_page_basic_less_strict(solution_provided)}"

    kb_articles_referred = custom_field.get('cf_kb_articles_referred')
    if kb_articles_referred:
        text += f" KB Article Referred for the Solution: {parse_html_page_basic_less_strict(kb_articles_referred)}"
    
    # This is also used in the ID because it is more unique than the just the ticket ID
    link = f"https://{domain}.freshdesk.com/helpdesk/tickets/{ticket['id']}"

    metadata = _create_metadata_from_ticket(ticket,custom_field, link, name)

    return Document(
        id=_FRESHDESK_ID_PREFIX + link,
        sections=[
            Section(
                link=link,
                text=text,
            )
        ],
        source=DocumentSource.FRESHDESK,
        semantic_identifier=ticket.get("subject", "None"),
        metadata=metadata,
        doc_updated_at=datetime.fromisoformat(
            ticket["updated_at"].replace("Z", "+00:00")
        ),
    )


class FreshdeskConnector(PollConnector, LoadConnector):

    # attribute to store the connector name in instantiate_connector()
    name: str | None = None

    def __init__(self, batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.batch_size = batch_size
        self.name = "freshdesk"

    def load_credentials(self, credentials: dict[str, str | int]) -> None:
        api_key = credentials.get("freshdesk_api_key")
        domain = credentials.get("freshdesk_domain")
        password = credentials.get("freshdesk_password")

        if not all(isinstance(cred, str) for cred in [domain, api_key, password]):
            raise ConnectorMissingCredentialError(
                "All Freshdesk credentials must be strings"
            )

        self.api_key = str(api_key)
        self.domain = str(domain)
        self.password = str(password)

    def _fetch_tickets(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> Iterator[List[dict]]:
        """
        'end' is not currently used, so we may double fetch tickets created after the indexing
        starts but before the actual call is made.

        To use 'end' would require us to use the search endpoint but it has limitations,
        namely having to fetch all IDs and then individually fetch each ticket because there is no
        'include' field available for this endpoint:
        https://developers.freshdesk.com/api/#filter_tickets
        """
        if self.api_key is None or self.domain is None or self.password is None:
            raise ConnectorMissingCredentialError("freshdesk")

        base_url = f"https://{self.domain}.freshdesk.com/api/v2/tickets"
        params: dict[str, int | str] = {
            "include": "description",
            "per_page": 100,
            "page": 1,
        }

        if start:
            params["updated_since"] = start.isoformat()

        last_updated_at_from_page_300 = None
        
        while True:
            response = requests.get(
                base_url, auth=(self.api_key, self.password), params=params
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                logger.error(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                response.raise_for_status()
                if response.status_code == 204:
                    break

                tickets = json.loads(response.content)
                logger.info(
                    f"Fetched {len(tickets)} tickets from Freshdesk API (Page {params['page']})"
                )
                
                # Store last_updated_at from page 300 for potential reset
                if params["page"] == 300 and tickets:
                    last_ticket = tickets[-1]
                    logger.debug(f"last ticket on {params['page']}: {last_ticket}")
                    last_updated_at_from_page_300 = last_ticket.get("updated_at")
                    logger.info(f"Stored last_updated_at from {params['page']}: {last_updated_at_from_page_300}")
                
                time.sleep(60)
                yield tickets

                if len(tickets) < int(params["per_page"]):
                    break

                params["page"] = int(params["page"]) + 1
                
                # Check if we need to reset after page 300
                if params["page"] == 301:
                    if last_updated_at_from_page_300:
                        logger.warning(f"Reached page limit (300) for Freshdesk API. Resetting to page 1 with new updated_since")
                        params["page"] = 1
                        params["updated_since"] = last_updated_at_from_page_300
                        logger.info(f"Continuing with updated_since: {last_updated_at_from_page_300}")
                    else:
                        logger.error(f"No last_updated_at available from page 300, stopping pagination")
                        break

    def _process_tickets(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> GenerateDocumentsOutput:
        doc_batch: List[Document] = []

        for ticket_batch in self._fetch_tickets(start, end):
            for ticket in ticket_batch:
                doc_batch.append(_create_doc_from_ticket(ticket, self.domain,self.api_key,self.password, self.name))

                if len(doc_batch) >= self.batch_size:
                    yield doc_batch
                    doc_batch = []

        if doc_batch:
            yield doc_batch

    def load_from_state(self) -> GenerateDocumentsOutput:
        return self._process_tickets()

    def poll_source(
        self, start: SecondsSinceUnixEpoch, end: SecondsSinceUnixEpoch
    ) -> GenerateDocumentsOutput:
        
        start_datetime = datetime.fromtimestamp(start, tz=timezone.utc)
        end_datetime = datetime.fromtimestamp(end, tz=timezone.utc)
        logger.info(f"start time : {start_datetime} and end_datetime : {end_datetime}")

        yield from self._process_tickets(start_datetime, end_datetime)