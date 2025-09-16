import datetime
from uuid import UUID
from collections import defaultdict
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import case, func, select, and_

from onyx.utils.logger import setup_logger
from onyx.configs.constants import MessageType
from onyx.db.models import (
    ChatMessage,
    ChatMessageFeedback,
    ChatSession,
    DocumentSet,
    ConnectorCredentialPair,
    SearchDoc,
    ChatMessage__SearchDoc,
    DocumentByConnectorCredentialPair,
    User,
    Persona
)
logger = setup_logger()


def fetch_bucketed_core_metrics(
    db_session: Session,
    start: datetime.datetime,
    end: datetime.datetime,
    bucket: str = "day",
) -> list[tuple[datetime.datetime, int, int, int, int, int]]:
    """
    Returns per-bucket metrics for the range [start, end]:
      (bucket_start, active_users, queries, input_tokens, output_tokens, dislikes)

    Definitions:
      - active_users: distinct ChatSession.user_id that had any ChatMessage in the bucket
      - queries: ChatMessage count where message_type == MessageType.USER
      - input_tokens: SUM(token_count) for USER + SYSTEM messages
      - output_tokens: SUM(token_count) for ASSISTANT messages
      - dislikes: count of ChatMessageFeedback rows where is_positive == False
                  joined to ASSISTANT messages in the bucket

    bucket: one of "day", "week", or "month" → uses PostgreSQL date_trunc.
    """

    if bucket not in {"day", "week", "month"}:
        raise ValueError("bucket must be one of 'day', 'week', or 'month'")

    bucket_trunc = func.date_trunc(bucket, ChatMessage.time_sent).label("bucket_start")

    # Messages in range
    msg_subq = (
        select(
            bucket_trunc,
            ChatMessage.id.label("cm_id"),
            ChatMessage.chat_session_id.label("cs_id"),
            ChatMessage.token_count.label("tokens"),
            ChatMessage.message_type.label("mt"),
        )
        .where(ChatMessage.time_sent >= start)
        .where(ChatMessage.time_sent <= end)
        .subquery()
    )

    # Join sessions + feedback
    sess_subq = (
        select(
            msg_subq.c.bucket_start,
            ChatSession.id.label("session_id"),
            ChatSession.user_id.label("user_id"),
            msg_subq.c.cm_id,
            msg_subq.c.tokens,
            msg_subq.c.mt,
            ChatMessageFeedback.is_positive.label("is_positive"),
        )
        .join(ChatSession, ChatSession.id == msg_subq.c.cs_id)
        .outerjoin(ChatMessageFeedback, ChatMessageFeedback.chat_message_id == msg_subq.c.cm_id)
        .subquery()
    )

    # Aggregation per bucket
    stmt = (
        select(
            sess_subq.c.bucket_start,
            func.count(func.distinct(sess_subq.c.user_id)).label("active_users"),
            func.sum(case((sess_subq.c.mt == MessageType.USER, 1), else_=0)).label("queries"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            sess_subq.c.mt.in_([MessageType.USER, MessageType.SYSTEM]),
                            sess_subq.c.tokens,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("input_tokens"),
            func.coalesce(
                func.sum(
                    case((sess_subq.c.mt == MessageType.ASSISTANT, sess_subq.c.tokens), else_=0)
                ),
                0,
            ).label("output_tokens"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (sess_subq.c.mt == MessageType.ASSISTANT)
                            & (sess_subq.c.is_positive == False),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("dislikes"),
        )
        .group_by(sess_subq.c.bucket_start)
        .order_by(sess_subq.c.bucket_start)
    )

    rows = db_session.execute(stmt).all()
    # each row = (bucket_start, active_users, queries, input_tokens, output_tokens, dislikes)
    return [tuple(row) for row in rows]


def fetch_core_metrics_totals(
    db_session: Session, start: datetime.datetime, end: datetime.datetime
) -> tuple[int, int, int, int, int, int]:
    """
    Totals over the full range [start, end]:
      (active_users, queries, input_tokens, output_tokens, likes, dislikes)

    Definitions:
      - active_users: distinct ChatSession.user_id that had any ChatMessage in the range
      - queries: ChatMessage count where message_type == MessageType.USER
      - input_tokens: SUM(token_count) for USER + SYSTEM messages
      - output_tokens: SUM(token_count) for ASSISTANT messages
      - likes: ChatMessageFeedback.is_positive == True
      - dislikes: ChatMessageFeedback.is_positive == False
    """

    # Step 1: aggregate tokens & queries (messages only, no feedback join)
    base_metrics = (
        select(
            func.count(func.distinct(ChatSession.user_id)).label("active_users"),
            func.coalesce(
                func.sum(
                    case((ChatMessage.message_type == MessageType.USER, 1), else_=0)
                ),
                0,
            ).label("queries"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            ChatMessage.message_type.in_([MessageType.USER, MessageType.SYSTEM]),
                            ChatMessage.token_count,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("input_tokens"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            ChatMessage.message_type == MessageType.ASSISTANT,
                            ChatMessage.token_count,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("output_tokens"),
        )
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(ChatMessage.time_sent >= start, ChatMessage.time_sent <= end)
    ).subquery()

    # Step 2: aggregate feedback (ensure always one row using outer join)
    feedback_metrics = (
        select(
            func.coalesce(
                func.sum(case((ChatMessageFeedback.is_positive == True, 1), else_=0)), 0
            ).label("likes"),
            func.coalesce(
                func.sum(case((ChatMessageFeedback.is_positive == False, 1), else_=0)), 0
            ).label("dislikes"),
        )
        .select_from(ChatMessage)  # ensure we always have a row, even if no feedback
        .outerjoin(
            ChatMessageFeedback,
            ChatMessage.id == ChatMessageFeedback.chat_message_id,
        )
        .where(ChatMessage.time_sent >= start, ChatMessage.time_sent <= end)
    ).subquery()

    # Step 3: cross join both (safe because both subqueries now always return one row)
    stmt = select(
        base_metrics.c.active_users,
        base_metrics.c.queries,
        base_metrics.c.input_tokens,
        base_metrics.c.output_tokens,
        feedback_metrics.c.likes,
        feedback_metrics.c.dislikes,
    )

    active_users, queries, input_tokens, output_tokens, likes, dislikes = (
        db_session.execute(stmt).one()
    )

    return (
        int(active_users or 0),
        int(queries or 0),
        int(input_tokens or 0),
        int(output_tokens or 0),
        int(likes or 0),
        int(dislikes or 0),
    )



def fetch_assistant_usage_totals(
    db_session: Session,
    start: datetime.datetime,
    end: datetime.datetime,
) -> list[tuple[int, str, int, int, int, int]]:
    """
    Returns aggregated usage metrics per assistant (persona) in the given time range.
    Each row: (assistant_id, assistant_name, messages, users, dislikes, tokens)
    """

    query = (
        select(
            Persona.id,
            Persona.name,
            # Total assistant messages
            func.count(ChatMessage.id).label("messages"),
            # Distinct users per assistant
            func.count(func.distinct(ChatSession.user_id)).label("users"),
            # Total dislikes
            func.coalesce(
                func.sum(
                    case((ChatMessageFeedback.is_positive == False, 1), else_=0)
                ),
                0,
            ).label("dislikes"),
            # Total tokens
            func.coalesce(func.sum(ChatMessage.token_count), 0).label("tokens"),
        )
        .join(ChatSession, ChatSession.persona_id == Persona.id)
        .outerjoin(ChatMessage, ChatMessage.chat_session_id == ChatSession.id)
        .outerjoin(
            ChatMessageFeedback,
            ChatMessageFeedback.chat_message_id == ChatMessage.id,
        )
        .where(
            ChatMessage.time_sent >= start,
            ChatMessage.time_sent <= end,
            ChatMessage.message_type == MessageType.ASSISTANT,
        )
        .group_by(Persona.id, Persona.name)
        .order_by(Persona.name)
    )

    return [tuple(row) for row in db_session.execute(query).all()]

def fetch_user_assistant_usage(
    db_session: Session,
    start: datetime.datetime,
    end: datetime.datetime,
) -> List[Dict[str, Any]]:
    """
    Returns aggregated and pivoted usage metrics for each user.

    The output is a list of dictionaries, one for each user, with columns
    dynamically created for each assistant's metrics (Queries, Tokens, Likes, Dislikes)
    plus overall totals for each user.
    """

    # 1. Fetch raw, unpivoted data with all necessary metrics
    raw_usage_query = (
        select(
            User.email.label("user_email"),
            Persona.name.label("assistant_name"),
            func.sum(case((ChatMessage.message_type == MessageType.USER, 1), else_=0)).label("queries"),
            func.coalesce(func.sum(ChatMessage.token_count), 0).label("tokens"),
            func.coalesce(func.sum(case((ChatMessageFeedback.is_positive == True, 1), else_=0)), 0).label("likes"),
            func.coalesce(func.sum(case((ChatMessageFeedback.is_positive == False, 1), else_=0)), 0).label("dislikes"),
        )
        .join(ChatSession, ChatSession.user_id == User.id)
        .join(Persona, Persona.id == ChatSession.persona_id)
        .join(ChatMessage, ChatMessage.chat_session_id == ChatSession.id)
        .outerjoin(ChatMessageFeedback, ChatMessageFeedback.chat_message_id == ChatMessage.id)
        .where(ChatMessage.time_sent >= start, ChatMessage.time_sent <= end)
        .group_by(User.email, Persona.name)
    )

    raw_results = db_session.execute(raw_usage_query).mappings().all()

    # Get unique assistant list
    all_assistants = sorted({row["assistant_name"] for row in raw_results})

    # 2. Process into pivot structure
    users_data = defaultdict(
        lambda: {"total_tokens": 0, "total_queries": 0, "total_likes": 0, "total_dislikes": 0}
    )

    for row in raw_results:
        user_email = row["user_email"]
        assistant_name = row["assistant_name"]

        # Store assistant metrics
        users_data[user_email][assistant_name] = {
            "queries": row["queries"],
            "tokens": row["tokens"],
            "likes": row["likes"],
            "dislikes": row["dislikes"],
        }

        # Update totals
        users_data[user_email]["total_queries"] += row["queries"]
        users_data[user_email]["total_tokens"] += row["tokens"]
        users_data[user_email]["total_likes"] += row["likes"]
        users_data[user_email]["total_dislikes"] += row["dislikes"]

    # 3. Flatten into final list
    final_report = []
    for email, data in users_data.items():
        user_row = {"user_email": email}

        for assistant in all_assistants:
            stats = data.get(assistant, {"queries": 0, "tokens": 0, "likes": 0, "dislikes": 0})
            user_row[f"{assistant}_Queries"] = stats["queries"]
            user_row[f"{assistant}_Total_Token"] = stats["tokens"]  # singular to match docstring
            user_row[f"{assistant}_Total_Likes"] = stats["likes"]
            user_row[f"{assistant}_Total_Dislikes"] = stats["dislikes"]

        user_row["total_queries"] = data["total_queries"]
        user_row["total_tokens"] = data["total_tokens"]
        user_row["total_likes"] = data["total_likes"]
        user_row["total_dislikes"] = data["total_dislikes"]

        final_report.append(user_row)

    return final_report


def fetch_kb_assistant_usage(
    db_session: Session,
    start: datetime.datetime,
    end: datetime.datetime,
) -> List[Dict[str, Any]]:
    """
    Returns aggregated and pivoted usage metrics for each knowledge base.

    The output is a list of dictionaries, one for each KB, with columns
    dynamically created for each assistant's metrics (Requests and Tokens),
    followed by overall totals for each KB.
    """

    # 1. Fetch raw, unpivoted data
    raw_usage_query = (
        select(
            ConnectorCredentialPair.name.label("cc_pair_name"),
            Persona.name.label("assistant_name"),
            func.count(func.distinct(ChatMessage.id)).label("accurate_request_count"),
        )
        .join(ChatSession, ChatMessage.chat_session_id == ChatSession.id)
        .join(Persona, ChatSession.persona_id == Persona.id)
        .join(ChatMessage__SearchDoc, ChatMessage.id == ChatMessage__SearchDoc.chat_message_id)
        .join(SearchDoc, ChatMessage__SearchDoc.search_doc_id == SearchDoc.id)
        .join(DocumentByConnectorCredentialPair, SearchDoc.document_id == DocumentByConnectorCredentialPair.id)
        .join(
            ConnectorCredentialPair,
            and_(
                DocumentByConnectorCredentialPair.connector_id == ConnectorCredentialPair.connector_id,
                DocumentByConnectorCredentialPair.credential_id == ConnectorCredentialPair.credential_id,
            ),
        )
        .where(
            ChatMessage.message_type == MessageType.ASSISTANT,
            ChatMessage.time_sent >= start,
            ChatMessage.time_sent <= end,
        )
        .group_by(ConnectorCredentialPair.name, Persona.name)
        .order_by(ConnectorCredentialPair.name, Persona.name)
    )

    raw_results = db_session.execute(raw_usage_query).mappings().all()

    # Get all unique assistants
    all_assistants = sorted({row["assistant_name"] for row in raw_results})

    # 2. Process into nested structure
    kbs_data = defaultdict(lambda: {"total_requests": 0})

    for row in raw_results:
        kb_name = row["cc_pair_name"]
        assistant_name = row["assistant_name"]

        requests = row["accurate_request_count"]
        kbs_data[kb_name][assistant_name] = {
            "requests": requests,
        }

        kbs_data[kb_name]["total_requests"] += requests

    # 3. Flatten into final report
    final_report = []
    for kb_name, data in kbs_data.items():
        kb_row = {"knowledge_base": kb_name}

        for assistant in all_assistants:
            stats = data.get(assistant, {"requests": 0})
            kb_row[f"{assistant}_Number of requests"] = stats["requests"]

        kb_row["Total Number of requests"] = data["total_requests"]

        final_report.append(kb_row)

    return final_report
