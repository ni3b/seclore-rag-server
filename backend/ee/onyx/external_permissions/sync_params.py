from collections.abc import Callable

from ee.onyx.configs.app_configs import CONFLUENCE_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import CONFLUENCE_PERMISSION_GROUP_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import DEFAULT_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import GITHUB_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import GITHUB_PERMISSION_GROUP_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import GOOGLE_DRIVE_PERMISSION_GROUP_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import JIRA_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import SHAREPOINT_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import SHAREPOINT_PERMISSION_GROUP_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import SLACK_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.configs.app_configs import TEAMS_PERMISSION_DOC_SYNC_FREQUENCY
from ee.onyx.db.external_perm import ExternalUserGroup
from ee.onyx.external_permissions.confluence.doc_sync import confluence_doc_sync
from ee.onyx.external_permissions.confluence.group_sync import confluence_group_sync
from ee.onyx.external_permissions.github.doc_sync import github_doc_sync
from ee.onyx.external_permissions.github.group_sync import github_group_sync
from ee.onyx.external_permissions.gmail.doc_sync import gmail_doc_sync
from ee.onyx.external_permissions.google_drive.doc_sync import gdrive_doc_sync
from ee.onyx.external_permissions.google_drive.group_sync import gdrive_group_sync
from ee.onyx.external_permissions.jira.doc_sync import jira_doc_sync
from ee.onyx.external_permissions.perm_sync_types import CensoringFuncType
from ee.onyx.external_permissions.perm_sync_types import DocSyncFuncType
from ee.onyx.external_permissions.perm_sync_types import FetchAllDocumentsFunction
from ee.onyx.external_permissions.perm_sync_types import FetchAllDocumentsIdsFunction
from ee.onyx.external_permissions.perm_sync_types import GroupSyncFuncType
from ee.onyx.external_permissions.salesforce.postprocessing import (
    censor_salesforce_chunks,
from ee.onyx.external_permissions.post_query_censoring import (
    DOC_SOURCE_TO_CHUNK_CENSORING_FUNCTION,
)
from ee.onyx.external_permissions.sharepoint.doc_sync import sharepoint_doc_sync
from ee.onyx.external_permissions.sharepoint.group_sync import sharepoint_group_sync
from ee.onyx.external_permissions.slack.doc_sync import slack_doc_sync
from onyx.access.models import DocExternalAccess
from onyx.configs.constants import DocumentSource

if TYPE_CHECKING:
    from onyx.access.models import DocExternalAccess  # noqa
    from onyx.db.models import ConnectorCredentialPair  # noqa
    from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface  # noqa


class DocSyncConfig(BaseModel):
    doc_sync_frequency: int
    doc_sync_func: DocSyncFuncType
    initial_index_should_sync: bool


class GroupSyncConfig(BaseModel):
    group_sync_frequency: int
    group_sync_func: GroupSyncFuncType
    group_sync_is_cc_pair_agnostic: bool


class CensoringConfig(BaseModel):
    chunk_censoring_func: CensoringFuncType


class SyncConfig(BaseModel):
    # None means we don't perform a doc_sync
    doc_sync_config: DocSyncConfig | None = None
    # None means we don't perform a group_sync
    group_sync_config: GroupSyncConfig | None = None
    # None means we don't perform a chunk_censoring
    censoring_config: CensoringConfig | None = None


# Mock doc sync function for testing (no-op)
def mock_doc_sync(
    cc_pair: "ConnectorCredentialPair",
    fetch_all_docs_fn: FetchAllDocumentsFunction,
    fetch_all_docs_ids_fn: FetchAllDocumentsIdsFunction,
    callback: Optional["IndexingHeartbeatInterface"],
) -> Generator["DocExternalAccess", None, None]:
    """Mock doc sync function for testing - returns empty list since permissions are fetched during indexing"""
    yield from []


_SOURCE_TO_SYNC_CONFIG: dict[DocumentSource, SyncConfig] = {
    DocumentSource.GOOGLE_DRIVE: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=DEFAULT_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=gdrive_doc_sync,
            initial_index_should_sync=True,
        ),
        group_sync_config=GroupSyncConfig(
            group_sync_frequency=GOOGLE_DRIVE_PERMISSION_GROUP_SYNC_FREQUENCY,
            group_sync_func=gdrive_group_sync,
            group_sync_is_cc_pair_agnostic=False,
        ),
    ),
    DocumentSource.CONFLUENCE: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=CONFLUENCE_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=confluence_doc_sync,
            initial_index_should_sync=False,
        ),
        group_sync_config=GroupSyncConfig(
            group_sync_frequency=CONFLUENCE_PERMISSION_GROUP_SYNC_FREQUENCY,
            group_sync_func=confluence_group_sync,
            group_sync_is_cc_pair_agnostic=True,
        ),
    ),
    DocumentSource.JIRA: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=JIRA_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=jira_doc_sync,
            initial_index_should_sync=True,
        ),
    ),
    # Groups are not needed for Slack.
    # All channel access is done at the individual user level.
    DocumentSource.SLACK: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=SLACK_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=slack_doc_sync,
            initial_index_should_sync=True,
        ),
    ),
    DocumentSource.GMAIL: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=DEFAULT_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=gmail_doc_sync,
            initial_index_should_sync=False,
        ),
    ),
    DocumentSource.GITHUB: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=GITHUB_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=github_doc_sync,
            initial_index_should_sync=True,
        ),
        group_sync_config=GroupSyncConfig(
            group_sync_frequency=GITHUB_PERMISSION_GROUP_SYNC_FREQUENCY,
            group_sync_func=github_group_sync,
            group_sync_is_cc_pair_agnostic=False,
        ),
    ),
    DocumentSource.SALESFORCE: SyncConfig(
        censoring_config=CensoringConfig(
            chunk_censoring_func=censor_salesforce_chunks,
        ),
    ),
    DocumentSource.MOCK_CONNECTOR: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=DEFAULT_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=mock_doc_sync,
            initial_index_should_sync=True,
        ),
    ),
    # Groups are not needed for Teams.
    # All channel access is done at the individual user level.
    DocumentSource.TEAMS: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=TEAMS_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=teams_doc_sync,
            initial_index_should_sync=True,
        ),
    ),
    DocumentSource.SHAREPOINT: SyncConfig(
        doc_sync_config=DocSyncConfig(
            doc_sync_frequency=SHAREPOINT_PERMISSION_DOC_SYNC_FREQUENCY,
            doc_sync_func=sharepoint_doc_sync,
            initial_index_should_sync=True,
        ),
        group_sync_config=GroupSyncConfig(
            group_sync_frequency=SHAREPOINT_PERMISSION_GROUP_SYNC_FREQUENCY,
            group_sync_func=sharepoint_group_sync,
            group_sync_is_cc_pair_agnostic=False,
        ),
    ),
}

# If nothing is specified here, we run the doc_sync every time the celery beat runs
EXTERNAL_GROUP_SYNC_PERIODS: dict[DocumentSource, int] = {
    # Polling is not supported so we fetch all group permissions every 30 minutes
    DocumentSource.GOOGLE_DRIVE: 5 * 60,
    DocumentSource.CONFLUENCE: CONFLUENCE_PERMISSION_GROUP_SYNC_FREQUENCY,
}


def check_if_valid_sync_source(source_type: DocumentSource) -> bool:
    return (
        source_type in DOC_PERMISSIONS_FUNC_MAP
        or source_type in DOC_SOURCE_TO_CHUNK_CENSORING_FUNCTION
    )
