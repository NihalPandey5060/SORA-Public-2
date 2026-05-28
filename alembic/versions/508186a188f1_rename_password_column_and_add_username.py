"""rename password column and add username

Revision ID: 508186a188f1
Revises: a97d3eba14b2
Create Date: 2026-01-04 23:16:35.962638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '508186a188f1'
down_revision: Union[str, Sequence[str], None] = 'a97d3eba14b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('hashed_password', new_column_name='password')
        batch_op.add_column(sa.Column('username', sa.String(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password', new_column_name='hashed_password')
        batch_op.drop_column('username')
