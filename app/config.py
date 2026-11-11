import os


class Settings:
    app_name: str = "FocusRadio API"
    version: str = "1.0.0"

    seconds_per_minute: float = float(os.getenv("FOCUSRADIO_SECONDS_PER_MINUTE", "60"))

    seed_demo_data: bool = os.getenv("FOCUSRADIO_SEED", "1") == "1"

    max_pauses_per_session: int = 3
    max_pause_minutes: int = 15
    min_focus_minutes: int = 1
    max_focus_minutes: int = 180

    xp_per_focus_minute: int = 2
    xp_per_early_minute: int = 1
    xp_full_completion_bonus: int = 20
    xp_no_pause_bonus: int = 10
    xp_streak_bonus_per_day: int = 5
    xp_streak_bonus_cap_days: int = 10
    xp_room_bonus: int = 5
    xp_task_completed: int = 15


settings = Settings()
