import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from pytz import UTC
from simple_salesforce import Salesforce
from simple_salesforce import SFType
from simple_salesforce.bulk2 import SFBulk2Handler
from simple_salesforce.bulk2 import SFBulk2Type

from onyx.connectors.interfaces import SecondsSinceUnixEpoch
from onyx.connectors.salesforce.sqlite_functions import has_at_least_one_object_of_type
from onyx.connectors.salesforce.utils import get_object_type_path
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _build_time_filter_for_salesforce(
    start: SecondsSinceUnixEpoch | None, end: SecondsSinceUnixEpoch | None
) -> str:
    if start is None or end is None:
        return ""
    start_datetime = datetime.fromtimestamp(start, UTC)
    end_datetime = datetime.fromtimestamp(end, UTC)
    return (
        f" WHERE LastModifiedDate > {start_datetime.isoformat()} "
        f"AND LastModifiedDate < {end_datetime.isoformat()}"
    )


def _get_sf_type_object_json(sf_client: Salesforce, type_name: str) -> Any:
    sf_object = SFType(type_name, sf_client.session_id, sf_client.sf_instance)
    return sf_object.describe()


def _is_valid_child_object(
    sf_client: Salesforce, child_relationship: dict[str, Any]
) -> bool:
    if not child_relationship["childSObject"]:
        return False
    if not child_relationship["relationshipName"]:
        return False

    sf_type = child_relationship["childSObject"]
    object_description = _get_sf_type_object_json(sf_client, sf_type)
    if not object_description["queryable"]:
        return False

    if child_relationship["field"]:
        if child_relationship["field"] == "RelatedToId":
            return False
    else:
        return False

    return True


def get_all_children_of_sf_type(sf_client: Salesforce, sf_type: str) -> set[str]:
    object_description = _get_sf_type_object_json(sf_client, sf_type)

    child_object_types = set()
    for child_relationship in object_description["childRelationships"]:
        if _is_valid_child_object(sf_client, child_relationship):
            logger.debug(
                f"Found valid child object {child_relationship['childSObject']}"
            )
            child_object_types.add(child_relationship["childSObject"])
    return child_object_types


def _get_all_queryable_fields_of_sf_type(
    sf_client: Salesforce,
    sf_type: str,
) -> list[str]:
    object_description = _get_sf_type_object_json(sf_client, sf_type)
    fields: list[dict[str, Any]] = object_description["fields"]
    valid_fields: set[str] = set()
    field_names_to_remove: set[str] = set()
    for field in fields:
        if compound_field_name := field.get("compoundFieldName"):
            # We do want to get name fields even if they are compound
            if not field.get("nameField"):
                field_names_to_remove.add(compound_field_name)
        if field.get("type", "base64") == "base64":
            continue
        if field_name := field.get("name"):
            valid_fields.add(field_name)

    return list(valid_fields - field_names_to_remove)


def _check_if_object_type_is_empty(
    sf_client: Salesforce, sf_type: str, time_filter: str
) -> bool:
    """
    Use the rest api to check to make sure the query will result in a non-empty response
    """
    try:
        query = f"SELECT Count() FROM {sf_type}{time_filter} LIMIT 1"
        result = sf_client.query(query)
        if result["totalSize"] == 0:
            return False
    except Exception as e:
        if "OPERATION_TOO_LARGE" not in str(e):
            logger.warning(f"Object type {sf_type} doesn't support query: {e}")
            return False
    return True


def _check_for_existing_csvs(sf_type: str) -> list[str] | None:
    # Check if the csv already exists
    if os.path.exists(get_object_type_path(sf_type)):
        existing_csvs = [
            os.path.join(get_object_type_path(sf_type), f)
            for f in os.listdir(get_object_type_path(sf_type))
            if f.endswith(".csv")
        ]
        # If the csv already exists, return the path
        # This is likely due to a previous run that failed
        # after downloading the csv but before the data was
        # written to the db
        if existing_csvs:
            return existing_csvs
    return None


def _build_bulk_query(sf_client: Salesforce, sf_type: str, time_filter: str) -> str:
    queryable_fields = _get_all_queryable_fields_of_sf_type(sf_client, sf_type)
    query = f"SELECT {', '.join(queryable_fields)} FROM {sf_type}{time_filter}"
    return query


def _bulk_retrieve_from_salesforce(
    sf_client: Salesforce,
    sf_type: str,
    time_filter: str,
) -> tuple[str, list[str] | None]:
    if not _check_if_object_type_is_empty(sf_client, sf_type, time_filter):
        return sf_type, None

    if existing_csvs := _check_for_existing_csvs(sf_type):
        return sf_type, existing_csvs

    query = _build_bulk_query(sf_client, sf_type, time_filter)

    bulk_2_handler = SFBulk2Handler(
        session_id=sf_client.session_id,
        bulk2_url=sf_client.bulk2_url,
        proxies=sf_client.proxies,
        session=sf_client.session,
    )
    bulk_2_type = SFBulk2Type(
        object_name=sf_type,
        bulk2_url=bulk_2_handler.bulk2_url,
        headers=bulk_2_handler.headers,
        session=bulk_2_handler.session,
    )

    logger.info(f"Downloading {sf_type}")
    logger.info(f"Query: {query}")

    try:
        # This downloads the file to a file in the target path with a random name
        results = bulk_2_type.download(
            query=query,
            path=get_object_type_path(sf_type),
            max_records=1000000,
        )
        all_download_paths = [result["file"] for result in results]
        logger.info(f"Downloaded {sf_type} to {all_download_paths}")
        return sf_type, all_download_paths
    except Exception as e:
        logger.info(f"Failed to download salesforce csv for object type {sf_type}: {e}")
        return sf_type, None


