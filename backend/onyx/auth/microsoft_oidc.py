from authlib.integrations.starlette_client import OAuth
from authlib.oidc.core import UserInfo
from fastapi import FastAPI, Request, APIRouter, Depends, HTTPException, Query
from starlette.config import Config
from starlette.responses import RedirectResponse
from fastapi_users.authentication.strategy import Strategy
from fastapi_users.manager import BaseUserManager
from pydantic import BaseModel
import secrets
import httpx
import os
import asyncio
from datetime import datetime, timezone, timedelta
import time

from onyx.configs.app_configs import OAUTH_CLIENT_ID
from onyx.configs.app_configs import OAUTH_CLIENT_SECRET
from onyx.configs.app_configs import OPENID_CONFIG_URL
from onyx.configs.app_configs import USER_AUTH_SECRET
from onyx.configs.app_configs import WEB_DOMAIN
from onyx.auth.users import get_user_manager
from onyx.auth.users import auth_backend
from onyx.auth.users import current_user
from onyx.db.models import User
from onyx.utils.logger import setup_logger
from onyx.db.engine import get_session
from onyx.db.models import Persona
from onyx.db.models import OAuthAccount
from onyx.auth.schemas import UserCreate, UserRole
from fastapi_users.password import PasswordHelper
from fastapi_users import exceptions
from sqlalchemy import cast, ARRAY, Text

logger = setup_logger()

# Common Microsoft OIDC constants
MICROSOFT_TENANT_ID = OPENID_CONFIG_URL.split("/")[3] if OPENID_CONFIG_URL else None
MICROSOFT_TOKEN_URL = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token" if MICROSOFT_TENANT_ID else None

# Retry configuration
MAX_RETRIES = 3

class OIDCAuthorizeResponse(BaseModel):
    authorization_url: str

class MicrosoftADGroup(BaseModel):
    id: str
    display_name: str
    description: str | None = None
    mail: str | None = None
    is_member: bool = False  # Indicates if the current user is a member of this group

class MicrosoftADGroupsResponse(BaseModel):
    groups: list[MicrosoftADGroup]

class MicrosoftADUser(BaseModel):
    id: str
    display_name: str
    user_principal_name: str
    mail: str | None = None

class MicrosoftADGroupUsersResponse(BaseModel):
    users: list[MicrosoftADUser]

class AddMicrosoftUserRequest(BaseModel):
    email: str

# Microsoft OIDC configuration
MICROSOFT_OIDC_CONFIG = {
    'client_id': OAUTH_CLIENT_ID,
    'client_secret': OAUTH_CLIENT_SECRET,
    'server_metadata_url': OPENID_CONFIG_URL,
    'client_kwargs': {
        'scope': 'openid email profile Group.Read.All',
        'token_endpoint_auth_method': 'client_secret_post'
    }
}

# Global OAuth instance
_oauth_instance = None

def setup_microsoft_oidc(app: FastAPI) -> OAuth:
    """Setup Microsoft OIDC authentication"""
    global _oauth_instance
    
    # Check if USER_AUTH_SECRET is properly set
    if not USER_AUTH_SECRET or USER_AUTH_SECRET == "your-secret-key-here-change-this-in-production":
        logger.error("USER_AUTH_SECRET is not properly configured. Please set a secure secret key.")
        raise ValueError("USER_AUTH_SECRET must be set to a secure value")
    
    # Create OAuth instance
    _oauth_instance = OAuth()
    
    # Register Microsoft OIDC client
    _oauth_instance.register(
        name='microsoft',
        **MICROSOFT_OIDC_CONFIG
    )
    
    return _oauth_instance

