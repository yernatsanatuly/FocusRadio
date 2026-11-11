from pydantic import BaseModel

from app.models.enums import LeaderboardMetric


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    display_name: str
    level: int
    value: int


class Leaderboard(BaseModel):
    metric: LeaderboardMetric
    scope: str
    entries: list[LeaderboardEntry]