def fetch_all_csvs_in_parallel(
    sf_client: Salesforce,
    object_types: set[str],
    start: SecondsSinceUnixEpoch | None,
    end: SecondsSinceUnixEpoch | None,
) -> dict[str, list[str] | None]:
    """
    Fetches all the csvs in parallel for the given object types
    Returns a dict of (sf_type, full_download_path)
    """
    time_filter = _build_time_filter_for_salesforce(start, end)
    time_filter_for_each_object_type = {}
    # We do this outside of the thread pool executor because this requires
    # a database connection and we don't want to block the thread pool
    # executor from running
    for sf_type in object_types:
        """Only add time filter if there is at least one object of the type
        in the database. We aren't worried about partially completed object update runs
        because this occurs after we check for existing csvs which covers this case"""
        if has_at_least_one_object_of_type(sf_type):
            time_filter_for_each_object_type[sf_type] = time_filter
        else:
            time_filter_for_each_object_type[sf_type] = ""

    # Run the bulk retrieve in parallel
    with ThreadPoolExecutor() as executor:
        results = executor.map(
            lambda object_type: _bulk_retrieve_from_salesforce(
                sf_client=sf_client,
                sf_type=object_type,
                time_filter=time_filter_for_each_object_type[object_type],
            ),
            object_types,
        )
        return dict(results)

import gc
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from pytz import UTC
from simple_salesforce import Salesforce
from simple_salesforce.bulk2 import SFBulk2Handler
from simple_salesforce.bulk2 import SFBulk2Type
from simple_salesforce.exceptions import SalesforceRefusedRequest

from onyx.connectors.cross_connector_utils.rate_limit_wrapper import (
    rate_limit_builder,
)
from onyx.connectors.interfaces import SecondsSinceUnixEpoch
from onyx.connectors.salesforce.utils import MODIFIED_FIELD
from onyx.utils.logger import setup_logger
from onyx.utils.retry_wrapper import retry_builder

logger = setup_logger()


def is_salesforce_rate_limit_error(exception: Exception) -> bool:
    """Check if an exception is a Salesforce rate limit error."""
    return isinstance(
        exception, SalesforceRefusedRequest
    ) and "REQUEST_LIMIT_EXCEEDED" in str(exception)


def _build_last_modified_time_filter_for_salesforce(
    start: SecondsSinceUnixEpoch | None, end: SecondsSinceUnixEpoch | None
) -> str:
    if start is None or end is None:
        return ""
    start_datetime = datetime.fromtimestamp(start, UTC)
    end_datetime = datetime.fromtimestamp(end, UTC)
    return (
        f" WHERE LastModifiedDate > {start_datetime.isoformat()} "
        f"AND LastModifiedDate < {end_datetime.isoformat()}"
    )


def _build_created_date_time_filter_for_salesforce(
    start: SecondsSinceUnixEpoch | None, end: SecondsSinceUnixEpoch | None
) -> str:
    if start is None or end is None:
        return ""
    start_datetime = datetime.fromtimestamp(start, UTC)
    end_datetime = datetime.fromtimestamp(end, UTC)
    return (
        f" WHERE CreatedDate > {start_datetime.isoformat()} "
        f"AND CreatedDate < {end_datetime.isoformat()}"
    )


def _make_time_filter_for_sf_type(
    queryable_fields: set[str],
    start: SecondsSinceUnixEpoch,
    end: SecondsSinceUnixEpoch,
) -> str | None:

    if MODIFIED_FIELD in queryable_fields:
        return _build_last_modified_time_filter_for_salesforce(start, end)

    if "CreatedDate" in queryable_fields:
        return _build_created_date_time_filter_for_salesforce(start, end)

    return None


def _make_time_filtered_query(
    queryable_fields: set[str], sf_type: str, time_filter: str
) -> str:
    query = f"SELECT {', '.join(queryable_fields)} FROM {sf_type}{time_filter}"
    return query


def get_object_by_id_query(
    object_id: str, sf_type: str, queryable_fields: set[str]
) -> str:
    query = (
        f"SELECT {', '.join(queryable_fields)} FROM {sf_type} WHERE Id = '{object_id}'"
    )
    return query


