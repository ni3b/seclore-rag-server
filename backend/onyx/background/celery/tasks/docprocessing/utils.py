import time
from datetime import datetime
from datetime import timezone
from uuid import uuid4

from celery import Celery
from redis import Redis
from redis.exceptions import LockError
from redis.lock import Lock as RedisLock
from sqlalchemy.orm import Session

from onyx.background.celery.apps.app_base import task_logger
from onyx.configs.app_configs import DISABLE_INDEX_UPDATE_ON_SWAP
from onyx.configs.constants import CELERY_GENERIC_BEAT_LOCK_TIMEOUT
from onyx.configs.constants import DANSWER_REDIS_FUNCTION_LOCK_PREFIX
from onyx.configs.constants import DocumentSource
from onyx.configs.constants import OnyxCeleryPriority
from onyx.configs.constants import OnyxCeleryQueues
from onyx.configs.constants import OnyxCeleryTask
from onyx.db.connector_credential_pair import get_connector_credential_pair_from_id
from onyx.db.engine.time_utils import get_db_current_time
from onyx.db.engine import get_db_current_time
from onyx.db.engine import get_session_with_tenant
from onyx.db.enums import ConnectorCredentialPairStatus
from onyx.db.enums import IndexingStatus
from onyx.db.enums import IndexModelStatus
from onyx.db.index_attempt import mark_attempt_failed
from onyx.db.indexing_coordination import IndexingCoordination
from onyx.db.models import ConnectorCredentialPair
from onyx.db.models import SearchSettings
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface
from onyx.redis.redis_connector import RedisConnector
from onyx.redis.redis_pool import redis_lock_dump
from onyx.redis.redis_pool import SCAN_ITER_COUNT_DEFAULT
from onyx.utils.logger import setup_logger

logger = setup_logger()

NUM_REPEAT_ERRORS_BEFORE_REPEATED_ERROR_STATE = 5


class IndexingCallback(IndexingHeartbeatInterface):
    PARENT_CHECK_INTERVAL = 60

    def __init__(
        self,
        parent_pid: int,
        stop_key: str,
        generator_progress_key: str,
        redis_lock: RedisLock,
        redis_client: Redis,
    ):
        super().__init__()
        self.parent_pid = parent_pid
        self.redis_lock: RedisLock = redis_lock
        self.stop_key: str = stop_key
        self.generator_progress_key: str = generator_progress_key
        self.redis_client = redis_client
        self.started: datetime = datetime.now(timezone.utc)
        self.redis_lock.reacquire()

        self.last_tag: str = "IndexingCallback.__init__"
        self.last_lock_reacquire: datetime = datetime.now(timezone.utc)
        self.last_lock_monotonic = time.monotonic()

        self.last_parent_check = time.monotonic()

    def should_stop(self) -> bool:
        # Check if the associated indexing attempt has been cancelled
        # TODO: Pass index_attempt_id to the callback and check cancellation using the db
        return bool(self.redis_client.exists(self.stop_key))

    def progress(self, tag: str, amount: int) -> None:
        # rkuo: this shouldn't be necessary yet because we spawn the process this runs inside
        # with daemon = True. It seems likely some indexing tasks will need to spawn other processes eventually
        # so leave this code in until we're ready to test it.

        # if self.parent_pid:
        #     # check if the parent pid is alive so we aren't running as a zombie
        #     now = time.monotonic()
        #     if now - self.last_parent_check > IndexingCallback.PARENT_CHECK_INTERVAL:
        #         try:
        #             # this is unintuitive, but it checks if the parent pid is still running
        #             os.kill(self.parent_pid, 0)
        #         except Exception:
        #             logger.exception("IndexingCallback - parent pid check exceptioned")
        #             raise
        #         self.last_parent_check = now

        try:
            current_time = time.monotonic()
            if current_time - self.last_lock_monotonic >= (
                CELERY_GENERIC_BEAT_LOCK_TIMEOUT / 4
            ):
                self.redis_lock.reacquire()
                self.last_lock_reacquire = datetime.now(timezone.utc)
                self.last_lock_monotonic = time.monotonic()

            self.last_tag = tag
        except LockError:
            logger.exception(
                f"IndexingCallback - lock.reacquire exceptioned: "
                f"lock_timeout={self.redis_lock.timeout} "
                f"start={self.started} "
                f"last_tag={self.last_tag} "
                f"last_reacquired={self.last_lock_reacquire} "
                f"now={datetime.now(timezone.utc)}"
            )

            redis_lock_dump(self.redis_lock, self.redis_client)
            raise

        self.redis_client.incrby(self.generator_progress_key, amount)


