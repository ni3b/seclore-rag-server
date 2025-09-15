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