"""open plantbook config

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import app.db


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('opb_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.String(length=255), nullable=True),
    sa.Column('client_secret', sa.Text(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('opb_config')
