"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Initial schema is generated from the canonical SQLAlchemy models.
    # This guarantees migrations and models never drift apart.
    from app.db.models import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app.db.models import Base
    Base.metadata.drop_all(bind=op.get_bind())
