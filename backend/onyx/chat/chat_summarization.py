from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
import json
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from onyx.document_index.vespa.index import VespaIndex
from onyx.document_index.vespa.shared_utils.utils import get_vespa_http_client
from onyx.document_index.vespa_constants import DOCUMENT_ID_ENDPOINT, SEARCH_ENDPOINT
from onyx.db.models import ChatMessage, ChatSession, Persona
from onyx.connectors.models import Document, Section, BasicExpertInfo, IndexAttemptMetadata
from onyx.configs.constants import DocumentSource, MessageType
from onyx.configs.chat_configs import CHAT_SUMMARIZATION_THRESHOLD
from onyx.utils.logger import setup_logger
from onyx.llm.factory import get_llms_for_persona, get_default_llms
from onyx.llm.models import PreviousMessage
from onyx.db.persona import get_persona_by_id
from onyx.document_index.vespa.index import IndexBatchParams
from onyx.indexing.models import DocMetadataAwareIndexChunk, ChunkEmbedding, DocAwareChunk
from onyx.access.models import DocumentAccess
from onyx.configs.constants import DEFAULT_BOOST
from onyx.indexing.indexing_pipeline import index_doc_batch
from onyx.indexing.embedder import DefaultIndexingEmbedder
from onyx.indexing.chunker import Chunker
from onyx.natural_language_processing.utils import get_tokenizer
from onyx.db.search_settings import get_current_search_settings

logger = setup_logger()

def _safe_parse_message_id(value: str) -> int:
    """Safely parse message ID from string, handling both UUID and integer formats"""
    try:
        # First try to parse as integer
        return int(value)
    except ValueError:
        # If that fails, check if it's a UUID and extract a hash-based integer
        try:
            uuid_obj = UUID(value)
            # Convert UUID to a consistent integer representation
            # Using hash() to get a deterministic integer from UUID
            return abs(hash(str(uuid_obj))) % (10**9)  # Keep it within reasonable range
        except ValueError:
            # If both fail, log warning and return 0
            logger.warning(f"Failed to parse message ID '{value}' as either int or UUID, using 0")
            return 0

class ChatSummary(BaseModel):
    chat_session_id: UUID
    user_id: UUID
    assistant_id: int
    last_message_id: int  # Changed from UUID to int since message IDs are integers
    last_message_number: int
    summary: str
    created_at: datetime
    # New fields for incremental summarization
    message_count_at_creation: int
    summary_version: int = 1

