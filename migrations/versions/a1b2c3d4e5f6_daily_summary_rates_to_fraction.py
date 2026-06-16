"""daily_summaries: widen rate columns to Numeric(6,4) (0..1 fraction scale)

Revision ID: a1b2c3d4e5f6
Revises: c5e9a740f218
Create Date: 2026-06-15 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c5e9a740f218"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RATE_COLUMNS = ("completion_rate", "weighted_completion", "submission_rate")


def upgrade() -> None:
    # Rates move from a 0..100 percentage in Numeric(5,2) to a 0..1 fraction in
    # Numeric(6,4). The USING clause divides existing rows by 100 *as part of* the
    # type change, so old percentages (e.g. 85.00) never have to fit the narrower
    # target type before being rescaled.
    for column in _RATE_COLUMNS:
        op.alter_column(
            "daily_summaries",
            column,
            type_=sa.Numeric(6, 4),
            existing_type=sa.Numeric(5, 2),
            existing_nullable=False,
            postgresql_using=f"{column} / 100",
        )


def downgrade() -> None:
    for column in _RATE_COLUMNS:
        op.alter_column(
            "daily_summaries",
            column,
            type_=sa.Numeric(5, 2),
            existing_type=sa.Numeric(6, 4),
            existing_nullable=False,
            postgresql_using=f"{column} * 100",
        )
