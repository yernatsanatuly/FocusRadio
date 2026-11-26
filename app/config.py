from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "FocusRadio API"
    version: str = "3.0.0"

    database_url: str = Field(
        default="postgresql+psycopg://focusradio:focusradio@localhost:5433/focusradio",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    test_database_url: str = Field(
        default="postgresql+psycopg://focusradio:focusradio@localhost:5433/focusradio_test",
        validation_alias=AliasChoices("TEST_DATABASE_URL", "test_database_url"),
    )
    sql_echo: bool = Field(
        default=False,
        validation_alias=AliasChoices("SQL_ECHO", "sql_echo"),
    )

    jwt_secret_key: str = Field(
        default="focusradio-dev-secret-key-change-in-production-32bytes",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "jwt_secret_key"),
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("JWT_ALGORITHM", "jwt_algorithm"),
    )
    access_token_expire_minutes: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "ACCESS_TOKEN_EXPIRE_MINUTES", "access_token_expire_minutes"
        ),
    )

    seconds_per_minute: float = Field(
        default=60.0,
        validation_alias=AliasChoices("FOCUSRADIO_SECONDS_PER_MINUTE", "seconds_per_minute"),
    )
    seed_demo_data: bool = Field(
        default=True,
        validation_alias=AliasChoices("FOCUSRADIO_SEED", "seed_demo_data"),
    )

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
