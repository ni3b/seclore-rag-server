import re
from datetime import datetime
from email_validator import EmailNotValidError
from email_validator import validate_email
from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.auth.users import current_admin_user, current_user
from onyx.db.engine import get_session
from onyx.db.models import PlatformEmail
from onyx.db.models import User
from onyx.utils.logger import setup_logger

logger = setup_logger()
router = APIRouter()


class PlatformEmailCreate(BaseModel):
    email: str


class PlatformEmailResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    updated_at: datetime


@router.get("/platform-emails")
def list_platform_emails_public(
    _: User = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> list[PlatformEmailResponse]:
    """Get all platform emails (public endpoint)"""
    try:
        stmt = select(PlatformEmail).order_by(PlatformEmail.created_at.desc())
        result = db_session.execute(stmt)
        platform_emails = result.scalars().all()
        
        return [
            PlatformEmailResponse(
                id=email.id,
                email=email.email,
                created_at=email.created_at,
                updated_at=email.updated_at,
            )
            for email in platform_emails
        ]
    except Exception as e:
        logger.error(f"Error fetching platform emails: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch platform emails")


# private endpoint for admin users
@router.get("/manage/platform-emails")
def list_platform_emails(
    _: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> list[PlatformEmailResponse]:
    """Get all platform emails"""
    try:
        stmt = select(PlatformEmail).order_by(PlatformEmail.created_at.desc())
        result = db_session.execute(stmt)
        platform_emails = result.scalars().all()
        
        return [
            PlatformEmailResponse(
                id=email.id,
                email=email.email,
                created_at=email.created_at,
                updated_at=email.updated_at,
            )
            for email in platform_emails
        ]
    except Exception as e:
        logger.error(f"Error fetching platform emails: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch platform emails")


@router.post("/manage/platform-emails")
def create_platform_email(
    email_data: PlatformEmailCreate,
    _: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> PlatformEmailResponse:
    """Create a new platform email"""
    try:
        # Validate email format
        try:
            validate_email(email_data.email)
        except EmailNotValidError:
            raise HTTPException(status_code=400, detail="Invalid email format")
        
        # Check if email already exists
        existing_email = db_session.execute(
            select(PlatformEmail).where(PlatformEmail.email == email_data.email)
        ).scalar_one_or_none()
        
        if existing_email:
            raise HTTPException(status_code=409, detail="Email already exists")
        
        # Create new platform email
        platform_email = PlatformEmail(email=email_data.email)
        db_session.add(platform_email)
        db_session.commit()
        db_session.refresh(platform_email)
        
        return PlatformEmailResponse(
            id=platform_email.id,
            email=platform_email.email,
            created_at=platform_email.created_at,
            updated_at=platform_email.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating platform email: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Failed to create platform email")


@router.delete("/manage/platform-emails/{email_id}")
def delete_platform_email(
    email_id: int,
    _: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete a platform email"""
    try:
        # Find the platform email
        platform_email = db_session.execute(
            select(PlatformEmail).where(PlatformEmail.id == email_id)
        ).scalar_one_or_none()
        
        if not platform_email:
            raise HTTPException(status_code=404, detail="Platform email not found")
        
        # Delete the platform email
        db_session.delete(platform_email)
        db_session.commit()
        
        return {"message": "Platform email deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting platform email: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete platform email") 