def validate_indexing_fence(
    tenant_id: str | None,
    key_bytes: bytes,
    reserved_tasks: set[str],
    r_celery: Redis,
    db_session: Session,
) -> None:
    """Checks for the error condition where an indexing fence is set but the associated celery tasks don't exist.
    This can happen if the indexing worker hard crashes or is terminated.
    Being in this bad state means the fence will never clear without help, so this function
    gives the help.

    How this works:
    1. This function renews the active signal with a 5 minute TTL under the following conditions
    1.2. When the task is seen in the redis queue
    1.3. When the task is seen in the reserved / prefetched list

    2. Externally, the active signal is renewed when:
    2.1. The fence is created
    2.2. The indexing watchdog checks the spawned task.

    3. The TTL allows us to get through the transitions on fence startup
    and when the task starts executing.

    More TTL clarification: it is seemingly impossible to exactly query Celery for
    whether a task is in the queue or currently executing.
    1. An unknown task id is always returned as state PENDING.
    2. Redis can be inspected for the task id, but the task id is gone between the time a worker receives the task
    and the time it actually starts on the worker.
    """
    # if the fence doesn't exist, there's nothing to do
    fence_key = key_bytes.decode("utf-8")
    composite_id = RedisConnector.get_id_from_fence_key(fence_key)
    if composite_id is None:
        task_logger.warning(
            f"validate_indexing_fence - could not parse composite_id from {fence_key}"
        )
        return

    # parse out metadata and initialize the helper class with it
    parts = composite_id.split("/")
    if len(parts) != 2:
        return

    cc_pair_id = int(parts[0])
    search_settings_id = int(parts[1])

    redis_connector = RedisConnector(tenant_id, cc_pair_id)
    redis_connector_index = redis_connector.new_index(search_settings_id)

    # check to see if the fence/payload exists
    if not redis_connector_index.fenced:
        return

    payload = redis_connector_index.payload
    if not payload:
        return

    # OK, there's actually something for us to validate

    if payload.celery_task_id is None:
        # the fence is just barely set up.
        if redis_connector_index.active():
            return

        # it would be odd to get here as there isn't that much that can go wrong during
        # initial fence setup, but it's still worth making sure we can recover
        logger.info(
            f"validate_indexing_fence - Resetting fence in basic state without any activity: fence={fence_key}"
        )
        redis_connector_index.reset()
        return

    found = celery_find_task(
        payload.celery_task_id, OnyxCeleryQueues.CONNECTOR_INDEXING, r_celery
    )
    if found:
        # the celery task exists in the redis queue
        redis_connector_index.set_active()
        return

    if payload.celery_task_id in reserved_tasks:
        # the celery task was prefetched and is reserved within the indexing worker
        redis_connector_index.set_active()
        return

    # we may want to enable this check if using the active task list somehow isn't good enough
    # if redis_connector_index.generator_locked():
    #     logger.info(f"{payload.celery_task_id} is currently executing.")

    # if we get here, we didn't find any direct indication that the associated celery tasks exist,
    # but they still might be there due to gaps in our ability to check states during transitions
    # Checking the active signal safeguards us against these transition periods
    # (which has a duration that allows us to bridge those gaps)
    if redis_connector_index.active():
        return

    # celery tasks don't exist and the active signal has expired, possibly due to a crash. Clean it up.
    logger.warning(
        f"validate_indexing_fence - Resetting fence because no associated celery tasks were found: "
        f"index_attempt={payload.index_attempt_id} "
        f"cc_pair={cc_pair_id} "
        f"search_settings={search_settings_id} "
        f"fence={fence_key}"
    )
    if payload.index_attempt_id:
        try:
            mark_attempt_failed(
                payload.index_attempt_id,
                db_session,
                "validate_indexing_fence - Canceling index attempt due to missing celery tasks: "
                f"index_attempt={payload.index_attempt_id}",
            )
        except Exception:
            logger.exception(
                "validate_indexing_fence - Exception while marking index attempt as failed: "
                f"index_attempt={payload.index_attempt_id}",
            )

    redis_connector_index.reset()
    return


