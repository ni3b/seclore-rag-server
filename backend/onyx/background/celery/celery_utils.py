from collections.abc import Generator
from collections.abc import Iterator
from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy.orm import Session

from onyx.configs.app_configs import MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE
from onyx.connectors.connector_runner import batched_doc_ids
from onyx.connectors.cross_connector_utils.rate_limit_wrapper import (
    rate_limit_builder,
)
from onyx.connectors.interfaces import BaseConnector
from onyx.connectors.interfaces import CheckpointedConnector
from onyx.connectors.interfaces import LoadConnector
from onyx.connectors.interfaces import PollConnector
from onyx.connectors.interfaces import SlimConnector
from onyx.connectors.models import Document
from onyx.db.connector_credential_pair import get_connector_credential_pair
from onyx.db.enums import ConnectorCredentialPairStatus
from onyx.db.enums import TaskStatus
from onyx.db.models import TaskQueueState
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface
from onyx.redis.redis_connector import RedisConnector
from onyx.server.documents.models import DeletionAttemptSnapshot
from onyx.utils.logger import setup_logger


logger = setup_logger()
PRUNING_CHECKPOINTED_BATCH_SIZE = 32


def _get_deletion_status(
    connector_id: int,
    credential_id: int,
    db_session: Session,
    tenant_id: str | None = None,
) -> TaskQueueState | None:
    """We no longer store TaskQueueState in the DB for a deletion attempt.
    This function populates TaskQueueState by just checking redis.
    """
    cc_pair = get_connector_credential_pair(
        connector_id=connector_id, credential_id=credential_id, db_session=db_session
    )
    if not cc_pair:
        return None

    redis_connector = RedisConnector(tenant_id, cc_pair.id)
    if redis_connector.delete.fenced:
        return TaskQueueState(
            task_id="",
            task_name=redis_connector.delete.fence_key,
            status=TaskStatus.STARTED,
        )

    if cc_pair.status == ConnectorCredentialPairStatus.DELETING:
        return TaskQueueState(
            task_id="",
            task_name=redis_connector.delete.fence_key,
            status=TaskStatus.PENDING,
        )

    return None


def get_deletion_attempt_snapshot(
    connector_id: int,
    credential_id: int,
    db_session: Session,
    tenant_id: str | None = None,
) -> DeletionAttemptSnapshot | None:
    deletion_task = _get_deletion_status(
        connector_id, credential_id, db_session, tenant_id
    )
    if not deletion_task:
        return None

    return DeletionAttemptSnapshot(
        connector_id=connector_id,
        credential_id=credential_id,
        status=deletion_task.status,
    )


def document_batch_to_ids(
    doc_batch: Iterator[list[Document]],
) -> Generator[set[str], None, None]:
    for doc_list in doc_batch:
        yield {doc.id for doc in doc_list}


def extract_ids_from_runnable_connector(
    runnable_connector: BaseConnector,
    callback: IndexingHeartbeatInterface | None = None,
) -> set[str]:
    """
    If the SlimConnector hasnt been implemented for the given connector, just pull
    all docs using the load_from_state and grab out the IDs.

    Optionally, a callback can be passed to handle the length of each document batch.
    """
    all_connector_doc_ids: set[str] = set()

    if isinstance(runnable_connector, SlimConnector):
        for metadata_batch in runnable_connector.retrieve_all_slim_documents():
            all_connector_doc_ids.update({doc.id for doc in metadata_batch})

    doc_batch_id_generator = None

    if isinstance(runnable_connector, LoadConnector):
        doc_batch_id_generator = document_batch_to_ids(
            runnable_connector.load_from_state()
        )
    elif isinstance(runnable_connector, PollConnector):
        start = datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp()
        end = datetime.now(timezone.utc).timestamp()
        doc_batch_id_generator = document_batch_to_ids(
            runnable_connector.poll_source(start=start, end=end)
        )
    elif isinstance(runnable_connector, CheckpointedConnector):
        start = datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp()
        end = datetime.now(timezone.utc).timestamp()
        checkpoint = runnable_connector.build_dummy_checkpoint()
        checkpoint_generator = runnable_connector.load_from_checkpoint(
            start=start, end=end, checkpoint=checkpoint
        )
        doc_batch_id_generator = batched_doc_ids(
            checkpoint_generator, batch_size=PRUNING_CHECKPOINTED_BATCH_SIZE
        )
    else:
        raise RuntimeError("Pruning job could not find a valid runnable_connector.")

    # this function is called per batch for rate limiting
    def doc_batch_processing_func(doc_batch_ids: set[str]) -> set[str]:
        return doc_batch_ids

    if MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE:
        doc_batch_processing_func = rate_limit_builder(
            max_calls=MAX_PRUNING_DOCUMENT_RETRIEVAL_PER_MINUTE, period=60
        )(lambda x: x)
    for doc_batch_ids in doc_batch_id_generator:
        if callback:
            if callback.should_stop():
                raise RuntimeError(
                    "extract_ids_from_runnable_connector: Stop signal detected"
                )

        all_connector_doc_ids.update(doc_batch_processing_func(doc_batch_ids))

        if callback:
            callback.progress("extract_ids_from_runnable_connector", len(doc_batch_ids))

    return all_connector_doc_ids


def celery_is_listening_to_queue(worker: Any, name: str) -> bool:
    """Checks to see if we're listening to the named queue"""

    # how to get a list of queues this worker is listening to
    # https://stackoverflow.com/questions/29790523/how-to-determine-which-queues-a-celery-worker-is-consuming-at-runtime
    queue_names = list(worker.app.amqp.queues.consume_from.keys())
    for queue_name in queue_names:
        if queue_name == name:
            return True

    return False


def celery_is_worker_primary(worker: Any) -> bool:
    """There are multiple approaches that could be taken to determine if a celery worker
    is 'primary', as defined by us. But the way we do it is to check the hostname set
    for the celery worker, which can be done on the
    command line with '--hostname'."""
    hostname = worker.hostname
    if hostname.startswith("primary"):
        return True

    return False
