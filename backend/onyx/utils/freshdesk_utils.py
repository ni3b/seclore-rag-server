import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import re
import requests

from onyx.file_processing.html_utils import parse_html_page_basic_less_strict
from onyx.utils.logger import setup_logger
from onyx.configs.chat_configs import FRESHDESK_MAX_RETRIES, FRESHDESK_RETRY_INTERVAL

logger = setup_logger()


class TicketStatus(Enum):
    OPEN = 2
    PENDING = 3
    RESOLVED = 4
    CLOSED = 5
    PENDING_WITH_CSM = 17
    PENDING_WITH_CLOUD = 19
    PENDING_WITH_CUSTOMER = 18
    WORK_IN_PROGRESS = 16


class TicketPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


class TicketSource(Enum):
    EMAIL = 1
    PORTAL = 2
    PHONE = 3
    CHAT = 7
    FEEDBACK_WIDGET = 9
    OUTBOUND_EMAIL = 10


class FreshdeskUtils:
    """
    Utility class for Freshdesk API operations providing methods to:
    1. Get ticket details with conversations
    2. List tickets with various filters
    3. Handle custom tool endpoints for search and details
    """
    
    def __init__(self, domain: str, api_key: str, password: str = "X"):
        """
        Initialize FreshdeskUtils with credentials
        
        Args:
            domain: Freshdesk domain (e.g., 'yourcompany' for yourcompany.freshdesk.com)
            api_key: Freshdesk API key
            password: Password for API authentication (default is 'X' for API key auth)
        """
        self.domain = domain
        self.api_key = api_key
        self.password = password
        self.base_url = f"https://{domain}.freshdesk.com/api/v2"
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> requests.Response:
        """
        Make a request to Freshdesk API with rate limiting handling
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            Response object
        """
        url = f"{self.base_url}/{endpoint}"
        max_retries = FRESHDESK_MAX_RETRIES
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"url: {url} | params: {params}")
                response = requests.get(url, auth=(self.api_key, self.password), params=params)
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                    logger.warning(f"Rate limit exceeded. Retrying after {retry_after} seconds... (attempt {retry_count + 1}/{max_retries})")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                elif response.status_code == 500:
                    retry_after = int(response.headers.get("Retry-After", FRESHDESK_RETRY_INTERVAL))
                    logger.warning(f"Unknown error occurred. Retrying after {retry_after} seconds... (attempt {retry_count + 1}/{max_retries})")
                    time.sleep(retry_after)
                    retry_count += 1
                    continue
                elif response.status_code == 401:
                    logger.error("Authentication failed. Please check your API key and credentials.")
                    return {"error": "Authentication failed. Please check your API key and credentials."}
                elif response.status_code == 403:
                    logger.error("Access forbidden. Please check your permissions.")
                    return {"error": "Access forbidden. Please check your permissions."}
                elif response.status_code == 404:
                    logger.error("Resource not found. Please check your request parameters.")
                    return {"error": "No results found. Please check information provided by you is correct?"}
                elif response.status_code >= 400:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")
                    return {"error": f"API request failed with status {response.status_code}: {response.text}"}
                else:
                    return response
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if retry_count < max_retries - 1:
                    retry_count += 1
                    time.sleep(5)  # Wait 5 seconds before retrying
                    continue
                else:
                    raise
        
        # If we've exhausted all retries
        raise Exception(f"Failed to make request after {max_retries} attempts")
    
    def get_ticket_details(self, ticket_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific ticket including all conversations
        
        Args:
            ticket_id: The ID of the ticket to retrieve
            include_conversations: Whether to include conversations (default: True)
            
        Returns:
            Dictionary containing ticket details and conversations
        """
        # Get ticket details
        response = self._make_request(f"tickets/{ticket_id}")
        
        # Check if response is an error dictionary
        if isinstance(response, dict) and "error" in response:
            return response # return error response directly for llm to handle
        else:        
            ticket = response.json()

            # Parse and format ticket data
            description_text = ""
            if ticket.get("description"):
                description_text = parse_html_page_basic_less_strict(ticket.get("description"))
            
            # Parse and format ticket data
            ticket_details = {
                "id": ticket.get("id"),
                "subject": ticket.get("subject"),
                "description_text": description_text,
                "status": self._get_status_name(ticket.get("status")),
                "priority": self._get_priority_name(ticket.get("priority")),
                "source": self._get_source_name(ticket.get("source")),
                "type": ticket.get("type"),
                "created_at": ticket.get("created_at"),
                "updated_at": ticket.get("updated_at"),
                "due_by": ticket.get("due_by"),
                "fr_due_by": ticket.get("fr_due_by"),
                "is_escalated": ticket.get("is_escalated"),
                "tags": ticket.get("tags", []),
                "cc_emails": ticket.get("cc_emails", []),
                "fwd_emails": ticket.get("fwd_emails", []),
                "reply_cc_emails": ticket.get("reply_cc_emails", []),
                "ticket_cc_emails": ticket.get("ticket_cc_emails", []),
                "requester_id": ticket.get("requester_id"),
                "responder_id": ticket.get("responder_id"),
                "group_id": ticket.get("group_id"),
                "product_id": ticket.get("product_id"),
                "company_id": ticket.get("company_id"),
                "custom_fields": ticket.get("custom_fields", {}),
                "ticket_summary": ticket.get("custom_fields", {}).get("ticket_summary", None),
                "link": f"https://{self.domain}.freshdesk.com/helpdesk/tickets/{ticket.get('id')}"
            }
            
            # Get conversations
            conversations = self._get_ticket_conversations(ticket_id)
            ticket_details["conversations"] = conversations
            ticket_details["conversations_count"] = len(conversations)
        
        return ticket_details
    
    def _get_ticket_conversations(self, ticket_id: int) -> List[Dict[str, Any]]:
        """
        Fetch all conversations for a ticket with pagination support
        
        Args:
            ticket_id: The ID of the ticket
            
        Returns:
            List of conversation dictionaries
        """
        all_conversations = []
        page = 1
        per_page = 100
        
        while True:
            params = {
                "per_page": per_page,
                "page": page
            }
            
            response = self._make_request(f"tickets/{ticket_id}/conversations", params)
            conversations = response.json()
            
            if not conversations:
                break
            
            # Process and clean up conversations
            for conversation in conversations:
                processed_conversation = {
                    "id": conversation.get("id"),
                    #"body": conversation.get("body"),
                    #"body_text": conversation.get("body_text"),
                    "body_text_clean": parse_html_page_basic_less_strict(
                        conversation.get("body_text", "")
                    ) if conversation.get("body_text") else "",
                    "incoming": conversation.get("incoming"),
                    "private": conversation.get("private"),
                    "user_id": conversation.get("user_id"),
                    "support_email": conversation.get("support_email"),
                    "source": conversation.get("source"),
                    "created_at": conversation.get("created_at"),
                    "updated_at": conversation.get("updated_at"),
                    "to_emails": conversation.get("to_emails", []),
                    "from_email": conversation.get("from_email"),
                    "cc_emails": conversation.get("cc_emails", []),
                    "bcc_emails": conversation.get("bcc_emails", []),
                    "attachments": conversation.get("attachments", [])
                }
                all_conversations.append(processed_conversation)
            
            logger.info(f"Fetched {len(conversations)} conversations from page {page} for ticket {ticket_id}")
            
            # If we got less than the maximum per page, we've reached the end
            if len(conversations) < per_page:
                break
            
            page += 1
        
        return all_conversations
 
    def _get_status_name(self, status_id: Optional[int]) -> str:
        """Convert status ID to readable name"""
        if status_id is None:
            return "Unknown"
        
        status_map = {
            2: "Open",
            3: "Pending",
            4: "Resolved",
            5: "Closed",
            17: "Pending with CSM",
            19: "Pending with Cloud",
            18: "Pending with Customer",
            16: "Work in Progress"
        }
        return status_map.get(status_id, f"Unknown Status ({status_id})")
    
    def _get_priority_name(self, priority_id: Optional[int]) -> str:
        """Convert priority ID to readable name"""
        if priority_id is None:
            return "Unknown"
        
        priority_map = {
            1: "Low",
            2: "Medium",
            3: "High",
            4: "Urgent"
        }
        return priority_map.get(priority_id, f"Unknown Priority ({priority_id})")
    
    def _get_source_name(self, source_id: Optional[int]) -> str:
        """Convert source ID to readable name"""
        if source_id is None:
            return "Unknown"
        
        source_map = {
            1: "Email",
            2: "Portal",
            3: "Phone",
            7: "Chat",
            9: "Feedback Widget",
            10: "Outbound Email"
        }
        return source_map.get(source_id, f"Unknown Source ({source_id})")
 
    def _fix_freshdesk_query_operators(self, query: str) -> str:
        """
        Converts malformed Freshdesk query parts like created_at:'>2025-06-01'
        or created_at:>2025-06-01 to the correct format: created_at:>'2025-06-01'
        Also handles URL encoding issues with >= and <= operators
        """
        # Step 1: Normalize operators (convert >= to > and <= to <)
        query = re.sub(r'>=', '>', query)
        query = re.sub(r'<=', '<', query)

        # Step 2: Fix quoted operators (created_at:'>2025-06-01' → created_at:>'2025-06-01')
        query = re.sub(r"(\w+):'([><]=?)([^']+)'", r"\1:\2'\3'", query)

        # Step 3: Fix unquoted values (created_at:>2025-06-01 → created_at:>'2025-06-01')
        query = re.sub(r"(\w+):([><]=?)(\d{4}-\d{2}-\d{2})", r"\1:\2'\3'", query)

        return query

    def _replace_status_names_with_ids(self, query: str) -> str:
        """
        Replaces `status:'name1,name2,...'` with `status:id1 OR status:id2 ...` using TicketStatus enum.
        Other query parts remain unchanged.
        """

        name_to_status_value = {name.replace("_", " ").lower(): status.value for name, status in TicketStatus.__members__.items()}

        pattern = r"status:\'([^']+)\'"
        match = re.search(pattern, query)

        if not match:
            return query  # No status field to replace

        status_text = match.group(1)  # e.g., "open,Work in Progress"
        status_names = [s.strip().lower() for s in status_text.split(",")]

        # Convert to numeric status
        status_ids = []
        for name in status_names:
            if name in name_to_status_value:
                status_ids.append(f"status:{name_to_status_value[name]}")
            else:
                raise ValueError(f"Unknown status name: '{name}'")

        # Build correct OR chain
        status_replacement = " OR ".join(status_ids)

        # Replace in original query
        return re.sub(pattern, status_replacement, query)
  
    def _replace_priority_names_with_ids(self, query: str) -> str:
        """
        Replaces `priority:'name1,name2,...'` with `priority:id1 OR priority:id2 ...` using TicketPriority enum.
        Other query parts remain unchanged.
        """
        name_to_priority_value = {name.replace("_", " ").lower(): priority.value for name, priority in TicketPriority.__members__.items()}
        
        pattern = r"priority:\'([^']+)\'"
        match = re.search(pattern, query)
        
        
        if not match:
            return query  # No priority field to replace
        
        priority_text = match.group(1)  # e.g., "high,medium"
        priority_names = [p.strip().lower() for p in priority_text.split(",")]
        logger.info(f"priority_names: {priority_names}")

        
        priority_ids = []
        for name in priority_names:
            if name in name_to_priority_value:
                priority_ids.append(f"priority:{name_to_priority_value[name]}")
                logger.info(f"priority_ids: {priority_ids}")
            else:
                raise ValueError(f"Unknown priority name: '{name}'")
        
        priority_replacement = " OR ".join(priority_ids)
        
        return re.sub(pattern, priority_replacement, query)

    def _process_ticket_for_custom_tool(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process ticket data for custom tool response
        
        Args:
            ticket: Raw ticket data from Freshdesk API
            
        Returns:
            Processed ticket data
        """
        # Clean HTML content
        description_text = ""
        if ticket.get('description'):
            description_text = parse_html_page_basic_less_strict(ticket['description'])
        
        return {
            "id": ticket.get('id'),
            "subject": ticket.get('subject', ''),
            "description": description_text,
            "status": self._get_status_name(ticket.get('status')),
            "priority": self._get_priority_name(ticket.get('priority')),
            "type": ticket.get('type'),
            "source": self._get_source_name(ticket.get('source')),
            "created_at": ticket.get('created_at'),
            "updated_at": ticket.get('updated_at'),
            "due_by": ticket.get('due_by'),
            "fr_due_by": ticket.get('fr_due_by'),
            "is_escalated": ticket.get('is_escalated', False),
            "custom_fields": ticket.get('custom_fields', {}),
            "tags": ticket.get('tags', []),
            "cc_emails": ticket.get('cc_emails', []),
            "fwd_emails": ticket.get('fwd_emails', []),
            "reply_cc_emails": ticket.get('reply_cc_emails', []),
            "fr_escalated": ticket.get('fr_escalated', False),
            "spam": ticket.get('spam', False),
            "email_config_id": ticket.get('email_config_id'),
            "group_id": ticket.get('group_id'),
            "product_id": ticket.get('product_id'),
            "company_id": ticket.get('company_id'),
            "requester_id": ticket.get('requester_id'),
            "responder_id": ticket.get('responder_id'),
            "link": f"https://{self.domain}.freshdesk.com/helpdesk/tickets/{ticket.get('id')}"
        }

    # Custom tool implementation for search tickets and get ticket details     
    def search_tickets_custom_tool(self, **kwargs) -> Dict[str, Any]:
        try:
            # If ticket ID is provided, return specific ticket
            if 'id' in kwargs and kwargs['id']:
                ticket_data = self.get_ticket_details_custom_tool(kwargs['id'])
                return {
                    "total": 1,
                    "results": [ticket_data]
                }

            params = {}
            endpoint = "search/tickets"
            query = ""

            # Use direct query if passed (Freshdesk Query Language)
            if 'query' in kwargs and kwargs['query']:
                logger.info(f"query_parts: {kwargs['query']}")

                # Fix the query operators
                query = self._fix_freshdesk_query_operators(kwargs['query'])

                # Build the status query
                query = self._replace_status_names_with_ids(query)

                # Build the priority query
                query = self._replace_priority_names_with_ids(query)

            if not query:
                endpoint = "tickets"
            else:
                logger.info(f"endpoint: {endpoint}")
                params['query'] = f'"{query}"'  # wrap in double quotes for FQL

            # Handle pagination - get the requested page
            current_page = kwargs.get('page', 1)
            params['page'] = current_page

            logger.info(f"url: https://{self.domain}/api/v2/{endpoint} | params: {params}")
            response = self._make_request(endpoint, params)
                        
            if endpoint == "search/tickets":
                data = response.json()
                tickets = data.get("results", [])
                total = data.get("total", 0)
                logger.info(f"total: {total}")
                logger.info(f"tickets length: {len(tickets)}")
                    
            else:
                tickets = response.json()
                total = len(tickets)

            processed_tickets = [self._process_ticket_for_custom_tool(ticket) for ticket in tickets]
            logger.info(f"total length of processed_tickets: {len(processed_tickets)}")

            # Calculate pagination info
            per_page = 30  # Freshdesk default page size
            total_pages = (total + per_page - 1) // per_page  # Ceiling division
            has_next_page = current_page < total_pages
            has_previous_page = current_page > 1

            # Create a user-friendly summary
            summary = f"Showing page {current_page} of {total_pages} (tickets {((current_page-1)*per_page)+1}-{min(current_page*per_page, total)} of {total} total tickets)"
            if has_next_page:
                summary += f". Use page {current_page + 1} to see more tickets."
            if has_previous_page:
                summary += f" Use page {current_page - 1} to see previous tickets."
            
            return {
                "page": current_page,
                "total": total,
                "results": processed_tickets,
                "per_page": per_page,
                "total_pages": total_pages,
                "has_next_page": has_next_page,
                "has_previous_page": has_previous_page,
                "next_page": current_page + 1 if has_next_page else None,
                "previous_page": current_page - 1 if has_previous_page else None,
                "summary": summary
            }

        except Exception as e:
            logger.error(f"Error in search_tickets_custom_tool: {e}")
            return {
                "total": 0,
                "results": [],
                "error": str(e)
            }

    def get_ticket_details_custom_tool(self, ticket_id: int, include: Optional[str] = None) -> Dict[str, Any]:
        """
        Get ticket details for custom tool
        
        Args:
            ticket_id: Ticket ID
            include: Optional resources to include (conversations, company, requester)
            
        Returns:
            Dictionary with ticket details
        """
        try:
            # Build include parameter
            include_params = {}
            if include:
                include_params['include'] = include
            
            # Get ticket details
            response = self._make_request(f"tickets/{ticket_id}", include_params)
            ticket_data = response.json()
            
            result = {
                "ticket": self._process_ticket_for_custom_tool(ticket_data)
            }
            
            # Add included resources if requested
            if include and 'conversations' in include:
                conversations = self._get_ticket_conversations(ticket_id)
                result["conversations"] = conversations
            
            if include and 'company' in include and ticket_data.get('company_id'):
                # Get company details (if needed)
                result["company"] = {"id": ticket_data.get('company_id')}
            
            if include and 'requester' in include and ticket_data.get('requester_id'):
                # Get requester details (if needed)
                result["requester"] = {"id": ticket_data.get('requester_id')}
            
            return result
            
        except Exception as e:
            logger.error(f"Error in get_ticket_details_custom_tool: {e}")
            return {
                "ticket": {},
                "error": str(e)
            }