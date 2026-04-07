"""Create core business tables: data_sources, ingestion_jobs, metadata_records, classification_results, cost_records, benchmarks, decisions, webhook_logs

Revision ID: 002
Revises: 001_initial_auth
Create Date: 2026-02-16 12:05:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_core_business_tables'
down_revision = '001_initial_auth'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # data_sources table
    op.create_table(
        'data_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('schedule', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_data_sources_id', 'data_sources', ['id'], unique=False)
    op.create_index('ix_data_sources_user_id', 'data_sources', ['user_id'], unique=False)
    
    # ingestion_jobs table
    op.create_table(
        'ingestion_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('data_source_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('celery_task_id', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], ondelete='SET NULL')
    )
    op.create_index('ix_ingestion_jobs_id', 'ingestion_jobs', ['id'], unique=False)
    op.create_index('ix_ingestion_jobs_user_id', 'ingestion_jobs', ['user_id'], unique=False)
    op.create_index('ix_ingestion_jobs_data_source_id', 'ingestion_jobs', ['data_source_id'], unique=False)
    op.create_index('ix_ingestion_jobs_status', 'ingestion_jobs', ['status'], unique=False)
    op.create_index('ix_ingestion_jobs_celery_task_id', 'ingestion_jobs', ['celery_task_id'], unique=False)
    
    # metadata_records table
    op.create_table(
        'metadata_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ingestion_job_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('account_id', sa.String(length=100), nullable=True),
        sa.Column('attributes', sa.JSON(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resource_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resource_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_path', sa.String(length=500), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['ingestion_job_id'], ['ingestion_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_metadata_records_id', 'metadata_records', ['id'], unique=False)
    op.create_index('ix_metadata_records_ingestion_job_id', 'metadata_records', ['ingestion_job_id'], unique=False)
    op.create_index('ix_metadata_records_user_id', 'metadata_records', ['user_id'], unique=False)
    op.create_index('ix_metadata_records_entity_type', 'metadata_records', ['entity_type'], unique=False)
    op.create_index('ix_metadata_records_entity_id', 'metadata_records', ['entity_id'], unique=False)
    op.create_index('ix_metadata_records_provider', 'metadata_records', ['provider'], unique=False)
    
    # classification_results table
    op.create_table(
        'classification_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ingestion_job_id', sa.Integer(), nullable=False),
        sa.Column('metadata_record_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('method', sa.String(length=50), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=True),
        sa.Column('rules_applied', sa.Text(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('is_manual', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('manual_category', sa.String(length=20), nullable=True),
        sa.Column('manual_by', sa.String(length=255), nullable=True),
        sa.Column('manual_at', sa.DateTime(), nullable=True),
        sa.Column('manual_reason', sa.Text(), nullable=True),
        sa.Column('classified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reclassified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['ingestion_job_id'], ['ingestion_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['metadata_record_id'], ['metadata_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_classification_results_id', 'classification_results', ['id'], unique=False)
    op.create_index('ix_classification_results_ingestion_job_id', 'classification_results', ['ingestion_job_id'], unique=False)
    op.create_index('ix_classification_results_metadata_record_id', 'classification_results', ['metadata_record_id'], unique=False)
    op.create_index('ix_classification_results_user_id', 'classification_results', ['user_id'], unique=False)
    op.create_index('ix_classification_results_category', 'classification_results', ['category'], unique=False)
    
    # cost_records table
    op.create_table(
        'cost_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ingestion_job_id', sa.Integer(), nullable=False),
        sa.Column('metadata_record_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('service_type', sa.String(length=100), nullable=False),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('cost_amount', sa.Numeric(15, 6), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('usage_quantity', sa.Numeric(15, 6), nullable=False),
        sa.Column('usage_unit', sa.String(length=50), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('billing_line_item_id', sa.String(length=255), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['ingestion_job_id'], ['ingestion_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['metadata_record_id'], ['metadata_records.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_cost_records_id', 'cost_records', ['id'], unique=False)
    op.create_index('ix_cost_records_ingestion_job_id', 'cost_records', ['ingestion_job_id'], unique=False)
    op.create_index('ix_cost_records_metadata_record_id', 'cost_records', ['metadata_record_id'], unique=False)
    op.create_index('ix_cost_records_user_id', 'cost_records', ['user_id'], unique=False)
    op.create_index('ix_cost_records_resource_id', 'cost_records', ['resource_id'], unique=False)
    op.create_index('ix_cost_records_provider', 'cost_records', ['provider'], unique=False)
    op.create_index('ix_cost_records_service_type', 'cost_records', ['service_type'], unique=False)
    op.create_index('ix_cost_records_period_start', 'cost_records', ['period_start'], unique=False)
    
    # benchmarks table
    op.create_table(
        'benchmarks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('service_type', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('avg_cost_per_unit', sa.Numeric(15, 6), nullable=True),
        sa.Column('min_cost_per_unit', sa.Numeric(15, 6), nullable=True),
        sa.Column('max_cost_per_unit', sa.Numeric(15, 6), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_benchmarks_id', 'benchmarks', ['id'], unique=False)
    op.create_index('ix_benchmarks_user_id', 'benchmarks', ['user_id'], unique=False)
    op.create_index('ix_benchmarks_service_type', 'benchmarks', ['service_type'], unique=False)
    op.create_index('ix_benchmarks_provider', 'benchmarks', ['provider'], unique=False)
    
    # decisions table
    op.create_table(
        'decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cost_record_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('action_type', sa.String(length=20), nullable=False, server_default='review'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('estimated_savings_monthly', sa.Numeric(15, 2), nullable=True),
        sa.Column('estimated_cost_to_implement', sa.Numeric(15, 2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('rule_id', sa.String(length=50), nullable=True),
        sa.Column('rule_explanation', sa.Text(), nullable=True),
        sa.Column('is_automated', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_result', sa.Text(), nullable=True),
        sa.Column('webhook_url', sa.String(length=500), nullable=True),
        sa.Column('webhook_secret', sa.String(length=255), nullable=True),
        sa.Column('webhook_status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('webhook_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('webhook_last_attempt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('webhook_error', sa.Text(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_by', sa.String(length=255), nullable=True),
        sa.Column('dismiss_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cost_record_id'], ['cost_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )
    op.create_index('ix_decisions_id', 'decisions', ['id'], unique=False)
    op.create_index('ix_decisions_cost_record_id', 'decisions', ['cost_record_id'], unique=False)
    op.create_index('ix_decisions_user_id', 'decisions', ['user_id'], unique=False)
    op.create_index('ix_decisions_action_type', 'decisions', ['action_type'], unique=False)
    
    # webhook_logs table
    op.create_table(
        'webhook_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('decision_id', sa.Integer(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('request_payload', sa.Text(), nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['decision_id'], ['decisions.id'], ondelete='CASCADE')
    )
    op.create_index('ix_webhook_logs_id', 'webhook_logs', ['id'], unique=False)
    op.create_index('ix_webhook_logs_decision_id', 'webhook_logs', ['decision_id'], unique=False)


def downgrade() -> None:
    # Drop in reverse order to respect foreign keys
    op.drop_index('ix_webhook_logs_decision_id', table_name='webhook_logs')
    op.drop_index('ix_webhook_logs_id', table_name='webhook_logs')
    op.drop_table('webhook_logs')
    
    op.drop_index('ix_decisions_action_type', table_name='decisions')
    op.drop_index('ix_decisions_user_id', table_name='decisions')
    op.drop_index('ix_decisions_cost_record_id', table_name='decisions')
    op.drop_index('ix_decisions_id', table_name='decisions')
    op.drop_table('decisions')
    
    op.drop_index('ix_benchmarks_provider', table_name='benchmarks')
    op.drop_index('ix_benchmarks_service_type', table_name='benchmarks')
    op.drop_index('ix_benchmarks_user_id', table_name='benchmarks')
    op.drop_index('ix_benchmarks_id', table_name='benchmarks')
    op.drop_table('benchmarks')
    
    op.drop_index('ix_cost_records_period_start', table_name='cost_records')
    op.drop_index('ix_cost_records_service_type', table_name='cost_records')
    op.drop_index('ix_cost_records_provider', table_name='cost_records')
    op.drop_index('ix_cost_records_resource_id', table_name='cost_records')
    op.drop_index('ix_cost_records_user_id', table_name='cost_records')
    op.drop_index('ix_cost_records_metadata_record_id', table_name='cost_records')
    op.drop_index('ix_cost_records_ingestion_job_id', table_name='cost_records')
    op.drop_index('ix_cost_records_id', table_name='cost_records')
    op.drop_table('cost_records')
    
    op.drop_index('ix_classification_results_category', table_name='classification_results')
    op.drop_index('ix_classification_results_user_id', table_name='classification_results')
    op.drop_index('ix_classification_results_metadata_record_id', table_name='classification_results')
    op.drop_index('ix_classification_results_ingestion_job_id', table_name='classification_results')
    op.drop_index('ix_classification_results_id', table_name='classification_results')
    op.drop_table('classification_results')
    
    op.drop_index('ix_metadata_records_provider', table_name='metadata_records')
    op.drop_index('ix_metadata_records_entity_id', table_name='metadata_records')
    op.drop_index('ix_metadata_records_entity_type', table_name='metadata_records')
    op.drop_index('ix_metadata_records_user_id', table_name='metadata_records')
    op.drop_index('ix_metadata_records_ingestion_job_id', table_name='metadata_records')
    op.drop_index('ix_metadata_records_id', table_name='metadata_records')
    op.drop_table('metadata_records')
    
    op.drop_index('ix_ingestion_jobs_celery_task_id', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_status', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_data_source_id', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_user_id', table_name='ingestion_jobs')
    op.drop_index('ix_ingestion_jobs_id', table_name='ingestion_jobs')
    op.drop_table('ingestion_jobs')
    
    op.drop_index('ix_data_sources_user_id', table_name='data_sources')
    op.drop_index('ix_data_sources_id', table_name='data_sources')
    op.drop_table('data_sources')
