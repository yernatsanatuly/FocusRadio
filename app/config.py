"""Application settings (read from environment variables)."""
import os


class Settings:
    app_name: str = "FocusRadio API"
    version: str = "1.0.0"

    # How many real seconds make up one "timer minute".
    # Default 60 (real time). For demos in Swagger set
    #   FOCUSRADIO_SECONDS_PER_MINUTE=1
    # so a 25-minute pomodoro finishes in 25 real seconds.
    seconds_per_minute: float = float(os.getenv("FOCUSRADIO_SECONDS_PER_MINUTE", "60"))

    # Load demo users / rooms / tracks on startup.
    seed_demo_data: bool = os.getenv("FOCUSRADIO_SEED", "1") == "1"

    # Business rules
    max_pauses_per_session: int = 3
    max_pause_minutes: int = 15          # a single pause longer than this auto-cancels on resume
    min_focus_minutes: int = 1
    max_focus_minutes: int = 180

    # XP rules
    xp_per_focus_minute: int = 2
    xp_per_early_minute: int = 1
    xp_full_completion_bonus: int = 20
    xp_no_pause_bonus: int = 10
    xp_streak_bonus_per_day: int = 5
    xp_streak_bonus_cap_days: int = 10
    xp_room_bonus: int = 5               # focusing together with others
    xp_task_completed: int = 15


settings = Settings()
