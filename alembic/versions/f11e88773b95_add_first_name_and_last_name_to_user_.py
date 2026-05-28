"""add first name and last name to user table

Revision ID: f11e88773b95
Revises: 508186a188f1
Create Date: 2026-01-04 23:41:31.239511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f11e88773b95'
down_revision: Union[str, Sequence[str], None] = '508186a188f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("last_name", sa.String(length=50), nullable=True))
        batch_op.drop_column("username")
    


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("username", sa.String(length=50), nullable=True))
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")