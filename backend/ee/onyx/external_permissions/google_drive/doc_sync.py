from datetime import datetime
from datetime import timezone
from typing import Any

from onyx.access.models import DocExternalAccess
from onyx.access.models import ExternalAccess
from onyx.connectors.google_drive.connector import GoogleDriveConnector
from onyx.connectors.google_utils.google_utils import execute_paginated_retrieval
from onyx.connectors.google_utils.resources import get_drive_service
from onyx.connectors.interfaces import GenerateSlimDocumentOutput
from onyx.connectors.models import SlimDocument
from onyx.db.models import ConnectorCredentialPair
from onyx.utils.logger import setup_logger

logger = setup_logger()

_PERMISSION_ID_PERMISSION_MAP: dict[str, dict[str, Any]] = {}


def _get_slim_doc_generator(
    cc_pair: ConnectorCredentialPair,
    google_drive_connector: GoogleDriveConnector,
) -> GenerateSlimDocumentOutput:
    current_time = datetime.now(timezone.utc)
    start_time = (
        cc_pair.last_time_perm_sync.replace(tzinfo=timezone.utc).timestamp()
        if cc_pair.last_time_perm_sync
        else 0.0
    )

    return google_drive_connector.retrieve_all_slim_documents(
        start=start_time, end=current_time.timestamp()
    )


def _fetch_permissions_for_permission_ids(
    google_drive_connector: GoogleDriveConnector,
    permission_ids: list[str],
    permission_info: dict[str, Any],
) -> list[dict[str, Any]]:
    doc_id = permission_info.get("doc_id")
    if not permission_info or not doc_id:
        return []

    permissions = [
        _PERMISSION_ID_PERMISSION_MAP[pid]
        for pid in permission_ids
        if pid in _PERMISSION_ID_PERMISSION_MAP
    ]

    if len(permissions) == len(permission_ids):
        return permissions

    owner_email = permission_info.get("owner_email")

    drive_service = get_drive_service(
        creds=google_drive_connector.creds,
        user_email=(owner_email or google_drive_connector.primary_admin_email),
    )

    fetched_permissions = execute_paginated_retrieval(
        retrieval_function=drive_service.permissions().list,
        list_key="permissions",
        fileId=doc_id,
        fields="permissions(id, emailAddress, type, domain)",
        supportsAllDrives=True,
    )

    permissions_for_doc_id = []
    for permission in fetched_permissions:
        permissions_for_doc_id.append(permission)
        _PERMISSION_ID_PERMISSION_MAP[permission["id"]] = permission

    return permissions_for_doc_id


def _get_permissions_from_slim_doc(
    google_drive_connector: GoogleDriveConnector,
    slim_doc: SlimDocument,
) -> ExternalAccess:
    permission_info = slim_doc.perm_sync_data or {}

    permissions_list = permission_info.get("permissions", [])
    if not permissions_list:
        if permission_ids := permission_info.get("permission_ids"):
            permissions_list = _fetch_permissions_for_permission_ids(
                google_drive_connector=google_drive_connector,
                permission_ids=permission_ids,
                permission_info=permission_info,
            )
        if not permissions_list:
            logger.warning(f"No permissions found for document {slim_doc.id}")
            return ExternalAccess(
                external_user_emails=set(),
                external_user_group_ids=set(),
                is_public=False,
            )

    company_domain = google_drive_connector.google_domain
    user_emails: set[str] = set()
    group_emails: set[str] = set()
    public = False
    for permission in permissions_list:
        permission_type = permission["type"]
        if permission_type == "user":
            user_emails.add(permission["emailAddress"])
        elif permission_type == "group":
            group_emails.add(permission["emailAddress"])
        elif permission_type == "domain" and company_domain:
            if permission.get("domain") == company_domain:
                public = True
            else:
                logger.warning(
                    "Permission is type domain but does not match company domain:"
                    f"\n {permission}"
                )
        elif permission_type == "anyone":
            public = True

    drive_id = permission_info.get("drive_id")
    group_ids = group_emails | ({drive_id} if drive_id is not None else set())

    return ExternalAccess(
        external_user_emails=user_emails,
        external_user_group_ids=group_ids,
        is_public=public,
    )


