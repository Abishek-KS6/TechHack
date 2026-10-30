"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use SQLAlchemy metadata create_all for portable dialect creation
    from app.infrastructure.db.models import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.infrastructure.db.models import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
