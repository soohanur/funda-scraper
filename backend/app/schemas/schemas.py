"""
Pydantic schemas for request/response validation
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum


# Enums matching database models
class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ToolType(str, Enum):
    FUNDA = "funda"  # Funda property scraper


# ===== User Schemas =====

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    admin_key: str = Field(..., min_length=1)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[str] = None


# ===== Job Schemas =====

class JobConfigBase(BaseModel):
    """Base configuration for all tools."""
    max_workers: int = Field(default=3, ge=1, le=5)
    headless_mode: bool = True
    timeout: int = Field(default=30, ge=10, le=120)


class JobCreate(BaseModel):
    tool_type: ToolType
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: JobPriority = JobPriority.NORMAL
    config: Optional[Dict[str, Any]] = None


class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[JobPriority] = None
    config: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    id: int
    job_uuid: str
    user_id: int
    tool_type: ToolType
    name: str
    description: Optional[str]
    status: JobStatus
    priority: JobPriority
    progress: float
    
    input_file_path: Optional[str]
    output_file_path: Optional[str]
    display_filename: Optional[str]
    
    total_rows: int
    processed_rows: int
    successful_rows: int
    failed_rows: int
    
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_completion: Optional[datetime]
    
    error_message: Optional[str]
    retry_count: int
    
    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    page_size: int


class JobProgressUpdate(BaseModel):
    progress: float = Field(..., ge=0, le=100)
    processed_rows: int
    successful_rows: int
    failed_rows: int
    message: Optional[str] = None


# ===== File Upload Schemas =====

class FileUploadResponse(BaseModel):
    filename: str
    file_path: str
    size: int
    uploaded_at: datetime


class FileListResponse(BaseModel):
    files: List[Dict[str, Any]]
    total: int


# ===== System Schemas =====

class HealthCheck(BaseModel):
    status: str
    version: str
    timestamp: datetime
    database: str
    redis: str
    celery: str


class SystemStats(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    active_jobs: int
    queued_jobs: int
    completed_jobs_today: int
    failed_jobs_today: int
    success_rate: float


# ===== Job Log Schemas =====

class JobLogCreate(BaseModel):
    level: str = "INFO"
    message: str
    metadata: Optional[Dict[str, Any]] = None


class JobLogResponse(BaseModel):
    id: int
    job_id: int
    timestamp: datetime
    level: str
    message: str
    metadata: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True

# ===== Notification Schemas =====

class NotificationType(str, Enum):
    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NotificationCreate(BaseModel):
    type: NotificationType
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    job_uuid: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationUpdate(BaseModel):
    read: Optional[bool] = None


class NotificationResponse(BaseModel):
    id: str  # notification_uuid
    type: NotificationType
    title: str
    message: str
    read: bool
    job_uuid: Optional[str]
    metadata: Optional[Dict[str, Any]]
    timestamp: datetime  # created_at
    
    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    count: int

# ===== WebSocket Schemas =====

class WebSocketMessage(BaseModel):
    type: str  # "job_update", "log", "system_alert"
    job_uuid: Optional[str] = None
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ===== Tool Config Schemas =====

class ToolConfigCreate(BaseModel):
    tool_type: ToolType
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_default: bool = False


class ToolConfigResponse(BaseModel):
    id: int
    tool_type: ToolType
    name: str
    description: Optional[str]
    config: Dict[str, Any]
    is_default: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ===== Error Schemas =====

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
