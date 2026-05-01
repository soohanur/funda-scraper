"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2026-02-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_keys_id'), 'api_keys', ['id'], unique=False)
    op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=True)

    # Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('job_uuid', sa.String(), nullable=False),
        sa.Column('tool_type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True, default='pending'),
        sa.Column('priority', sa.String(), nullable=True, default='normal'),
        sa.Column('progress', sa.Float(), nullable=True, default=0.0),
        sa.Column('input_file_path', sa.String(), nullable=True),
        sa.Column('output_file_path', sa.String(), nullable=True),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('total_rows', sa.Integer(), nullable=True, default=0),
        sa.Column('processed_rows', sa.Integer(), nullable=True, default=0),
        sa.Column('successful_rows', sa.Integer(), nullable=True, default=0),
        sa.Column('failed_rows', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('estimated_completion', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True, default=0),
        sa.Column('celery_task_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)
    op.create_index(op.f('ix_jobs_job_uuid'), 'jobs', ['job_uuid'], unique=True)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_celery_task_id'), 'jobs', ['celery_task_id'], unique=False)

    # Create job_logs table
    op.create_table(
        'job_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('level', sa.String(), nullable=True, default='INFO'),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_logs_id'), 'job_logs', ['id'], unique=False)
    op.create_index(op.f('ix_job_logs_timestamp'), 'job_logs', ['timestamp'], unique=False)

    # Create system_metrics table
    op.create_table(
        'system_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('cpu_percent', sa.Float(), nullable=True),
        sa.Column('memory_percent', sa.Float(), nullable=True),
        sa.Column('disk_percent', sa.Float(), nullable=True),
        sa.Column('active_jobs', sa.Integer(), nullable=True, default=0),
        sa.Column('queued_jobs', sa.Integer(), nullable=True, default=0),
        sa.Column('completed_jobs_today', sa.Integer(), nullable=True, default=0),
        sa.Column('failed_jobs_today', sa.Integer(), nullable=True, default=0),
        sa.Column('avg_job_duration', sa.Float(), nullable=True),
        sa.Column('success_rate', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_metrics_id'), 'system_metrics', ['id'], unique=False)
    op.create_index(op.f('ix_system_metrics_timestamp'), 'system_metrics', ['timestamp'], unique=False)

    # Create tool_configs table
    op.create_table(
        'tool_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tool_type', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tool_configs_id'), 'tool_configs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tool_configs_id'), table_name='tool_configs')
    op.drop_table('tool_configs')
    
    op.drop_index(op.f('ix_system_metrics_timestamp'), table_name='system_metrics')
    op.drop_index(op.f('ix_system_metrics_id'), table_name='system_metrics')
    op.drop_table('system_metrics')
    
    op.drop_index(op.f('ix_job_logs_timestamp'), table_name='job_logs')
    op.drop_index(op.f('ix_job_logs_id'), table_name='job_logs')
    op.drop_table('job_logs')
    
    op.drop_index(op.f('ix_jobs_celery_task_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_created_at'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_job_uuid'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_id'), table_name='jobs')
    op.drop_table('jobs')
    
    op.drop_index(op.f('ix_api_keys_key_hash'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_id'), table_name='api_keys')
    op.drop_table('api_keys')
    
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
