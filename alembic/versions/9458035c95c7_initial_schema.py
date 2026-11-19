"""initial_schema

Revision ID: 9458035c95c7
Revises:
Create Date: 2026-11-19 14:33:37.218283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9458035c95c7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

genre_enum = postgresql.ENUM(
    "lofi", "ambient", "nature", "classical", "white_noise", "synthwave",
    name="genre_enum",
    create_type=False,
)
mood_enum = postgresql.ENUM(
    "focus", "break", "energize", "calm",
    name="mood_enum",
    create_type=False,
)
task_priority_enum = postgresql.ENUM(
    "low", "medium", "high",
    name="task_priority_enum",
    create_type=False,
)
task_status_enum = postgresql.ENUM(
    "todo", "in_progress", "done",
    name="task_status_enum",
    create_type=False,
)
session_mode_enum = postgresql.ENUM(
    "pomodoro", "short", "deep_work", "custom",
    name="session_mode_enum",
    create_type=False,
)
session_status_enum = postgresql.ENUM(
    "active", "paused", "completed", "ended_early", "cancelled",
    name="session_status_enum",
    create_type=False,
)

ALL_ENUMS = (
    genre_enum,
    mood_enum,
    task_priority_enum,
    task_status_enum,
    session_mode_enum,
    session_status_enum,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("artist", sa.String(length=100), nullable=False),
        sa.Column("genre", genre_enum, nullable=False),
        sa.Column("mood", mood_enum, nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("bpm", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("bpm IS NULL OR (bpm >= 40 AND bpm <= 220)", name=op.f("ck_tracks_bpm_range")),
        sa.CheckConstraint("duration_seconds >= 30 AND duration_seconds <= 7200", name=op.f("ck_tracks_duration_range")),
        sa.CheckConstraint("energy >= 1 AND energy <= 10", name=op.f("ck_tracks_energy_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracks")),
    )
    op.create_index(op.f("ix_tracks_genre"), "tracks", ["genre"], unique=False)
    op.create_index(op.f("ix_tracks_mood"), "tracks", ["mood"], unique=False)
    op.create_index(
        "uq_tracks_title_artist_lower",
        "tracks",
        [sa.literal_column("lower(title)"), sa.literal_column("lower(artist)")],
        unique=True,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("bio", sa.String(length=200), nullable=True),
        sa.Column("xp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_focus_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("longest_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_focus_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("completed_sessions >= 0", name=op.f("ck_users_completed_sessions_non_negative")),
        sa.CheckConstraint("completed_tasks >= 0", name=op.f("ck_users_completed_tasks_non_negative")),
        sa.CheckConstraint("current_streak >= 0", name=op.f("ck_users_current_streak_non_negative")),
        sa.CheckConstraint("longest_streak >= 0", name=op.f("ck_users_longest_streak_non_negative")),
        sa.CheckConstraint("total_focus_minutes >= 0", name=op.f("ck_users_total_focus_minutes_non_negative")),
        sa.CheckConstraint("xp >= 0", name=op.f("ck_users_xp_non_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="8", nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("access_code", sa.String(length=12), nullable=True),
        sa.Column("preferred_genre", genre_enum, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=20)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
        sa.Column("current_track_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(is_private = true AND access_code IS NOT NULL) OR (is_private = false AND access_code IS NULL)",
            name=op.f("ck_rooms_privacy_access_code_consistency"),
        ),
        sa.CheckConstraint("capacity >= 2 AND capacity <= 50", name=op.f("ck_rooms_capacity_range")),
        sa.ForeignKeyConstraint(["current_track_id"], ["tracks.id"], name=op.f("fk_rooms_current_track_id_tracks"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_rooms_owner_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rooms")),
    )
    op.create_index(op.f("ix_rooms_current_track_id"), "rooms", ["current_track_id"], unique=False)
    op.create_index(op.f("ix_rooms_owner_id"), "rooms", ["owner_id"], unique=False)
    op.create_index("uq_rooms_name_lower", "rooms", [sa.literal_column("lower(name)")], unique=True)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("priority", task_priority_enum, server_default="medium", nullable=False),
        sa.Column("status", task_status_enum, server_default="todo", nullable=False),
        sa.Column("estimated_pomodoros", sa.Integer(), server_default="1", nullable=False),
        sa.Column("completed_pomodoros", sa.Integer(), server_default="0", nullable=False),
        sa.Column("xp_awarded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("completed_pomodoros >= 0", name=op.f("ck_tasks_completed_pomodoros_non_negative")),
        sa.CheckConstraint("estimated_pomodoros >= 1 AND estimated_pomodoros <= 20", name=op.f("ck_tasks_estimated_pomodoros_range")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tasks_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_user_id"), "tasks", ["user_id"], unique=False)
    op.create_index(
        "uq_tasks_open_user_title_lower",
        "tasks",
        ["user_id", sa.literal_column("lower(title)")],
        unique=True,
        postgresql_where=sa.text("status != 'done'"),
    )

    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("mode", session_mode_enum, nullable=False),
        sa.Column("status", session_status_enum, server_default="active", nullable=False),
        sa.Column("focus_minutes", sa.Integer(), nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_paused_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("pause_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("focused_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("xp_earned", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("break_minutes >= 0 AND break_minutes <= 60", name=op.f("ck_focus_sessions_break_minutes_range")),
        sa.CheckConstraint("focus_minutes >= 1 AND focus_minutes <= 180", name=op.f("ck_focus_sessions_focus_minutes_range")),
        sa.CheckConstraint("focused_seconds >= 0", name=op.f("ck_focus_sessions_focused_seconds_non_negative")),
        sa.CheckConstraint("pause_count >= 0 AND pause_count <= 3", name=op.f("ck_focus_sessions_pause_count_range")),
        sa.CheckConstraint("total_paused_seconds >= 0", name=op.f("ck_focus_sessions_total_paused_seconds_non_negative")),
        sa.CheckConstraint("xp_earned >= 0", name=op.f("ck_focus_sessions_xp_earned_non_negative")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name=op.f("fk_focus_sessions_room_id_rooms"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name=op.f("fk_focus_sessions_task_id_tasks"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_focus_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_focus_sessions")),
    )
    op.create_index(op.f("ix_focus_sessions_room_id"), "focus_sessions", ["room_id"], unique=False)
    op.create_index(op.f("ix_focus_sessions_status"), "focus_sessions", ["status"], unique=False)
    op.create_index(op.f("ix_focus_sessions_task_id"), "focus_sessions", ["task_id"], unique=False)
    op.create_index(op.f("ix_focus_sessions_user_id"), "focus_sessions", ["user_id"], unique=False)
    op.create_index(
        "uq_focus_sessions_one_active_per_user",
        "focus_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )

    op.create_table(
        "room_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name=op.f("fk_room_members_room_id_rooms"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_room_members_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_members")),
        sa.UniqueConstraint("user_id", name=op.f("uq_room_members_user_id")),
    )
    op.create_index(op.f("ix_room_members_room_id"), "room_members", ["room_id"], unique=False)

    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["focus_sessions.id"], name=op.f("fk_user_achievements_session_id_focus_sessions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_achievements_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_achievements")),
        sa.UniqueConstraint("user_id", "code", name="uq_user_achievements_user_code"),
    )
    op.create_index(op.f("ix_user_achievements_session_id"), "user_achievements", ["session_id"], unique=False)
    op.create_index(op.f("ix_user_achievements_user_id"), "user_achievements", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_achievements_user_id"), table_name="user_achievements")
    op.drop_index(op.f("ix_user_achievements_session_id"), table_name="user_achievements")
    op.drop_table("user_achievements")

    op.drop_index(op.f("ix_room_members_room_id"), table_name="room_members")
    op.drop_table("room_members")

    op.drop_index(
        "uq_focus_sessions_one_active_per_user",
        table_name="focus_sessions",
        postgresql_where=sa.text("status IN ('active', 'paused')"),
    )
    op.drop_index(op.f("ix_focus_sessions_user_id"), table_name="focus_sessions")
    op.drop_index(op.f("ix_focus_sessions_task_id"), table_name="focus_sessions")
    op.drop_index(op.f("ix_focus_sessions_status"), table_name="focus_sessions")
    op.drop_index(op.f("ix_focus_sessions_room_id"), table_name="focus_sessions")
    op.drop_table("focus_sessions")

    op.drop_index(
        "uq_tasks_open_user_title_lower",
        table_name="tasks",
        postgresql_where=sa.text("status != 'done'"),
    )
    op.drop_index(op.f("ix_tasks_user_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("uq_rooms_name_lower", table_name="rooms")
    op.drop_index(op.f("ix_rooms_owner_id"), table_name="rooms")
    op.drop_index(op.f("ix_rooms_current_track_id"), table_name="rooms")
    op.drop_table("rooms")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index("uq_tracks_title_artist_lower", table_name="tracks")
    op.drop_index(op.f("ix_tracks_mood"), table_name="tracks")
    op.drop_index(op.f("ix_tracks_genre"), table_name="tracks")
    op.drop_table("tracks")

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