class ChatSummarizer:
    def __init__(self, vespa_index: VespaIndex):
        self.vespa_index = vespa_index
        self.summary_chunk_size = 1000  # Adjust based on your needs
        self.messages_per_summary_trigger = CHAT_SUMMARIZATION_THRESHOLD

    def _create_summary_document(self, summary: ChatSummary) -> Dict[str, Any]:
        """Create a Vespa document for the chat summary"""
        return {
            "fields": {
                "chat_session_id": str(summary.chat_session_id),
                "user_id": str(summary.user_id),
                "assistant_id": str(summary.assistant_id),
                "last_message_id": str(summary.last_message_id),
                "last_message_number": str(summary.last_message_number),
                "summary": summary.summary,
                "created_at": summary.created_at.isoformat(),
                "document_type": "chat_summary",
                "message_count_at_creation": str(summary.message_count_at_creation),
                "summary_version": str(summary.summary_version)
            }
        }

    def store_summary(self, summary: ChatSummary, user_email: str, document_index, db_session) -> None:
        """Store or update the chat summary as a document in Vespa"""
        try:
            # Use a consistent document ID for the same chat session to enable updates
            doc_id = f"chat_summary_{summary.chat_session_id}"
            logger.info(f"Storing/updating summary for chat_session_id={summary.chat_session_id}, version={summary.summary_version}")
            
            doc = Document(
                id=doc_id,
                sections=[Section(link=None, text=summary.summary)],
                source=DocumentSource.CHAT_SUMMARY,
                semantic_identifier=f"Chat Summary for {summary.chat_session_id} (v{summary.summary_version})",
                doc_updated_at=summary.created_at.replace(tzinfo=timezone.utc),
                primary_owners=[BasicExpertInfo(display_name="Chat User", email=user_email)] if user_email else None,
                metadata={
                    "chat_session_id": str(summary.chat_session_id),
                    "user_id": str(summary.user_id),
                    "assistant_id": str(summary.assistant_id),
                    "last_message_id": str(summary.last_message_id),
                    "last_message_number": str(summary.last_message_number),
                    "document_type": "chat_summary",
                    "created_at": summary.created_at.isoformat(),
                    "message_count_at_creation": str(summary.message_count_at_creation),
                    "summary_version": str(summary.summary_version)
                }
            )
            logger.info(f"Document created: {doc}")

            # Get search settings and embedder
            search_settings = get_current_search_settings(db_session)
            embedder = DefaultIndexingEmbedder.from_db_search_settings(search_settings)
            tokenizer = get_tokenizer(model_name=embedder.model_name, provider_type=embedder.provider_type)
            chunker = Chunker(tokenizer)
            logger.info(f"Chunker created: {chunker}")
            # Chunk the document
            chunks: list[DocAwareChunk] = chunker.chunk([doc])
            logger.info(f"Chunks created: {chunks}")
            # Embed the chunks
            embedded_chunks = embedder.embed_chunks(chunks)
            logger.info(f"Embedded chunks created: {embedded_chunks}")
            # Convert to DocMetadataAwareIndexChunk
            access = DocumentAccess.build(
                user_emails=[user_email] if user_email else [],
                user_groups=[],
                external_user_emails=[],
                external_user_group_ids=[],
                is_public=False
            )
            docmeta_chunks = [
                DocMetadataAwareIndexChunk.from_index_chunk(
                    index_chunk=chunk,
                    access=access,
                    document_sets=set(),
                    boost=DEFAULT_BOOST,
                    tenant_id=None
                )
                for chunk in embedded_chunks
            ]

            # Prepare index batch params - this will replace/update the existing document
            index_batch_params = IndexBatchParams(
                doc_id_to_previous_chunk_cnt={doc_id: None},  # Let Vespa handle the update
                doc_id_to_new_chunk_cnt={doc_id: len(docmeta_chunks)},
                tenant_id=None,
                large_chunks_enabled=False
            )

            # Index directly to Vespa (this will update the existing document)
            document_index.index(docmeta_chunks, index_batch_params)
            logger.info(f"Document indexed: {docmeta_chunks}")
            logger.info(f"Successfully stored/updated chat summary as document for session {summary.chat_session_id}")
        except Exception as e:
            logger.error(f"Failed to store chat summary as document: {str(e)}")
            raise

    def get_latest_summary(self, chat_session_id: UUID) -> Optional[ChatSummary]:
        """Retrieve the latest summary for a chat session"""
        try:
            # Use the correct index name and metadata_list format for querying
            yql = f'select * from sources {self.vespa_index.index_name} where (metadata_list contains "chat_session_id==={chat_session_id}") and (metadata_list contains "document_type===chat_summary")'
            with get_vespa_http_client() as http_client:
                response = http_client.get(
                    SEARCH_ENDPOINT,
                    params={"yql": yql}
                )
                response.raise_for_status()
                result = response.json()
                
                if not result.get("root", {}).get("children"):
                    return None
                
                # Get the most recent summary by parsing metadata from all results
                summaries = []
                for child in result["root"]["children"]:
                    fields = child["fields"]
                    
                    # Parse metadata from the metadata field (JSON string)
                    metadata_str = fields.get("metadata", "{}")
                    try:
                        metadata = json.loads(metadata_str)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse metadata: {metadata_str}")
                        continue
                    
                    # Extract summary data from metadata
                    try:
                        summary = ChatSummary(
                            chat_session_id=UUID(metadata["chat_session_id"]),
                            user_id=UUID(metadata["user_id"]),
                            assistant_id=int(metadata["assistant_id"]),
                            last_message_id=_safe_parse_message_id(metadata["last_message_id"]),
                            last_message_number=_safe_parse_message_id(metadata["last_message_number"]),
                            summary=fields.get("content", ""),  # The actual summary text is in content field
                            created_at=datetime.fromisoformat(metadata["created_at"]),
                            message_count_at_creation=int(metadata.get("message_count_at_creation", 0)),
                            summary_version=int(metadata.get("summary_version", 1))
                        )
                        summaries.append(summary)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Failed to parse summary from metadata: {e}")
                        continue
                
                # Return the summary with the highest summary_version
                if summaries:
                    return max(summaries, key=lambda s: s.summary_version)
                return None
                
        except Exception as e:
            logger.error(f"Failed to retrieve chat summary: {str(e)}")
            return None

    def generate_summary(self, persona_id: int, messages: List[ChatMessage], db_session: Session, 
                        existing_summary: Optional[str] = None) -> str:
        """Generate a summary of chat messages using an LLM, optionally updating an existing summary"""
        try:
            # Get the persona for summarization
            persona = get_persona_by_id(
                persona_id=persona_id,
                user=None,
                db_session=db_session,
                is_for_edit=False
            )
            
            # Get LLM for summarization - try persona-specific first, then default
            llm = None
            try:
                if persona:
                    llm, _ = get_llms_for_persona(
                        persona=persona,
                        llm_override=None,
                        additional_headers=None
                    )
                else:
                    logger.info("No persona found, using default LLMs")
                    llm, _ = get_default_llms()
                    
            except Exception as persona_llm_error:
                logger.warning(f"Failed to get persona-specific LLM: {str(persona_llm_error)}, falling back to default LLM")
                try:
                    llm, _ = get_default_llms()
                except Exception as default_llm_error:
                    logger.error(f"Failed to get default LLM: {str(default_llm_error)}")
                    raise RuntimeError(f"No LLM provider available for summarization: {str(default_llm_error)}")
                
            if not llm:
                logger.error("No LLM returned from get_llms_for_persona or get_default_llms")
                raise RuntimeError("No LLM provider available for summarization")

            # Prepare messages for summarization
            formatted_messages = []
            for msg in messages:
                role = "user" if msg.message_type == MessageType.USER else "assistant"
                formatted_messages.append(f"{role}: {msg.message}")

            # Create summarization prompt based on whether we're updating or creating new
            if existing_summary:
                # Update existing summary with new messages
                summarization_prompt = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that updates conversation summaries. When provided with an existing summary and new messages, create an updated summary that incorporates the new information while maintaining context and key points from the previous summary."
                    },
                    {
                        "role": "user",
                        "content": f"""Please update the following conversation summary with the new messages provided. Keep the context and key information from the existing summary, and incorporate the main points from the new messages.

Existing Summary:
{existing_summary}

New Messages:
{chr(10).join(formatted_messages)}

Updated Summary:"""
                    }
                ]
            else:
                # Create new summary
                summarization_prompt = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that summarizes conversations. Provide concise summaries focusing on main points and key information. Keep the context as it is and mostly keep the user messages as they are."
                    },
                    {
                        "role": "user",
                        "content": f"""Please summarize the following conversation, focusing on the main points and key information exchanged:

{chr(10).join(formatted_messages)}

Summary:"""
                    }
                ]

            # Generate summary using LLM
            response = llm.invoke(
                prompt=summarization_prompt
            )

            summary = response.content.strip()
            logger.info(f"[SUMMARY {'UPDATED' if existing_summary else 'CREATED'}] {summary}")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary using LLM: {str(e)}")
            raise RuntimeError(f"Chat summarization failed: {str(e)}")

    def _create_fallback_summary(self, messages: List[ChatMessage], existing_summary: Optional[str] = None) -> str:
        """This method is removed - we now strictly require LLM for summarization"""
        raise RuntimeError("Fallback summary creation is disabled - LLM is required for summarization")

    def should_summarize(self, messages: List[ChatMessage], last_summary: Optional[ChatSummary]) -> bool:
        """Determine if messages should be summarized based on the configured threshold"""
        # If threshold is 0, summarization is disabled
        if self.messages_per_summary_trigger == 0:
            return False
            
        total_messages = len(messages)
        
        if not last_summary:
            # Create first summary when we have enough messages
            return total_messages >= self.messages_per_summary_trigger
        
        # Update summary when we have enough new messages since last summary
        messages_since_last_summary = total_messages - last_summary.message_count_at_creation
        return messages_since_last_summary >= self.messages_per_summary_trigger

    def get_context_for_response(
        self,
        chat_session: ChatSession,
        messages: List[ChatMessage],
        system_message: str
    ) -> Dict[str, Any]:
        """Get the context for generating a response in the new format:
        system message > summary > 3rd last message > 2nd last message > last message
        If summarization is disabled, return all messages for normal chat behavior.
        """
        # If summarization is disabled, use all messages (normal chat behavior)
        if self.messages_per_summary_trigger == 0:
            return {
                "system_message": system_message,
                "summary": None,
                "context_messages": messages,
                "remaining_messages": [],
                "messages_to_summarize": []
            }
        
        last_summary = self.get_latest_summary(chat_session.id)
        
        if not last_summary:
            # If no summary exists, use all messages (up to reasonable limit)
            return {
                "system_message": system_message,
                "summary": None,
                "context_messages": messages,
                "remaining_messages": [],
                "messages_to_summarize": []
            }
        else:
            logger.info(f"[SUMMARY SENT] {last_summary.summary}")
            # Use system message, summary, and last 3 messages
            # Messages to include in context (last 3)
            context_messages = messages[-3:] if len(messages) >= 3 else messages
            
            # Messages that were used to create the current summary
            messages_in_summary = messages[:last_summary.message_count_at_creation]
            
            # New messages since the last summary (for potential new summary creation)
            new_messages_since_summary = messages[last_summary.message_count_at_creation:]
            
            return {
                "system_message": system_message,
                "summary": last_summary.summary,
                "context_messages": context_messages,
                "remaining_messages": messages_in_summary,  # Messages already in summary
                "messages_to_summarize": new_messages_since_summary  # New messages to potentially summarize
            }

    def create_or_update_summary(
        self,
        chat_session: ChatSession,
        messages: List[ChatMessage],
        user_email: str,
        document_index,
        db_session: Session
    ) -> Optional[str]:
        """Create a new summary or update existing one based on message count"""
        # If summarization is disabled, return None
        if self.messages_per_summary_trigger == 0:
            return None
            
        last_summary = self.get_latest_summary(chat_session.id)
        total_messages = len(messages)
        
        if not self.should_summarize(messages, last_summary):
            return last_summary.summary if last_summary else None
        
        if not last_summary:
            # Create first summary
            messages_to_summarize = messages
            existing_summary_text = None
            new_version = 1
            logger.info(f"Creating first summary for chat_session_id={chat_session.id} with {len(messages_to_summarize)} messages")
        else:
            # Update existing summary with new messages
            new_messages = messages[last_summary.message_count_at_creation:]
            messages_to_summarize = new_messages
            existing_summary_text = last_summary.summary
            new_version = last_summary.summary_version + 1
            logger.info(f"Updating summary for chat_session_id={chat_session.id} with {len(new_messages)} new messages (version {new_version})")
        
        # Generate new or updated summary
        summary_text = self.generate_summary(
            chat_session.persona.id, 
            messages_to_summarize, 
            db_session,
            existing_summary_text
        )
        
        # Create summary object
        chat_summary = ChatSummary(
            chat_session_id=chat_session.id,
            user_id=chat_session.user_id,
            assistant_id=chat_session.persona_id,
            last_message_id=messages[-1].id,
            last_message_number=messages[-1].id,
            summary=summary_text,
            created_at=datetime.now(),
            message_count_at_creation=total_messages,
            summary_version=new_version
        )
        
        # Store/update the summary
        self.store_summary(chat_summary, user_email, document_index, db_session)
        logger.info(f"Summary {'created' if new_version == 1 else 'updated'} for chat_session_id={chat_session.id}")
        
        return summary_text

    def store_summary_as_document(
        self,
        chat_session_id,
        user_id,
        assistant_id,
        last_message_id,
        last_message_number,
        summary,
        user_email,
        document_index
    ):
        """Legacy method - kept for backward compatibility"""
        doc = Document(
            id=f"chat_summary_{chat_session_id}_{last_message_number}",
            sections=[Section(link=None, text=summary)],
            source=DocumentSource.CHAT_SUMMARY,
            semantic_identifier=f"Chat Summary for {chat_session_id}",
            doc_updated_at=datetime.now(timezone.utc),
            primary_owners=[BasicExpertInfo(display_name="Chat User", email=user_email)],
            metadata={
                "chat_session_id": str(chat_session_id),
                "user_id": str(user_id),
                "assistant_id": str(assistant_id),
                "last_message_id": str(last_message_id),
                "last_message_number": last_message_number,
                "document_type": "chat_summary"
            }
        )
        document_index.index([doc]) 