@retry_builder(
    tries=5,
    delay=2,
    backoff=2,
    max_delay=60,
    exceptions=(SalesforceRefusedRequest,),
)
@rate_limit_builder(max_calls=50, period=60)
def _object_type_has_api_data(
    sf_client: Salesforce, sf_type: str, time_filter: str
) -> bool:
    """
    Use the rest api to check to make sure the query will result in a non-empty response.
    """
    try:
        query = f"SELECT Count() FROM {sf_type}{time_filter} LIMIT 1"
        result = sf_client.query(query)
        if result["totalSize"] == 0:
            return False
    except SalesforceRefusedRequest as e:
        if is_salesforce_rate_limit_error(e):
            logger.warning(
                f"Salesforce rate limit exceeded for object type check: {sf_type}"
            )
            # Add additional delay for rate limit errors
            time.sleep(3)
        raise

    except Exception as e:
        if "OPERATION_TOO_LARGE" not in str(e):
            logger.warning(f"Object type {sf_type} doesn't support query: {e}")
            return False
    return True


def _bulk_retrieve_from_salesforce(
    sf_type: str,
    query: str,
    target_dir: str,
    sf_client: Salesforce,
) -> tuple[str, list[str] | None]:
    """Returns a tuple of
    1. the salesforce object type (NOTE: seems redundant)
    2. the list of CSV's written into the target directory
    """

    bulk_2_handler: SFBulk2Handler | None = SFBulk2Handler(
        session_id=sf_client.session_id,
        bulk2_url=sf_client.bulk2_url,
        proxies=sf_client.proxies,
        session=sf_client.session,
    )
    if not bulk_2_handler:
        return sf_type, None

    # NOTE(rkuo): there are signs this download is allocating large
    # amounts of memory instead of streaming the results to disk.
    # we're doing a gc.collect to try and mitigate this.

    # see https://github.com/simple-salesforce/simple-salesforce/issues/428 for a
    # possible solution
    bulk_2_type: SFBulk2Type | None = SFBulk2Type(
        object_name=sf_type,
        bulk2_url=bulk_2_handler.bulk2_url,
        headers=bulk_2_handler.headers,
        session=bulk_2_handler.session,
    )
    if not bulk_2_type:
        return sf_type, None

    logger.info(f"Downloading {sf_type}")

    logger.debug(f"Query: {query}")

    try:
        # This downloads the file to a file in the target path with a random name
        results = bulk_2_type.download(
            query=query,
            path=target_dir,
            max_records=500000,
        )

        # prepend each downloaded csv with the object type (delimiter = '.')
        all_download_paths: list[str] = []
        for result in results:
            original_file_path = result["file"]
            directory, filename = os.path.split(original_file_path)
            new_filename = f"{sf_type}.{filename}"
            new_file_path = os.path.join(directory, new_filename)
            os.rename(original_file_path, new_file_path)
            all_download_paths.append(new_file_path)
    except Exception as e:
        logger.error(
            f"Failed to download salesforce csv for object type {sf_type}: {e}"
        )
        logger.warning(f"Exceptioning query for object type {sf_type}: {query}")
        return sf_type, None
    finally:
        bulk_2_handler = None
        bulk_2_type = None
        gc.collect()

    logger.info(f"Downloaded {sf_type} to {all_download_paths}")
    return sf_type, all_download_paths


def fetch_all_csvs_in_parallel(
    sf_client: Salesforce,
    all_types_to_filter: dict[str, bool],
    queryable_fields_by_type: dict[str, set[str]],
    start: SecondsSinceUnixEpoch | None,
    end: SecondsSinceUnixEpoch | None,
    target_dir: str,
) -> dict[str, list[str] | None]:
    """
    Fetches all the csvs in parallel for the given object types
    Returns a dict of (sf_type, full_download_path)

    NOTE: We can probably lift object type has api data out of here
    """

    type_to_query = {}

    # query the available fields for each object type and determine how to filter
    for sf_type, apply_filter in all_types_to_filter.items():
        queryable_fields = queryable_fields_by_type[sf_type]

        time_filter = ""
        while True:
            if not apply_filter:
                break

            if start is not None and end is not None:
                time_filter_temp = _make_time_filter_for_sf_type(
                    queryable_fields, start, end
                )
                if time_filter_temp is None:
                    logger.warning(
                        f"Object type not filterable: type={sf_type} fields={queryable_fields}"
                    )
                    time_filter = ""
                else:
                    logger.info(
                        f"Object type filterable: type={sf_type} filter={time_filter_temp}"
                    )
                    time_filter = time_filter_temp

            break

        if not _object_type_has_api_data(sf_client, sf_type, time_filter):
            logger.warning(f"Object type skipped (no data available): type={sf_type}")
            continue

        query = _make_time_filtered_query(queryable_fields, sf_type, time_filter)
        type_to_query[sf_type] = query

    logger.info(
        f"Object types to query: initial={len(all_types_to_filter)} queryable={len(type_to_query)}"
    )

    # Run the bulk retrieve in parallel
    # limit to 4 to help with memory usage
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(
            lambda object_type: _bulk_retrieve_from_salesforce(
                sf_type=object_type,
                query=type_to_query[object_type],
                target_dir=target_dir,
                sf_client=sf_client,
            ),
            type_to_query.keys(),
        )
        return dict(results)
