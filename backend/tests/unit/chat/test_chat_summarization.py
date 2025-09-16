import pytest
from datetime import datetime
from uuid import UUID, uuid4
from unittest.mock import Mock, patch

from onyx.chat.chat_summarization import ChatSummarizer, ChatSummary
from onyx.db.models import ChatMessage, ChatSession, MessageType
from onyx.document_index.vespa.index import VespaIndex

@pytest.fixture
def mock_vespa_index():
    return Mock(spec=VespaIndex)

@pytest.fixture
def chat_summarizer(mock_vespa_index):
    return ChatSummarizer(mock_vespa_index)

@pytest.fixture
def sample_messages():
    messages = []
    for i in range(6):
        message = ChatMessage(
            id=uuid4(),
            message=f"Test message {i}",
            message_type=MessageType.USER if i % 2 == 0 else MessageType.ASSISTANT,
            created_at=datetime.now()
        )
        messages.append(message)
    return messages

@pytest.fixture
def sample_chat_session():
    return ChatSession(
        id=uuid4(),
        persona_id=1,
        created_at=datetime.now()
    )

def test_should_summarize_no_previous_summary(chat_summarizer, sample_messages):
    assert chat_summarizer.should_summarize(sample_messages, None) is True

def test_should_summarize_with_previous_summary(chat_summarizer, sample_messages):
    previous_summary = ChatSummary(
        chat_session_id=uuid4(),
        user_id=uuid4(),
        assistant_id=1,
        last_message_id=sample_messages[2].id,
        summary="Previous summary",
        created_at=datetime.now()
    )
    assert chat_summarizer.should_summarize(sample_messages, previous_summary) is True

def test_should_not_summarize_insufficient_messages(chat_summarizer, sample_messages):
    previous_summary = ChatSummary(
        chat_session_id=uuid4(),
        user_id=uuid4(),
        assistant_id=1,
        last_message_id=sample_messages[4].id,
        summary="Previous summary",
        created_at=datetime.now()
    )
    assert chat_summarizer.should_summarize(sample_messages, previous_summary) is False

@patch('onyx.chat.chat_summarization.get_llms_for_persona')
@patch('onyx.chat.chat_summarization.get_persona_by_id')
def test_generate_summary_with_llm(mock_get_persona, mock_get_llms, chat_summarizer, sample_messages):
    # Mock persona
    mock_persona = Mock()
    mock_get_persona.return_value = mock_persona

    # Mock LLM
    mock_llm = Mock()
    mock_llm.complete.return_value = "Generated summary"
    mock_get_llms.return_value = (mock_llm, None)

    # Mock db_session
    mock_db_session = Mock()

    summary = chat_summarizer.generate_summary(sample_messages, mock_db_session)
    assert summary == "Generated summary"
    mock_llm.complete.assert_called_once()

def test_generate_summary_fallback(chat_summarizer, sample_messages):
    # Mock db_session
    mock_db_session = Mock()
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    summary = chat_summarizer.generate_summary(sample_messages, mock_db_session)
    assert summary == " ".join([msg.message for msg in sample_messages])

def test_get_context_for_response_no_summary(chat_summarizer, sample_chat_session, sample_messages):
    context = chat_summarizer.get_context_for_response(
        chat_session=sample_chat_session,
        messages=sample_messages,
        system_message="System message"
    )
    assert context["summary"] is None
    assert len(context["context_messages"]) == 4
    assert len(context["remaining_messages"]) == 2

def test_get_context_for_response_with_summary(chat_summarizer, sample_chat_session, sample_messages):
    previous_summary = ChatSummary(
        chat_session_id=sample_chat_session.id,
        user_id=uuid4(),
        assistant_id=1,
        last_message_id=sample_messages[2].id,
        summary="Previous summary",
        created_at=datetime.now()
    )
    
    with patch.object(chat_summarizer, 'get_latest_summary', return_value=previous_summary):
        context = chat_summarizer.get_context_for_response(
            chat_session=sample_chat_session,
            messages=sample_messages,
            system_message="System message"
        )
        assert context["summary"] == "Previous summary"
        assert len(context["context_messages"]) == 3
        assert len(context["remaining_messages"]) == 3 