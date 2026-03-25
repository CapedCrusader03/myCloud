"""create_uploads_and_chunks_tables

Revision ID: b50b9325f431
Revises: 
Create Date: 2026-03-25 04:16:14.484812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b50b9325f431'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'uploads',
        sa.Column('id', sa.UUID, primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('total_size', sa.BigInteger(), nullable=False),
        sa.Column('chunk_size', sa.Integer(), nullable=False),
        sa.Column('total_chunks', sa.Integer(), nullable=False),
        sa.Column('file_checksum', sa.String(255), nullable=False),
        sa.Column('status', sa.String(100), nullable=False),
        sa.Column('api_key', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'chunks',
        sa.Column('id', sa.UUID, primary_key=True),
        sa.Column('upload_id', sa.UUID, sa.ForeignKey('uploads.id'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('checksum', sa.String(255), nullable=False),
        sa.Column('checksum_valid', sa.Boolean(), nullable=False),
        sa.Column('is_uploaded', sa.Boolean(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('idx_chunks_upload_id', 'chunks', ['upload_id', 'chunk_index'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_chunks_upload_id', 'chunks')
    op.drop_table('chunks')
    op.drop_table('uploads')