def validate_indexing_fences(
    tenant_id: str | None,
    r_replica: Redis,
    r_celery: Redis,
    lock_beat: RedisLock,
) -> None:
    """Validates all indexing fences for this tenant ... aka makes sure
    indexing tasks sent to celery are still in flight.
    """
    reserved_indexing_tasks = celery_get_unacked_task_ids(
        OnyxCeleryQueues.CONNECTOR_INDEXING, r_celery
    )

    # Use replica for this because the worst thing that happens
    # is that we don't run the validation on this pass
    for key_bytes in r_replica.scan_iter(
        RedisConnectorIndex.FENCE_PREFIX + "*", count=SCAN_ITER_COUNT_DEFAULT
    ):
        lock_beat.reacquire()
        with get_session_with_tenant(tenant_id) as db_session:
            validate_indexing_fence(
                tenant_id,
                key_bytes,
                reserved_indexing_tasks,
                r_celery,
                db_session,
            )
    return

# NOTE: we're in the process of removing all fences from indexing; this will
# eventually no longer be used. For now, it is used only for connector pausing.
class IndexingCallback(IndexingHeartbeatInterface):
    def __init__(
        self,
        redis_connector: RedisConnector,
    ):
        self.redis_connector = redis_connector

    def should_stop(self) -> bool:
        # Check if the associated indexing attempt has been cancelled
        # TODO: Pass index_attempt_id to the callback and check cancellation using the db
        return bool(self.redis_connector.stop.fenced)

    # included to satisfy old interface
    def progress(self, tag: str, amount: int) -> None:
        pass


# NOTE: The validate_indexing_fence and validate_indexing_fences functions have been removed
# as they are no longer needed with database-based coordination. The new validation is
# handled by validate_active_indexing_attempts in the main indexing tasks module.


def _should_index(
    cc_pair: ConnectorCredentialPair,
    last_index: IndexAttempt | None,
    search_settings_instance: SearchSettings,
    search_settings_primary: bool,
    secondary_index_building: bool,
    db_session: Session,
) -> bool:
    """Checks various global settings and past indexing attempts to determine if
    we should try to start indexing the cc pair / search setting combination.

    Note that tactical checks such as preventing overlap with a currently running task
    are not handled here.

    Return True if we should try to index, False if not.
    """
    connector = cc_pair.connector

    # uncomment for debugging
    # task_logger.debug(
    #     f"_should_index: "
    #     f"cc_pair={cc_pair.id} "
    #     f"connector={cc_pair.connector_id} "
    #     f"refresh_freq={connector.refresh_freq}"
    # )

    # don't kick off indexing for `NOT_APPLICABLE` sources
    if connector.source == DocumentSource.NOT_APPLICABLE:
        return False

    # User can still manually create single indexing attempts via the UI for the
    # currently in use index
    if DISABLE_INDEX_UPDATE_ON_SWAP:
        if (
            search_settings_instance.status == IndexModelStatus.PRESENT
            and secondary_index_building
        ):
            return False

    # When switching over models, always index at least once
    if search_settings_instance.status == IndexModelStatus.FUTURE:
        if last_index:
            # No new index if the last index attempt succeeded
            # Once is enough. The model will never be able to swap otherwise.
            if last_index.status == IndexingStatus.SUCCESS:
                return False

            # No new index if the last index attempt is waiting to start
            if last_index.status == IndexingStatus.NOT_STARTED:
                return False

            # No new index if the last index attempt is running
            if last_index.status == IndexingStatus.IN_PROGRESS:
                return False
        else:
            if (
                connector.id == 0 or connector.source == DocumentSource.INGESTION_API
            ):  # Ingestion API
                return False
        return True

    # If the connector is paused or is the ingestion API, don't index
    # NOTE: during an embedding model switch over, the following logic
    # is bypassed by the above check for a future model
    if (
        not cc_pair.status.is_active()
        or connector.id == 0
        or connector.source == DocumentSource.INGESTION_API
    ):
        return False

    if search_settings_primary:
        if cc_pair.indexing_trigger is not None:
            # if a manual indexing trigger is on the cc pair, honor it for primary search settings
            return True

    # if no attempt has ever occurred, we should index regardless of refresh_freq
    if not last_index:
        return True

    if connector.refresh_freq is None:
        return False

    current_db_time = get_db_current_time(db_session)
    time_since_index = current_db_time - last_index.time_updated
    if time_since_index.total_seconds() < connector.refresh_freq:
        return False

    return True


