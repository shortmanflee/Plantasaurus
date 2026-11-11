"""backups

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import app.db


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('backups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('counts', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('completed_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('backups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_backups_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('backups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_backups_status'))
    op.drop_table('backups')
