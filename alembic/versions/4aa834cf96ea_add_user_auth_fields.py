"""add_user_auth_fields

Revision ID: 4aa834cf96ea
Revises: 9458035c95c7
Create Date: 2026-11-26 11:01:01.361866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4aa834cf96ea"
down_revision: Union[str, Sequence[str], None] = "9458035c95c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role_enum = postgresql.ENUM(
    "user",
    "admin",
    name="user_role_enum",
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    user_role_enum.create(bind, checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "hashed_password",
            sa.String(length=255),
            server_default="!unusable!",
            nullable=False,
        ),
    )
    op.alter_column("users", "hashed_password", server_default=None)

    op.add_column(
        "users",
        sa.Column(
            "role",
            user_role_enum,
            server_default="user",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_column("users", "role")
    op.drop_column("users", "hashed_password")

    bind = op.get_bind()
    user_role_enum.drop(bind, checkfirst=True)