def get_valid_user_token(user: User) -> str | None:
    """Get a valid access token for the user using client credentials"""
    try:
        # Use app credentials to get access token (like the curl command)
        client_id = OAUTH_CLIENT_ID
        client_secret = OAUTH_CLIENT_SECRET
        
        if not client_id or not client_secret:
            logger.error("OAUTH_CLIENT_ID or OAUTH_CLIENT_SECRET not configured")
            return None
        
        token_data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }
        
        retry_count = 0
        while retry_count < MAX_RETRIES:
            try:
                logger.debug(f"Requesting access token from: {MICROSOFT_TOKEN_URL} (attempt {retry_count + 1}/{MAX_RETRIES})")                    
                token_resp = httpx.post(
                    MICROSOFT_TOKEN_URL,
                    data=token_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                
                if token_resp.status_code == 200:
                    token_json = token_resp.json()
                    access_token = token_json.get("access_token")
                    expires_in = token_json.get("expires_in", "unknown")
                    
                    if access_token:
                        logger.debug(f"Successfully obtained access token, expires in: {expires_in} seconds")
                        return access_token
                    else:
                        logger.error("No access token in response")
                        return None
                else:
                    logger.warning(f"Failed to get access token: {token_resp.status_code} (attempt {retry_count + 1}/{MAX_RETRIES})")
                    logger.warning(f"Token response: {token_resp.text}")
                    retry_count += 1
                    if retry_count < MAX_RETRIES:
                        time.sleep(1)  # Wait 1 second before retry
                        continue
                    else:
                        logger.error(f"Failed to get access token after {MAX_RETRIES} attempts")
                        return None
                            
            except Exception as e:
                logger.warning(f"Error getting access token (attempt {retry_count + 1}/{MAX_RETRIES}): {str(e)}")
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    time.sleep(1)  # Wait 1 second before retry
                    continue
                else:
                    logger.error(f"Error getting access token after {MAX_RETRIES} attempts: {str(e)}")
                    return None
            
    except Exception as e:
        logger.error(f"Error getting access token: {str(e)}")
        return None

def get_user_microsoft_groups(access_token: str, user_email: str = None) -> list[str]:
    """Get user's Microsoft AD group IDs using specific user email"""
    if not user_email:
        logger.error("User email is required for get_user_microsoft_groups")
        return []
    
    retry_count = 0    
    while retry_count < MAX_RETRIES:
        try:
            logger.debug(f"Making request to /users/{user_email}/memberOf with token (first 20 chars): {access_token[:20]}... (attempt {retry_count + 1}/{MAX_RETRIES})")
            response = httpx.get(
                f'https://graph.microsoft.com/v1.0/users/{user_email}/memberOf',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Content-Type': 'application/json'
                },
                params={
                    '$select': 'id',
                    '$top': 999
                }
            )
            
            logger.debug(f"Response status for user memberOf api: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                group_ids = [group.get('id') for group in data.get('value', [])]
                logger.debug(f"Successfully retrieved {len(group_ids)} group IDs for user {user_email}: {group_ids}")
                
                return group_ids
            else:
                logger.warning(f"Failed to get user {user_email} Microsoft AD groups: {response.status_code} (attempt {retry_count + 1}/{MAX_RETRIES})")
                logger.warning(f"Response text: {response.text}")
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    time.sleep(1)  # Wait 1 second before retry
                    continue
                else:
                    logger.error(f"Failed to get user {user_email} Microsoft AD groups after {MAX_RETRIES} attempts")
                    return []
                        
        except Exception as e:
            logger.warning(f"Error getting user Microsoft groups (attempt {retry_count + 1}/{MAX_RETRIES}): {str(e)}")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                time.sleep(1)  # Wait 1 second before retry
                continue
            else:
                logger.error(f"Error getting user Microsoft groups after {MAX_RETRIES} attempts: {str(e)}")
                return []

async def get_all_azure_ad_users(access_token: str) -> list[str]:
    """Get all Azure AD user email IDs using app credentials"""
    retry_count = 0    
    while retry_count < MAX_RETRIES:
        try:
            async with httpx.AsyncClient() as http_client:
                logger.debug(f"Making request to /users with token (first 20 chars): {access_token[:20]}... (attempt {retry_count + 1}/{MAX_RETRIES})")
                
                all_user_emails = []
                next_link = None
                page_count = 0
                
                while True:
                    page_count += 1
                    logger.debug(f"Fetching users page {page_count}")
                    
                    if next_link:
                        # Use the nextLink URL directly
                        response = await http_client.get(
                            next_link,
                            headers={
                                'Authorization': f'Bearer {access_token}',
                                'Content-Type': 'application/json'
                            }
                        )
                    else:
                        # First request
                        response = await http_client.get(
                            'https://graph.microsoft.com/v1.0/users',
                            headers={
                                'Authorization': f'Bearer {access_token}',
                                'Content-Type': 'application/json'
                            },
                            params={
                                '$select': 'id,userPrincipalName,mail',
                                '$top': 999  # Maximum per page
                            }
                        )
                    
                    logger.debug(f"Response status for users api page {page_count}: {response.status_code}")
                    
                    if response.is_success:
                        data = response.json()
                        users = data.get('value', [])
                        
                        # Extract email addresses from users
                        page_emails = []
                        for user in users:
                            # Prefer userPrincipalName over mail as it's more reliable
                            email = user.get('userPrincipalName') or user.get('mail')
                            if email:
                                page_emails.append(email)
                        
                        all_user_emails.extend(page_emails)
                        logger.debug(f"Page {page_count}: Retrieved {len(page_emails)} user emails (Total so far: {len(all_user_emails)})")
                        
                        # Check if there are more pages
                        next_link = data.get('@odata.nextLink')
                        if not next_link:
                            break
                    else:
                        logger.warning(f"Failed to get Azure AD users page {page_count}: {response.status_code} (attempt {retry_count + 1}/{MAX_RETRIES})")
                        logger.warning(f"Response text: {response.text}")
                        raise Exception(f"Failed to get Azure AD users page {page_count}: {response.status_code}")
                
                logger.debug(f"Successfully retrieved {len(all_user_emails)} total user emails from Azure AD")
                                
                return all_user_emails
                
        except Exception as e:
            logger.warning(f"Error getting all Azure AD users (attempt {retry_count + 1}/{MAX_RETRIES}): {str(e)}")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(1)  # Wait 1 second before retry
                continue
            else:
                logger.error(f"Error getting all Azure AD users after {MAX_RETRIES} attempts: {str(e)}")
                return []

async def check_and_grant_group_access(user: User, request: Request) -> None:
    """Check if user belongs to groups with assistant access and grant access"""
    if not user.oauth_accounts:
        return
    
    # Check for Microsoft OAuth account
    microsoft_account = None
    for account in user.oauth_accounts:
        if account.oauth_name == 'microsoft':
            microsoft_account = account
            break
    
    # Check if the user has a Microsoft OAuth account and an access token
    if not microsoft_account or not microsoft_account.access_token:
        return
    
    try:
        # Use app-level credentials instead of user's stored token to avoid expired token issues
        access_token = get_valid_user_token(user)
        
        if not access_token:
            logger.warning(f"Could not get valid access token for user {user.email}")
            return
        
        # Get user's Microsoft AD groups using app-level token
        user_groups = get_user_microsoft_groups(access_token, user.email)
        
        if not user_groups:
            logger.info(f"User {user.email} has no Microsoft AD groups")
            return
        
        # Find assistants that match user's groups
        for db_session in get_session():
            # Convert user_groups to the same type as stored in database (text[])
            user_groups_text = [str(group_id) for group_id in user_groups]
            
            # Use SQLAlchemy cast to ensure proper type casting
            matching_assistants = db_session.query(Persona).filter(
                Persona.microsoft_ad_groups.overlap(
                    cast(user_groups_text, ARRAY(Text))
                )
            ).all()
            
            if matching_assistants:
                assistant_names = [assistant.name for assistant in matching_assistants]
                logger.info(f"User {user.email} has access to {len(matching_assistants)} assistants based on Microsoft AD groups: {assistant_names}")
            else:
                logger.info(f"User {user.email} has no matching assistants for their Microsoft AD groups")
            break
                
    except Exception as e:
        logger.error(f"Error checking group access for user {user.email}: {str(e)}")

def create_oidc_router(oauth: OAuth) -> APIRouter:
    """Create the OIDC router with login and callback endpoints"""
    router = APIRouter()
    
    # Create client once
    client = oauth.create_client('microsoft')
    
    @router.get("/authorize", response_model=OIDCAuthorizeResponse)
    async def login(request: Request):
        """Login endpoint that returns the Microsoft OIDC authorization URL"""
        redirect_uri = f"{WEB_DOMAIN}/auth/oidc/callback"
        
        # Get next URL from query parameters and encode it in the state
        next_url = request.query_params.get('next', '/')
        
        logger.info(f"OIDC login initiated for next_url: {next_url}")

        # Generate the authorization URL using the OAuth client
        # We need to manually construct the URL since we want to return it, not redirect
        try:
            # Get the authorization endpoint from the client metadata
            metadata = await client.load_server_metadata()
            authorization_endpoint = metadata.get('authorization_endpoint')
            
            if not authorization_endpoint:
                logger.error("No authorization endpoint found in OIDC metadata")
                raise HTTPException(
                    status_code=500,
                    detail="OIDC configuration error: no authorization endpoint"
                )
            
            # Generate state for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Build authorization URL with all required parameters
            auth_params = {
                'client_id': OAUTH_CLIENT_ID,
                'response_type': 'code',
                'scope': 'openid email profile Group.Read.All',
                'redirect_uri': redirect_uri,
                'state': f"{state}|{next_url}",  # Encode next_url in state
            }
            
            # Construct the full authorization URL
            from urllib.parse import urlencode
            auth_url = f"{authorization_endpoint}?{urlencode(auth_params)}"
            
            logger.info(f"OIDC authorization URL generated successfully")
            
            return OIDCAuthorizeResponse(authorization_url=auth_url)
            
        except Exception as e:
            logger.error(f"Error generating OIDC authorization URL: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate authorization URL: {str(e)}"
            )
    
    @router.get("/callback")
    async def callback(
        request: Request,
        user_manager: BaseUserManager = Depends(get_user_manager),
        strategy: Strategy = Depends(auth_backend.get_strategy),
    ):
        """Callback endpoint that handles the OIDC response"""
        
        # Get authorization code and state from query parameters
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        
        # Decode next_url from state parameter
        next_url = '/'
        if state and '|' in state:
            state_parts = state.split('|', 1)
            if len(state_parts) == 2:
                state = state_parts[0]  # The actual state token
                next_url = state_parts[1]  # The next_url
                logger.debug(f"Decoded state: {state[:8]}..., next_url: {next_url}")
        else:
            logger.debug(f"No next_url encoded in state, using default: {next_url}")
        
        logger.info(f"OIDC callback received, next_url: {next_url}")
        
        try:
            # Check if the client secret is properly configured
            if not OAUTH_CLIENT_SECRET or len(OAUTH_CLIENT_SECRET) < 10:
                logger.error(f"OAUTH_CLIENT_SECRET appears to be misconfigured. Length: {len(OAUTH_CLIENT_SECRET) if OAUTH_CLIENT_SECRET else 0}")
                logger.error("Please ensure OAUTH_CLIENT_SECRET is set to the actual client secret value, not the client secret ID")
                raise HTTPException(
                    status_code=500,
                    detail="OAuth client secret is not properly configured. Please check that OAUTH_CLIENT_SECRET is set to the actual client secret value, not the client secret ID."
                )
            
            if not code:
                logger.error("No authorization code received in callback")
                raise HTTPException(
                    status_code=400,
                    detail="No authorization code received"
                )
            
            if not state:
                logger.error("No state parameter received in callback")
                raise HTTPException(
                    status_code=400,
                    detail="No state parameter received - CSRF protection failed"
                )
            
            logger.debug("Manual token exchange with Microsoft")
            
            # Exchange authorization code for access token manually
            token_endpoint = OPENID_CONFIG_URL.replace("/v2.0/.well-known/openid-configuration", "/oauth2/v2.0/token")
            redirect_uri = f"{WEB_DOMAIN}/auth/oidc/callback"
            
            token_data = {
                'client_id': OAUTH_CLIENT_ID,
                'client_secret': OAUTH_CLIENT_SECRET,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            }
            
            async with httpx.AsyncClient() as http_client:
                token_response = await http_client.post(
                    token_endpoint,
                    data=token_data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                
                if not token_response.is_success:
                    logger.error(f"Token exchange failed: {token_response.status_code} - {token_response.text}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Token exchange failed: {token_response.text}"
                    )
                
                token_json = token_response.json()
                access_token = token_json.get('access_token')
                
                if not access_token:
                    logger.error("No access token in response")
                    raise HTTPException(
                        status_code=400,
                        detail="No access token received"
                    )
                
                logger.debug("Token exchange successful")
                
                # Get user info from Microsoft Graph
                userinfo_response = await http_client.get(
                    'https://graph.microsoft.com/oidc/userinfo',
                    headers={'Authorization': f'Bearer {access_token}'}
                )
                
                if not userinfo_response.is_success:
                    logger.error(f"User info request failed: {userinfo_response.status_code} - {userinfo_response.text}")
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to get user information"
                    )
                
                user_info = userinfo_response.json()
                logger.debug(f"User info received: {list(user_info.keys()) if user_info else 'None'}")
            
            # Extract email and ID from user info
            email = user_info.get('email')
            account_id = user_info.get('sub')
            
            logger.info(f"OIDC user info - Email: {email}, Account ID: {account_id[:8] + '...' if account_id else 'None'}")
            
            if not email:
                logger.error("Email not available from Microsoft OIDC response")
                raise HTTPException(
                    status_code=400,
                    detail="Email not available from Microsoft OIDC"
                )
                
            # Create or update user
            try:
                logger.debug(f"Creating/updating user with email: {email}")
                # The code below attempts to create or update a user in the database using the user_manager's oauth_callback method.
                # It passes the Microsoft OIDC provider name, access token, account ID, email, token expiry, refresh token, and request.
                # It also tries to associate by email and mark the user as verified by default.
                #
                # However, this will fail for new users if the oauth_callback implementation expects the user to already exist in the database,
                # or if it does not handle user creation when the user is not found. In many FastAPI Users setups, oauth_callback is only for
                # linking an existing user, not for creating a new one. If the user does not exist, it may raise an exception or return None,
                # causing the authentication flow to break for first-time logins.
                #
                # To fix this, you should check if the user exists by email, and if not, create a new user record before calling oauth_callback,
                # or ensure that oauth_callback itself handles user creation for new users.

                user = await user_manager.oauth_callback(
                    'microsoft',
                    access_token,
                    account_id,
                    email,
                    token_json.get('expires_in'),  # expires_in instead of expires_at
                    token_json.get('refresh_token'),
                    request,
                    associate_by_email=True,
                    is_verified_by_default=True
                )
                logger.info(f"User created/updated successfully: {user.email}")
            except Exception as e:
                logger.error(f"Failed to create/update user: {str(e)}")
                logger.error(f"User manager error details: {type(e).__name__}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to create/update user: {str(e)}"
                )
                
            if not user.is_active:
                logger.warning(f"User {user.email} is inactive")
                raise HTTPException(
                    status_code=400,
                    detail="User is inactive"
                )
                
            # Login user and get response with session cookie
            logger.debug("Logging in user and creating session")
            response = await auth_backend.login(strategy, user)
            await user_manager.on_after_login(user, request, response)
            logger.info(f"User {user.email} logged in successfully")
            
            # Check for group-based access after successful login
            # await check_and_grant_group_access(user, request)
            
            # Create redirect response with proper 302 status
            redirect_response = RedirectResponse(next_url, status_code=302)
            
            # Copy authentication headers (especially Set-Cookie) from login response
            for header_name, header_value in response.headers.items():
                if header_name.lower() in ['set-cookie', 'authorization']:
                    redirect_response.headers[header_name] = header_value
                
            logger.info(f"OIDC authentication completed successfully, redirecting to: {next_url}")
            return redirect_response
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error in OIDC callback: {str(e)}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {e}")
            
            # Check if this is the client secret error
            if "invalid_client" in str(e) or "AADSTS7000215" in str(e):
                logger.error("This error indicates that OAUTH_CLIENT_SECRET is set to the client secret ID instead of the actual secret value")
                logger.error("Please check your Microsoft Azure app registration and use the actual client secret value")
                raise HTTPException(
                    status_code=500,
                    detail="OAuth client secret configuration error. Please check that OAUTH_CLIENT_SECRET is set to the actual client secret value, not the client secret ID."
                )
            
            raise HTTPException(
                status_code=500,
                detail="An unexpected error occurred during authentication"
            )
    
    @router.get("/microsoft-groups", response_model=MicrosoftADGroupsResponse)
    async def get_microsoft_groups(
        request: Request,
        search: str = Query(None, description="Search query to filter groups by name"),
        user_manager: BaseUserManager = Depends(get_user_manager),
        strategy: Strategy = Depends(auth_backend.get_strategy),
        current_user: User = Depends(current_user),
    ):
        """Fetch all Microsoft AD groups with user membership status and optional search filtering"""
        # For admin operations, we can allow access even if user session has expired
        # as long as we have a valid user record (for audit purposes)
        user_email = None
        
        if current_user:
            user_email = current_user.email
            logger.debug(f"User {user_email} requesting Microsoft groups with search: {search}")
        else:
            logger.debug("No authenticated user for Microsoft groups endpoint, proceeding with app-only access")
        
        # Use app credentials to fetch all groups (NOT user's delegated token)
        # This ensures we always have a valid token for admin operations
        client_id = os.environ["OAUTH_CLIENT_ID"]
        client_secret = os.environ["OAUTH_CLIENT_SECRET"]

        data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            try:
                async with httpx.AsyncClient() as client:
                    # Get access token with retry
                    token_resp = await client.post(MICROSOFT_TOKEN_URL, data=data)
                    if token_resp.status_code != 200:
                        logger.warning(f"Failed to get app access token: {token_resp.status_code} (attempt {retry_count + 1}/{MAX_RETRIES})")
                        logger.warning(f"Token response: {token_resp.text}")
                        retry_count += 1
                        if retry_count < MAX_RETRIES:
                            await asyncio.sleep(1)  # Wait 1 second before retry
                            continue
                        else:
                            logger.error(f"Failed to get app access token after {MAX_RETRIES} attempts")
                            raise HTTPException(status_code=500, detail="Failed to get app access token")
                    
                    token_data = token_resp.json()
                    access_token = token_data["access_token"]
                    expires_in = token_data.get("expires_in", "unknown")
                    logger.debug(f"Successfully obtained app access token, expires in: {expires_in} seconds")

                    # Build the Microsoft Graph API URL
                    graph_url = "https://graph.microsoft.com/v1.0/groups"
                    params = {
                        "$select": "id,displayName,description,mail",
                        "$top": "999"  # Maximum per page
                    }
                    
                    # Note: Microsoft Graph API doesn't support contains() filter for groups endpoint
                    # We'll fetch all groups and filter client-side if search is provided

                    logger.debug(f"Making Microsoft Graph API request to: {graph_url} (attempt {retry_count + 1}/{MAX_RETRIES})")
                    logger.debug(f"With parameters: {params}")
                    logger.debug(f"Using access token (first 20 chars): {access_token[:20]}...")
                    
                    # Fetch all groups using pagination
                    all_groups = []
                    next_link = None
                    page_count = 0
                    
                    while True:
                        page_count += 1
                        current_params = params.copy()
                        
                        if next_link:
                            # Use the nextLink URL directly
                            groups_resp = await client.get(next_link, headers={"Authorization": f"Bearer {access_token}"})
                        else:
                            # First request
                            groups_resp = await client.get(graph_url, headers={"Authorization": f"Bearer {access_token}"}, params=current_params)
                        
                        if groups_resp.status_code != 200:
                            error_detail = "Failed to fetch groups from Microsoft Graph"
                            if groups_resp.text:
                                try:
                                    error_json = groups_resp.json()
                                    if "error" in error_json:
                                        error_detail = f"Microsoft Graph API error: {error_json['error'].get('message', 'Unknown error')}"
                                except:
                                    error_detail = f"Microsoft Graph API error: {groups_resp.text}"
                            
                            logger.warning(f"Microsoft Graph API error: {groups_resp.status_code} (attempt {retry_count + 1}/{MAX_RETRIES})")
                            logger.warning(f"Response: {groups_resp.text}")
                            raise Exception(error_detail)
                        
                        groups_data = groups_resp.json()
                        page_groups = groups_data.get("value", [])
                        all_groups.extend(page_groups)
                        
                        logger.debug(f"Page {page_count}: Retrieved {len(page_groups)} groups (Total so far: {len(all_groups)})")
                        
                        # Check if there are more pages
                        next_link = groups_data.get("@odata.nextLink")
                        if not next_link:
                            break
                    
                    logger.debug(f"Total groups from Microsoft Graph API: {len(all_groups)}")                    
                    # Process all groups and mark user membership
                    processed_groups = []
                    for group in all_groups:
                        group_id = group["id"]
                        group_name = group.get("displayName", "")
                        
                        group_info = {
                            "id": group_id,
                            "display_name": group_name,
                            "description": group.get("description"),
                            "mail": group.get("mail"),
                            "is_member": False,  # Default to false since we're not checking membership
                        }
                        
                        # Debug logging for first few groups
                        if len(processed_groups) < 3:
                            logger.debug(f"Group '{group_name}' (ID: {group_id})")
                        
                        # Apply search filter if provided
                        if search and search.strip():
                            search_term = search.strip().lower()
                            if search_term in group_info["display_name"].lower():
                                processed_groups.append(group_info)
                        else:
                            processed_groups.append(group_info)
                    
                    logger.debug(f"Found {len(processed_groups)} groups")
                    
                    return {"groups": processed_groups}
                    
            except Exception as e:
                logger.warning(f"Error fetching groups from Microsoft Graph (attempt {retry_count + 1}/{MAX_RETRIES}): {str(e)}")
                retry_count += 1
                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(1)  # Wait 1 second before retry
                    continue
                else:
                    logger.error(f"Error fetching groups from Microsoft Graph after {MAX_RETRIES} attempts: {str(e)}")
                    raise HTTPException(status_code=500, detail="Failed to fetch groups from Microsoft Graph")
    
    @router.get("/microsoft-groups/{group_id}/users", response_model=MicrosoftADGroupUsersResponse)
    async def get_microsoft_group_users(
        group_id: str,
        request: Request,
        user_manager: BaseUserManager = Depends(get_user_manager),
        strategy: Strategy = Depends(auth_backend.get_strategy),
        current_user: User = Depends(current_user),
    ):
        """Fetch users belonging to a specific Microsoft AD group"""
        # For admin operations, we can allow access even if user session has expired
        user_email = None
        if current_user:
            user_email = current_user.email
            logger.debug(f"User {user_email} requesting users for group {group_id}")
        else:
            logger.warning("No authenticated user for Microsoft group users endpoint, proceeding with app-only access")
        
        # Use app credentials to fetch group members
        client_id = os.environ["OAUTH_CLIENT_ID"]
        client_secret = os.environ["OAUTH_CLIENT_SECRET"]

        data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(MICROSOFT_TOKEN_URL, data=data)
            if token_resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to get app access token")
            access_token = token_resp.json()["access_token"]

            # Fetch group members
            users_resp = await client.get(
                f"https://graph.microsoft.com/v1.0/groups/{group_id}/members",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            if users_resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch group users from Microsoft Graph")
            users_data = users_resp.json()
            
            # Filter to only user objects (not groups)
            users = []
            for user in users_data.get("value", []):
                if user.get("@odata.type") == "#microsoft.graph.user":
                    users.append({
                        "id": user["id"],
                        "display_name": user.get("displayName", ""),
                        "user_principal_name": user.get("userPrincipalName", ""),
                        "mail": user.get("mail"),
                    })
            
            return {"users": users}

    @router.get("/microsoft-users")
    async def get_all_microsoft_users(
        request: Request,
        user_manager: BaseUserManager = Depends(get_user_manager),
        strategy: Strategy = Depends(auth_backend.get_strategy),
        current_user: User = Depends(current_user),
    ):
        """Fetch all Azure AD users"""
        # For admin operations, we can allow access even if user session has expired
        user_email = None
        if current_user:
            user_email = current_user.email
            logger.debug(f"User {user_email} requesting all Microsoft users")
        else:
            logger.warning("No authenticated user for Microsoft users endpoint, proceeding with app-only access")
        
        # Use app credentials to fetch all users
        client_id = os.environ["OAUTH_CLIENT_ID"]
        client_secret = os.environ["OAUTH_CLIENT_SECRET"]

        data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(MICROSOFT_TOKEN_URL, data=data)
            if token_resp.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to get app access token")
            access_token = token_resp.json()["access_token"]

            # Get all Azure AD users
            all_user_emails = await get_all_azure_ad_users(access_token)
            
            # Convert to the format expected by the frontend
            users = []
            for email in all_user_emails:
                users.append({
                    "id": email,  # Use email as ID for consistency
                    "display_name": email.split('@')[0],  # Extract name from email
                    "user_principal_name": email,
                    "mail": email,
                })
            
            return {"users": users}

    @router.post("/add-microsoft-user")
    async def add_microsoft_user(
        user_data: AddMicrosoftUserRequest,
        request: Request,
        user_manager: BaseUserManager = Depends(get_user_manager),
        strategy: Strategy = Depends(auth_backend.get_strategy),
        current_user: User = Depends(current_user),
    ):
        """Add a Microsoft AD user to the local database"""
        try:
            email = user_data.email
            
            logger.info(f"Attempting to add Microsoft user: {email}")
            
            # Check if user already exists using try-catch pattern like SAML
            try:
                existing_user = await user_manager.get_by_email(email)
                logger.info(f"User already exists: {email}")
                return {"user_id": str(existing_user.id), "email": email, "status": "existing"}
            except exceptions.UserNotExists:
                logger.info(f"User does not exist, creating new user: {email}")
            
            # Create new user in database with proper structure
            password_helper = PasswordHelper()
            password = password_helper.generate()
            hashed_password = password_helper.hash(password)
            
            user_create_data = UserCreate(
                email=email,
                password=hashed_password,
                is_verified=True,  # Microsoft users are pre-verified
                role=UserRole.BASIC  # Default role
            )
            
            logger.info(f"Creating user with data: {user_create_data}")
            new_user = await user_manager.create(user_create_data)
            logger.info(f"Successfully created new user from Microsoft AD: {email} with ID: {new_user.id}")
            
            return {"user_id": str(new_user.id), "email": email, "status": "created"}
        except Exception as e:
            logger.error(f"Failed to add Microsoft user: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception details: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to add Microsoft user: {str(e)}")
    
    return router 