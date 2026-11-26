"""Add mandatory password change flag to user accounts."""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_must_change_password"
down_revision = "0005_transfer_segment_closure"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("users", "must_change_password")
