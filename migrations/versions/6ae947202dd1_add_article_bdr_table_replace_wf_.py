"""add article_bdr table, replace wf_article_mapping and detailed_article

Revision ID: 6ae947202dd1
Revises: 73325412b044
Create Date: 2026-04-29 12:30:11.129173

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6ae947202dd1'
down_revision: Union[str, None] = '73325412b044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop old wf_article_mapping (article_code/article_label/work_type_id columns)
    op.drop_index('ix_wf_article_mapping_article_code', table_name='wf_article_mapping')
    op.drop_index('ix_wf_article_mapping_work_type_id', table_name='wf_article_mapping')
    op.drop_table('wf_article_mapping')

    # 2. Create article_bdrs master table
    op.create_table(
        'article_bdrs',
        sa.Column('code_1c', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='article_bdrs_pkey'),
        sa.UniqueConstraint('code_1c', name='uq_article_bdrs_code_1c'),
    )
    op.create_index('ix_article_bdrs_code_1c', 'article_bdrs', ['code_1c'], unique=True)

    # 3. Create new wf_article_mapping as M2M link (article_bdr_id + work_type_id)
    op.create_table(
        'wf_article_mapping',
        sa.Column('article_bdr_id', sa.UUID(), nullable=False),
        sa.Column('work_type_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ['article_bdr_id'], ['article_bdrs.id'], name='fk_wf_article_mapping_article_bdr_id'
        ),
        sa.ForeignKeyConstraint(
            ['work_type_id'], ['work_types.id'], name='fk_wf_article_mapping_work_type_id'
        ),
        sa.PrimaryKeyConstraint('id', name='wf_article_mapping_pkey'),
    )
    op.create_index('ix_wf_article_mapping_article_bdr_id', 'wf_article_mapping', ['article_bdr_id'], unique=False)
    op.create_index('ix_wf_article_mapping_work_type_id', 'wf_article_mapping', ['work_type_id'], unique=False)

    # 4. Add article_bdr_id to wf_budget_items
    op.add_column('wf_budget_items', sa.Column('article_bdr_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_wf_budget_items_article_bdr_id'), 'wf_budget_items', ['article_bdr_id'], unique=False)
    op.create_foreign_key(
        'fk_wf_budget_items_article_bdr_id', 'wf_budget_items', 'article_bdrs', ['article_bdr_id'], ['id']
    )

    # 5. Drop detailed_article
    op.drop_column('wf_budget_items', 'detailed_article')


def downgrade() -> None:
    op.add_column('wf_budget_items', sa.Column('detailed_article', sa.VARCHAR(length=500), nullable=True))
    op.drop_constraint('fk_wf_budget_items_article_bdr_id', 'wf_budget_items', type_='foreignkey')
    op.drop_index(op.f('ix_wf_budget_items_article_bdr_id'), table_name='wf_budget_items')
    op.drop_column('wf_budget_items', 'article_bdr_id')

    op.drop_index('ix_wf_article_mapping_work_type_id', table_name='wf_article_mapping')
    op.drop_index('ix_wf_article_mapping_article_bdr_id', table_name='wf_article_mapping')
    op.drop_table('wf_article_mapping')

    op.drop_index('ix_article_bdrs_code_1c', table_name='article_bdrs')
    op.drop_table('article_bdrs')

    op.create_table(
        'wf_article_mapping',
        sa.Column('article_code', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
        sa.Column('article_label', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('work_type_id', sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['work_type_id'], ['work_types.id'], name='fk_wf_article_mapping_work_type_id'),
        sa.PrimaryKeyConstraint('id', name='wf_article_mapping_pkey'),
    )
    op.create_index('ix_wf_article_mapping_work_type_id', 'wf_article_mapping', ['work_type_id'], unique=False)
    op.create_index('ix_wf_article_mapping_article_code', 'wf_article_mapping', ['article_code'], unique=False)
