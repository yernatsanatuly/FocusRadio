"""/leaderboard endpoint."""
from fastapi import APIRouter, Query

from app.core.dependencies import Users
from app.models.enums import LeaderboardMetric
from app.schemas.leaderboard import Leaderboard

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("", response_model=Leaderboard, summary="Global leaderboard")
def global_leaderboard(
    service: Users,
    metric: LeaderboardMetric = LeaderboardMetric.XP,
    limit: int = Query(10, ge=1, le=100),
):
    return service.leaderboard(metric, limit)
