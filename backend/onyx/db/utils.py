from typing import Any

from sqlalchemy import inspect

from onyx.db.models import Base
from datetime import datetime, timedelta
from fastapi import HTTPException

def model_to_dict(model: Base) -> dict[str, Any]:
    return {c.key: getattr(model, c.key) for c in inspect(model).mapper.column_attrs}  # type: ignore

def parse_date_range(start: str, end: str):
    '''
    Function used to parse dates for analytics API
    '''
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")

    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    # Optionally normalize to day start/end
    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    return start_dt, end_dt
from enum import Enum
from typing import Any

from psycopg2 import errorcodes
from psycopg2 import OperationalError
from pydantic import BaseModel
from sqlalchemy import inspect

from onyx.db.models import Base


def model_to_dict(model: Base) -> dict[str, Any]:
    return {c.key: getattr(model, c.key) for c in inspect(model).mapper.column_attrs}  # type: ignore


RETRYABLE_PG_CODES = {
    errorcodes.SERIALIZATION_FAILURE,  # '40001'
    errorcodes.DEADLOCK_DETECTED,  # '40P01'
    errorcodes.CONNECTION_EXCEPTION,  # '08000'
    errorcodes.CONNECTION_DOES_NOT_EXIST,  # '08003'
    errorcodes.CONNECTION_FAILURE,  # '08006'
    errorcodes.TRANSACTION_ROLLBACK,  # '40000'
}


def is_retryable_sqlalchemy_error(exc: BaseException) -> bool:
    """Helper function for use with tenacity's retry_if_exception as the callback"""
    if isinstance(exc, OperationalError):
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        return pgcode in RETRYABLE_PG_CODES
    return False


class DocumentRow(BaseModel):
    id: str
    doc_metadata: dict[str, Any]
    external_user_group_ids: list[str]


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"
