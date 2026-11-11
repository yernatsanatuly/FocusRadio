from typing import Optional

from fastapi import APIRouter, Query, status

from app.core.dependencies import ActingUserId, Limit, Offset, Rooms
from app.models.enums import Genre, LeaderboardMetric
from app.schemas.common import Page, error_responses
from app.schemas.leaderboard import Leaderboard
from app.schemas.rooms import (
    JoinRoomRequest,
    LeaveRoomResult,
    RoomActivity,
    RoomCreate,
    RoomResponse,
    RoomUpdate,
    SetTrackRequest,
    TrackRecommendation,
)

router = APIRouter(prefix="/rooms", tags=["Rooms"])


@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED,
             responses=error_responses(404, 409, 422),
             summary="Create a room (owner joins automatically)")
def create_room(data: RoomCreate, service: Rooms):
    return service.create(data)


@router.get("", response_model=Page[RoomResponse], summary="Browse rooms")
def list_rooms(
    service: Rooms,
    search: Optional[str] = Query(None, min_length=1, max_length=60),
    tag: Optional[str] = Query(None, min_length=2, max_length=20),
    genre: Optional[Genre] = None,
    is_private: Optional[bool] = None,
    has_space: Optional[bool] = Query(None, description="Only rooms with free spots"),
    limit: Limit = 20,
    offset: Offset = 0,
):
    return service.list(search=search, tag=tag, genre=genre, is_private=is_private,
                        has_space=has_space, limit=limit, offset=offset)


@router.get("/{room_id}", response_model=RoomResponse, responses=error_responses(404),
            summary="Get a room")
def get_room(room_id: int, service: Rooms):
    return service.get(room_id)


@router.patch("/{room_id}", response_model=RoomResponse,
              responses=error_responses(403, 404, 409, 422), summary="Update room (owner only)")
def update_room(room_id: int, data: RoomUpdate, acting_user_id: ActingUserId, service: Rooms):
    return service.update(room_id, acting_user_id, data)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=error_responses(403, 404), summary="Close room (owner only)")
def delete_room(room_id: int, acting_user_id: ActingUserId, service: Rooms):
    service.delete(room_id, acting_user_id)


@router.get("/{room_id}/members", response_model=RoomActivity, responses=error_responses(404),
            summary="Members and their live focus status")
def room_members(room_id: int, service: Rooms):
    return service.activity(room_id)


@router.post("/{room_id}/members", response_model=RoomResponse,
             status_code=status.HTTP_201_CREATED,
             responses=error_responses(403, 404, 409, 422), summary="Join a room")
def join_room(room_id: int, data: JoinRoomRequest, service: Rooms):
    return service.join(room_id, data)


@router.delete("/{room_id}/members/{user_id}", response_model=LeaveRoomResult,
               responses=error_responses(403, 404),
               summary="Leave the room (self) or kick a member (owner)")
def leave_room(room_id: int, user_id: int, acting_user_id: ActingUserId, service: Rooms):
    return service.remove_member(room_id, user_id, acting_user_id)


@router.put("/{room_id}/track", response_model=RoomResponse,
            responses=error_responses(403, 404, 409, 422),
            summary="Set the room's now-playing track (members only)")
def set_track(room_id: int, data: SetTrackRequest, acting_user_id: ActingUserId, service: Rooms):
    return service.set_track(room_id, acting_user_id, data.track_id)


@router.delete("/{room_id}/track", response_model=RoomResponse,
               responses=error_responses(403, 404, 409), summary="Stop the music (members only)")
def stop_track(room_id: int, acting_user_id: ActingUserId, service: Rooms):
    return service.stop_track(room_id, acting_user_id)


@router.get("/{room_id}/recommended-tracks", response_model=TrackRecommendation,
            responses=error_responses(404),
            summary="Adaptive audio: tracks that fit the room's current phase")
def recommended_tracks(room_id: int, service: Rooms,
                       limit: int = Query(5, ge=1, le=20)):
    return service.recommend_tracks(room_id, limit)


@router.get("/{room_id}/leaderboard", response_model=Leaderboard,
            responses=error_responses(404), summary="Leaderboard among room members")
def room_leaderboard(room_id: int, service: Rooms,
                     metric: LeaderboardMetric = LeaderboardMetric.XP,
                     limit: int = Query(10, ge=1, le=50)):
    return service.leaderboard(room_id, metric, limit)