def gdrive_doc_sync(
    cc_pair: ConnectorCredentialPair,
) -> list[DocExternalAccess]:
    """
    Adds the external permissions to the documents in postgres
    if the document doesn't already exists in postgres, we create
    it in postgres so that when it gets created later, the permissions are
    already populated
    """
    google_drive_connector = GoogleDriveConnector(
        **cc_pair.connector.connector_specific_config
    )
    google_drive_connector.load_credentials(cc_pair.credential.credential_json)

    slim_doc_generator = _get_slim_doc_generator(cc_pair, google_drive_connector)

    document_external_accesses = []
    for slim_doc_batch in slim_doc_generator:
        for slim_doc in slim_doc_batch:
            ext_access = _get_permissions_from_slim_doc(
                google_drive_connector=google_drive_connector,
                slim_doc=slim_doc,
            )
            document_external_accesses.append(
                DocExternalAccess(
                    external_access=ext_access,
                    doc_id=slim_doc.id,
                )
            )
    return document_external_accesses

from collections.abc import Generator
from datetime import datetime
from datetime import timezone

from ee.onyx.external_permissions.google_drive.models import GoogleDrivePermission
from ee.onyx.external_permissions.google_drive.models import PermissionType
from ee.onyx.external_permissions.google_drive.permission_retrieval import (
    get_permissions_by_ids,
)
from ee.onyx.external_permissions.perm_sync_types import FetchAllDocumentsFunction
from ee.onyx.external_permissions.perm_sync_types import FetchAllDocumentsIdsFunction
from onyx.access.models import DocExternalAccess
from onyx.access.models import ExternalAccess
from onyx.connectors.google_drive.connector import GoogleDriveConnector
from onyx.connectors.google_drive.models import GoogleDriveFileType
from onyx.connectors.google_utils.resources import GoogleDriveService
from onyx.connectors.interfaces import GenerateSlimDocumentOutput
from onyx.db.models import ConnectorCredentialPair
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _get_slim_doc_generator(
    cc_pair: ConnectorCredentialPair,
    google_drive_connector: GoogleDriveConnector,
    callback: IndexingHeartbeatInterface | None = None,
) -> GenerateSlimDocumentOutput:
    current_time = datetime.now(timezone.utc)
    start_time = (
        cc_pair.last_time_perm_sync.replace(tzinfo=timezone.utc).timestamp()
        if cc_pair.last_time_perm_sync
        else 0.0
    )

    return google_drive_connector.retrieve_all_slim_documents(
        start=start_time,
        end=current_time.timestamp(),
        callback=callback,
    )


def _merge_permissions_lists(
    permission_lists: list[list[GoogleDrivePermission]],
) -> list[GoogleDrivePermission]:
    """
    Merge a list of permission lists into a single list of permissions.
    """
    seen_permission_ids: set[str] = set()
    merged_permissions: list[GoogleDrivePermission] = []
    for permission_list in permission_lists:
        for permission in permission_list:
            if permission.id not in seen_permission_ids:
                merged_permissions.append(permission)
                seen_permission_ids.add(permission.id)

    return merged_permissions


