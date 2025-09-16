from datetime import datetime
from datetime import timedelta
from datetime import timezone

from onyx.configs.constants import INDEX_SEPARATOR
from onyx.context.search.models import IndexFilters, TimeRange
from onyx.document_index.interfaces import VespaChunkRequest
from onyx.document_index.vespa_constants import ACCESS_CONTROL_LIST
from onyx.document_index.vespa_constants import CHUNK_ID
from onyx.document_index.vespa_constants import DOC_UPDATED_AT
from onyx.document_index.vespa_constants import DOCUMENT_ID
from onyx.document_index.vespa_constants import DOCUMENT_SETS
from onyx.document_index.vespa_constants import HIDDEN
from onyx.document_index.vespa_constants import METADATA_LIST
from onyx.document_index.vespa_constants import SOURCE_TYPE
from onyx.document_index.vespa_constants import TENANT_ID
from onyx.utils.logger import setup_logger
from shared_configs.configs import MULTI_TENANT

logger = setup_logger()


def build_vespa_filters(
    filters: IndexFilters,
    *,
    include_hidden: bool = False,
    remove_trailing_and: bool = False,  # Set to True when using as a complete Vespa query
) -> str:
    logger.info(f"Building Vespa filters with input filters: {filters}")
    
    def _build_or_filters(key: str, vals: list[str] | None) -> str:
        if vals is None:
            return ""

        valid_vals = [val for val in vals if val]
        if not key or not valid_vals:
            return ""

        eq_elems = [f'{key} contains "{elem}"' for elem in valid_vals]
        or_clause = " or ".join(eq_elems)
        return f"({or_clause}) and "

    def _build_time_filter(
        time_range: TimeRange | None,
        untimed_doc_cutoff: timedelta = timedelta(days=92),
    ) -> str:
        if not time_range or (not time_range.start_date and not time_range.end_date):
            return ""

        conditions = []
        
        if time_range.start_date:
            start_secs = int(time_range.start_date.timestamp())
            conditions.append(f"({DOC_UPDATED_AT} >= {start_secs})")
            
        if time_range.end_date:
            end_secs = int(time_range.end_date.timestamp())
            conditions.append(f"({DOC_UPDATED_AT} <= {end_secs})")
            
        if not conditions:
            return ""
            
        return " and ".join(conditions) + " and "

    filter_str = f"!({HIDDEN}=true) and " if not include_hidden else ""

    # If running in multi-tenant mode, we may want to filter by tenant_id
    if filters.tenant_id and MULTI_TENANT:
        filter_str += f'({TENANT_ID} contains "{filters.tenant_id}") and '

    # CAREFUL touching this one, currently there is no second ACL double-check post retrieval
    if filters.access_control_list is not None:
        filter_str += _build_or_filters(ACCESS_CONTROL_LIST, filters.access_control_list)

    source_strs = (
        [s.value for s in filters.source_type] if filters.source_type else None
    )
    source_filter = _build_or_filters(SOURCE_TYPE, source_strs)
    if source_filter:
        filter_str += source_filter

    # Add connector name filter to metadata list
    if filters.connector_name:
        if isinstance(filters.connector_name, list):
            # Handle multiple connector names with OR condition
            connector_filters = []
            for connector in filters.connector_name:
                connector_filter = f'connector_name{INDEX_SEPARATOR}{connector}'
                connector_filters.append(f'({METADATA_LIST} contains "{connector_filter}")')
            # Join all connector filters with OR
            connector_or_clause = " or ".join(connector_filters)
            filter_str += f"({connector_or_clause}) and "
        else:
            # Handle single connector name (backward compatibility)
            connector_filter = f'connector_name{INDEX_SEPARATOR}{filters.connector_name}'
            filter_str += f'({METADATA_LIST} contains "{connector_filter}") and '

    # Add status filter to metadata list
    if filters.status:
        if "," in filters.status:
            # Handle multiple statuses with OR condition
            statuses = [s.strip() for s in filters.status.split(",")]
            status_filters = []
            for status in statuses:
                status_filter = f'status{INDEX_SEPARATOR}{status}'
                status_filters.append(f'({METADATA_LIST} contains "{status_filter}")')
            filter_str += f"({' or '.join(status_filters)}) and "
        else:
            # Handle single status
            status_filter = f'status{INDEX_SEPARATOR}{filters.status}'
            filter_str += f'({METADATA_LIST} contains "{status_filter}") and '

    # Add ticket_id filter to metadata list
    if filters.ticket_id:
        ticket_filter = f'id{INDEX_SEPARATOR}{filters.ticket_id}'
        filter_str += f'({METADATA_LIST} contains "{ticket_filter}") and '

    tag_attributes = None
    tags = filters.tags
    if tags:
        tag_attributes = [tag.tag_key + INDEX_SEPARATOR + tag.tag_value for tag in tags]
    tag_filter = _build_or_filters(METADATA_LIST, tag_attributes)
    if tag_filter:
        filter_str += tag_filter

    doc_set_filter = _build_or_filters(DOCUMENT_SETS, filters.document_set)
    if doc_set_filter:
        filter_str += doc_set_filter

    time_filter = _build_time_filter(filters.time_range)
    if time_filter:
        filter_str += time_filter

    if remove_trailing_and and filter_str.endswith(" and "):
        filter_str = filter_str[:-5]

    logger.info(f"Final filter string: {filter_str}")
    return filter_str


def build_vespa_id_based_retrieval_yql(
    chunk_request: VespaChunkRequest,
) -> str:
    id_based_retrieval_yql_section = (
        f'({DOCUMENT_ID} contains "{chunk_request.document_id}"'
    )

    if chunk_request.is_capped:
        id_based_retrieval_yql_section += (
            f" and {CHUNK_ID} >= {chunk_request.min_chunk_ind or 0}"
        )
        id_based_retrieval_yql_section += (
            f" and {CHUNK_ID} <= {chunk_request.max_chunk_ind}"
        )

    id_based_retrieval_yql_section += ")"
    return id_based_retrieval_yql_section
