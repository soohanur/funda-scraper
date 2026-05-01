"""
Database models for automation platform
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, Float, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum
from .database import Base


class JobStatus(str, enum.Enum):
    """Job execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobPriority(str, enum.Enum):
    """Job execution priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ToolType(str, enum.Enum):
    """Available automation tools."""
    FUNDA = "funda"  # Funda property scraper


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.username}>"


class APIKey(Base):
    """API Key for programmatic access."""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_hash = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")
    
    def __repr__(self):
        return f"<APIKey {self.name}>"


class Job(Base):
    """Job execution tracking."""
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Job identification
    job_uuid = Column(String, unique=True, index=True, nullable=False)
    tool_type = Column(SQLEnum(ToolType), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    
    # Job execution
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, index=True)
    priority = Column(SQLEnum(JobPriority), default=JobPriority.NORMAL)
    progress = Column(Float, default=0.0)  # 0-100
    
    # Input/Output
    input_file_path = Column(String)
    output_file_path = Column(String)
    display_filename = Column(String)  # User-friendly display name (may have duplicates)
    config = Column(JSON)  # Tool-specific configuration
    
    # Results
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    successful_rows = Column(Integer, default=0)
    failed_rows = Column(Integer, default=0)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_completion = Column(DateTime)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Celery task tracking
    celery_task_id = Column(String, index=True)
    
    # Relationships
    user = relationship("User", back_populates="jobs")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Job {self.job_uuid} - {self.status}>"


class JobLog(Base):
    """Detailed job execution logs."""
    __tablename__ = "job_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String, default="INFO")  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    log_metadata = Column(JSON)  # Additional structured data (renamed from 'metadata' to avoid SQLAlchemy conflict)
    
    # Relationships
    job = relationship("Job", back_populates="logs")
    
    def __repr__(self):
        return f"<JobLog {self.level} - {self.timestamp}>"


class SystemMetrics(Base):
    """System performance metrics for monitoring."""
    __tablename__ = "system_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Resource usage
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    disk_percent = Column(Float)
    
    # Job statistics
    active_jobs = Column(Integer, default=0)
    queued_jobs = Column(Integer, default=0)
    completed_jobs_today = Column(Integer, default=0)
    failed_jobs_today = Column(Integer, default=0)
    
    # Performance
    avg_job_duration = Column(Float)  # seconds
    success_rate = Column(Float)  # percentage
    
    def __repr__(self):
        return f"<SystemMetrics {self.timestamp}>"


class ToolConfig(Base):
    """Tool-specific configuration presets."""
    __tablename__ = "tool_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    tool_type = Column(SQLEnum(ToolType), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    config = Column(JSON, nullable=False)
    is_default = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<ToolConfig {self.tool_type} - {self.name}>"