def try_creating_docfetching_task(
    celery_app: Celery,
    cc_pair: ConnectorCredentialPair,
    search_settings: SearchSettings,
    reindex: bool,
    db_session: Session,
    r: Redis,
    tenant_id: str | None,
) -> int | None:
    """Checks for any conditions that should block the indexing task from being
    created, then creates the task.

    Does not check for scheduling related conditions as this function
    is used to trigger indexing immediately.

    Now uses database-based coordination instead of Redis fencing.
    """

    LOCK_TIMEOUT = 30

    # we need to serialize any attempt to trigger indexing since it can be triggered
    # either via celery beat or manually (API call)
    lock: RedisLock = r.lock(
        DANSWER_REDIS_FUNCTION_LOCK_PREFIX + "try_creating_indexing_task",
        timeout=LOCK_TIMEOUT,
    )

    acquired = lock.acquire(blocking_timeout=LOCK_TIMEOUT / 2)
    if not acquired:
        return None

    index_attempt_id = None
    try:
        # Basic status checks
        db_session.refresh(cc_pair)
        if cc_pair.status == ConnectorCredentialPairStatus.DELETING:
            return None

        # Generate custom task ID for tracking
        custom_task_id = f"docfetching_{cc_pair.id}_{search_settings.id}_{uuid4()}"

        # Try to create a new index attempt using database coordination
        # This replaces the Redis fencing mechanism
        index_attempt_id = IndexingCoordination.try_create_index_attempt(
            db_session=db_session,
            cc_pair_id=cc_pair.id,
            search_settings_id=search_settings.id,
            celery_task_id=custom_task_id,
            from_beginning=reindex,
        )

        if index_attempt_id is None:
            # Another indexing attempt is already running
            return None

        # Determine which queue to use based on whether this is a user file
        # TODO: at the moment the indexing pipeline is
        # shared between user files and connectors
        queue = (
            OnyxCeleryQueues.USER_FILES_INDEXING
            if cc_pair.is_user_file
            else OnyxCeleryQueues.CONNECTOR_DOC_FETCHING
        )

        # Send the task to Celery
        result = celery_app.send_task(
            OnyxCeleryTask.CONNECTOR_DOC_FETCHING_TASK,
            kwargs=dict(
                index_attempt_id=index_attempt_id,
                cc_pair_id=cc_pair.id,
                search_settings_id=search_settings.id,
                tenant_id=tenant_id,
            ),
            queue=OnyxCeleryQueues.CONNECTOR_INDEXING,
            task_id=custom_task_id,
            priority=OnyxCeleryPriority.MEDIUM,
        )
        if not result:
            raise RuntimeError("send_task for connector_doc_fetching_task failed.")

        task_logger.info(
            f"Created docfetching task: "
            f"cc_pair={cc_pair.id} "
            f"search_settings={search_settings.id} "
            f"attempt_id={index_attempt_id} "
            f"celery_task_id={custom_task_id}"
        )

        return index_attempt_id

    except Exception:
        task_logger.exception(
            f"try_creating_indexing_task - Unexpected exception: "
            f"cc_pair={cc_pair.id} "
            f"search_settings={search_settings.id}"
        )

        # Clean up on failure
        if index_attempt_id is not None:
            mark_attempt_failed(index_attempt_id, db_session)

        return None
    finally:
        if lock.owned():
            lock.release()

    return index_attempt_id