def get_external_access_for_raw_gdrive_file(
    file: GoogleDriveFileType,
    company_domain: str,
    retriever_drive_service: GoogleDriveService | None,
    admin_drive_service: GoogleDriveService,
) -> ExternalAccess:
    """
    Get the external access for a raw Google Drive file.

    Assumes the file we retrieved has EITHER `permissions` or `permission_ids`
    """
    doc_id = file.get("id")
    if not doc_id:
        raise ValueError("No doc_id found in file")

    permissions = file.get("permissions")
    permission_ids = file.get("permissionIds")
    drive_id = file.get("driveId")

    permissions_list: list[GoogleDrivePermission] = []
    if permissions:
        permissions_list = [
            GoogleDrivePermission.from_drive_permission(p) for p in permissions
        ]
    elif permission_ids:

        def _get_permissions(
            drive_service: GoogleDriveService,
        ) -> list[GoogleDrivePermission]:
            return get_permissions_by_ids(
                drive_service=drive_service,
                doc_id=doc_id,
                permission_ids=permission_ids,
            )

        permissions_list = _get_permissions(
            retriever_drive_service or admin_drive_service
        )
        if len(permissions_list) != len(permission_ids) and retriever_drive_service:
            logger.warning(
                f"Failed to get all permissions for file {doc_id} with retriever service, "
                "trying admin service"
            )
            backup_permissions_list = _get_permissions(admin_drive_service)
            permissions_list = _merge_permissions_lists(
                [permissions_list, backup_permissions_list]
            )

    folder_ids_to_inherit_permissions_from: set[str] = set()
    user_emails: set[str] = set()
    group_emails: set[str] = set()
    public = False

    for permission in permissions_list:
        # if the permission is inherited, do not add it directly to the file
        # instead, add the folder ID as a group that has access to the file
        # we will then handle mapping that folder to the list of Onyx users
        # in the group sync job
        # NOTE: this doesn't handle the case where a folder initially has no
        # permissioning, but then later that folder is shared with a user or group.
        # We could fetch all ancestors of the file to get the list of folders that
        # might affect the permissions of the file, but this will get replaced with
        # an audit-log based approach in the future so not doing it now.
        if permission.inherited_from:
            folder_ids_to_inherit_permissions_from.add(permission.inherited_from)

        if permission.type == PermissionType.USER:
            if permission.email_address:
                user_emails.add(permission.email_address)
            else:
                logger.error(
                    "Permission is type `user` but no email address is "
                    f"provided for document {doc_id}"
                    f"\n {permission}"
                )
        elif permission.type == PermissionType.GROUP:
            # groups are represented as email addresses within Drive
            if permission.email_address:
                group_emails.add(permission.email_address)
            else:
                logger.error(
                    "Permission is type `group` but no email address is "
                    f"provided for document {doc_id}"
                    f"\n {permission}"
                )
        elif permission.type == PermissionType.DOMAIN and company_domain:
            if permission.domain == company_domain:
                public = True
            else:
                logger.warning(
                    "Permission is type domain but does not match company domain:"
                    f"\n {permission}"
                )
        elif permission.type == PermissionType.ANYONE:
            public = True

    group_ids = (
        group_emails
        | folder_ids_to_inherit_permissions_from
        | ({drive_id} if drive_id is not None else set())
    )

    return ExternalAccess(
        external_user_emails=user_emails,
        external_user_group_ids=group_ids,
        is_public=public,
    )


def gdrive_doc_sync(
    cc_pair: ConnectorCredentialPair,
    fetch_all_existing_docs_fn: FetchAllDocumentsFunction,
    fetch_all_existing_docs_ids_fn: FetchAllDocumentsIdsFunction,
    callback: IndexingHeartbeatInterface | None,
) -> Generator[DocExternalAccess, None, None]:
    """
    Adds the external permissions to the documents in postgres
    if the document doesn't already exists in postgres, we create
    it in postgres so that when it gets created later, the permissions are
    already populated
    """
    google_drive_connector = GoogleDriveConnector(
        **cc_pair.connector.connector_specific_config
    )
    google_drive_connector.load_credentials(cc_pair.credential.credential_json)

    slim_doc_generator = _get_slim_doc_generator(cc_pair, google_drive_connector)

    total_processed = 0
    for slim_doc_batch in slim_doc_generator:
        logger.info(f"Drive perm sync: Processing {len(slim_doc_batch)} documents")
        for slim_doc in slim_doc_batch:
            if callback:
                if callback.should_stop():
                    raise RuntimeError("gdrive_doc_sync: Stop signal detected")

                callback.progress("gdrive_doc_sync", 1)

            if slim_doc.external_access is None:
                raise ValueError(
                    f"Drive perm sync: No external access for document {slim_doc.id}"
                )

            yield DocExternalAccess(
                external_access=slim_doc.external_access,
                doc_id=slim_doc.id,
            )
        total_processed += len(slim_doc_batch)
        logger.info(f"Drive perm sync: Processed {total_processed} total documents")
