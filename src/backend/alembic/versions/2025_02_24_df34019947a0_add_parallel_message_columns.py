"""Add parallel message columns

Revision ID: df34019947a0
Revises: 74ba7e1b4810
Create Date: 2025-02-24 23:42:57.206152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df34019947a0'
down_revision: Union[str, None] = '74ba7e1b4810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('messages', sa.Column('is_parallel', sa.Boolean(), nullable=True))
    op.add_column('messages', sa.Column('parallel_group_id', sa.String(), nullable=True))
    op.add_column('messages', sa.Column('parallel_variant', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('messages', 'parallel_variant')
    op.drop_column('messages', 'parallel_group_id')
    op.drop_column('messages', 'is_parallel')
    # ### end Alembic commands ###
