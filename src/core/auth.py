"""Authentication module"""

import bcrypt
import hashlib
import os
from typing import Optional, Set
from fastapi import Header, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import config

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def get_provider_api_key_alias(api_key: str) -> str:
    """Build a deterministic provider-style alias for the primary API key."""
    normalized = (api_key or "").strip()
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"sk-flow2api-{digest}"


def get_accepted_api_keys() -> Set[str]:
    """Return all accepted API keys for the public API."""
    accepted: Set[str] = set()

    primary = (config.api_key or "").strip()
    if primary:
        accepted.add(primary)
        provider_alias = get_provider_api_key_alias(primary)
        if provider_alias:
            accepted.add(provider_alias)

    extra_keys = os.environ.get("FLOW2API_EXTRA_API_KEYS", "")
    for raw_key in extra_keys.split(","):
        candidate = raw_key.strip()
        if candidate:
            accepted.add(candidate)

    return accepted

class AuthManager:
    """Authentication manager"""

    @staticmethod
    def verify_api_key(api_key: str) -> bool:
        """Verify API key"""
        return api_key in get_accepted_api_keys()

    @staticmethod
    def verify_admin(username: str, password: str) -> bool:
        """Verify admin credentials"""
        # Compare with current config (which may be from database or config file)
        return username == config.admin_username and password == config.admin_password

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify password"""
        return bcrypt.checkpw(password.encode(), hashed.encode())

async def verify_api_key_header(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify API key from Authorization header"""
    api_key = credentials.credentials
    if not AuthManager.verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


async def verify_api_key_flexible(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(optional_security),
    x_goog_api_key: Optional[str] = Header(None, alias="x-goog-api-key"),
    key: Optional[str] = Query(None),
) -> str:
    """Verify API key from Authorization header, x-goog-api-key header, or key query param."""
    api_key = None

    if credentials is not None:
        api_key = credentials.credentials
    elif x_goog_api_key:
        api_key = x_goog_api_key
    elif key:
        api_key = key

    if not api_key or not AuthManager.verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key
