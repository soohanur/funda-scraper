"""
Security utilities for authentication and authorization
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token authentication
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token.
    
    Args:
        data: Payload to encode (typically {"sub": user_id})
        expires_delta: Token expiration time
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode JWT token and extract user ID.
    
    Args:
        token: JWT token string
        
    Returns:
        User ID if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        return user_id
    except JWTError:
        return None


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency to get current authenticated user.
    
    Args:
        credentials: HTTP Bearer token
        
    Returns:
        User ID
        
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    user_id = decode_access_token(token)
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed for given key."""
        now = datetime.utcnow()
        
        # Clean old entries
        self.requests = {
            k: v for k, v in self.requests.items()
            if now - v[-1] < timedelta(seconds=self.window_seconds)
        }
        
        # Check current key
        if key not in self.requests:
            self.requests[key] = [now]
            return True
        
        # Remove old timestamps for this key
        self.requests[key] = [
            ts for ts in self.requests[key]
            if now - ts < timedelta(seconds=self.window_seconds)
        ]
        
        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(now)
            return True
        
        return False


# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
