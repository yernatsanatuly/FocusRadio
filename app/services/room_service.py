"""Coworking room workflow: create/join/leave rooms, ownership transfer,
live activity and adaptive soundtrack."""
from __future__ import annotations

from typing import Optional

from app.core.database import Database
from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.models.entities import Room
from app.models.enums import Genre, LeaderboardMetric, Mood, SessionStatus
from app.schemas.leaderboard import Leaderboard
from app.schemas.rooms import (
    JoinRoomRequest,
    RoomActivity,
    RoomCreate,
    RoomMember,
    RoomResponse,
    RoomUpdate,
    TrackRecommendation,
)
from app.schemas.tracks import TrackResponse
from app.services import gamification
from app.services.common import (
    ensure_actor_exists,
    find_active_session,
    get_room,
    get_track,
    get_user,
    paginate,
)
from app.services.session_service import remaining_seconds


class RoomService:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---------------------------------------------------------------- presenters
    def to_response(self, room: Room) -> RoomResponse:
        track = self.db.tracks.get(room.current_track_id) if room.current_track_id else None
        return RoomResponse(
            id=room.id, name=room.name, description=room.description, owner_id=room.owner_id,
            capacity=room.capacity, member_count=len(room.member_ids),
            available_spots=room.capacity - len(room.member_ids),
            is_private=room.is_private, preferred_genre=room.preferred_genre, tags=room.tags,
            current_track=TrackResponse.model_validate(track) if track else None,
            created_at=room.created_at,
        )

    # ---------------------------------------------------------------- queries
    def list(self, *, search: Optional[str], tag: Optional[str], genre: Optional[Genre],
             is_private: Optional[bool], has_space: Optional[bool],
             limit: int, offset: int) -> dict:
        def match(r: Room) -> bool:
            if search and search.lower() not in (r.name + " " + (r.description or "")).lower():
                return False
            if tag and tag.lower() not in r.tags:
                return False
            if genre and r.preferred_genre != genre:
                return False
            if is_private is not None and r.is_private != is_private:
                return False
            if has_space is not None and (len(r.member_ids) < r.capacity) != has_space:
                return False
            return True

        rooms = sorted((r for r in self.db.rooms.values() if match(r)),
                       key=lambda r: (-len(r.member_ids), r.id))
        page = paginate(rooms, limit, offset)
        page["items"] = [self.to_response(r) for r in page["items"]]
        return page

    def get(self, room_id: int) -> RoomResponse:
        return self.to_response(get_room(self.db, room_id))

    def activity(self, room_id: int) -> RoomActivity:
        room = get_room(self.db, room_id)
        members: list[RoomMember] = []
        for uid in room.member_ids:
            user = self.db.users[uid]
            session = find_active_session(self.db, uid)
            if session is None:
                status, sid, remaining = "idle", None, None
            else:
                status = "focusing" if session.status == SessionStatus.ACTIVE else "paused"
                sid, remaining = session.id, remaining_seconds(session)
            members.append(RoomMember(
                user_id=uid, username=user.username, display_name=user.display_name,
                level=gamification.level_for_xp(user.xp), is_owner=uid == room.owner_id,
                focus_status=status, session_id=sid, remaining_seconds=remaining,
            ))
        focusing = sum(m.focus_status == "focusing" for m in members)
        paused = sum(m.focus_status == "paused" for m in members)
        return RoomActivity(
            room_id=room.id, member_count=len(members), focusing=focusing, paused=paused,
            idle=len(members) - focusing - paused,
            room_phase=self._phase(focusing, len(members)), members=members,
        )

    def leaderboard(self, room_id: int, metric: LeaderboardMetric, limit: int) -> Leaderboard:
        room = get_room(self.db, room_id)
        users = [self.db.users[uid] for uid in room.member_ids]
        return Leaderboard(metric=metric, scope=f"room:{room.id}",
                           entries=gamification.build_leaderboard(users, metric, limit))

    def recommend_tracks(self, room_id: int, limit: int) -> TrackRecommendation:
        """Adaptive audio: choose tracks according to what the room is doing right now."""
        room = get_room(self.db, room_id)
        act = self.activity(room_id)
        if act.room_phase == "focus":
            moods, target_mood, max_energy, target_energy = {Mood.FOCUS, Mood.CALM}, Mood.FOCUS, 5, 3
            reason = (f"{act.focusing}/{act.member_count} members are focusing — "
                      "calm, low-energy tracks keep the flow")
        else:
            moods, target_mood, max_energy, target_energy = {Mood.BREAK, Mood.ENERGIZE}, Mood.BREAK, 10, 6
            reason = "Most members are on a break — lighter, more energetic tracks to recharge"

        candidates = [t for t in self.db.tracks.values()
                      if t.mood in moods and t.energy <= max_energy
                      and t.id != room.current_track_id]
        candidates.sort(key=lambda t: (
            t.genre != room.preferred_genre,       # preferred genre first
            t.mood != target_mood,                 # exact mood first
            abs(t.energy - target_energy),
            t.id,
        ))
        return TrackRecommendation(
            room_id=room.id, room_phase=act.room_phase, target_mood=target_mood,
            max_energy=max_energy, reason=reason,
            tracks=[TrackResponse.model_validate(t) for t in candidates[:limit]],
        )

    # --------------------------------------------------------------- commands
    def create(self, data: RoomCreate) -> RoomResponse:
        owner = get_user(self.db, data.owner_id)
        self._ensure_name_free(data.name)
        if owner.current_room_id is not None:
            raise ConflictError(
                "Owner is already a member of another room; leave it first",
                code="USER_ALREADY_IN_ROOM",
                details={"current_room_id": owner.current_room_id},
            )
        rid = self.db.next_id("rooms")
        room = Room(
            id=rid, name=data.name, description=data.description, owner_id=owner.id,
            capacity=data.capacity, is_private=data.is_private, access_code=data.access_code,
            preferred_genre=data.preferred_genre, tags=data.tags, member_ids=[owner.id],
        )
        self.db.rooms[rid] = room
        owner.current_room_id = rid
        return self.to_response(room)

    def update(self, room_id: int, acting_user_id: int, data: RoomUpdate) -> RoomResponse:
        room = self._owned(room_id, acting_user_id)
        fields = data.model_fields_set

        if "name" in fields and data.name.lower() != room.name.lower():
            self._ensure_name_free(data.name)
        if "capacity" in fields and data.capacity < len(room.member_ids):
            raise ConflictError(
                "Capacity cannot be lower than the current number of members",
                code="CAPACITY_BELOW_MEMBERS",
                details={"member_count": len(room.member_ids), "requested": data.capacity},
            )

        new_private = data.is_private if "is_private" in fields else room.is_private
        new_code = data.access_code if "access_code" in fields else room.access_code
        if new_private and not new_code:
            raise BusinessRuleError("Private rooms require an access_code",
                                    code="ACCESS_CODE_REQUIRED")
        if not new_private:
            if "access_code" in fields and data.access_code:
                raise BusinessRuleError("Public rooms must not have an access_code",
                                        code="ACCESS_CODE_NOT_ALLOWED")
            new_code = None

        for name in fields - {"is_private", "access_code"}:
            setattr(room, name, getattr(data, name))
        room.is_private, room.access_code = new_private, new_code
        return self.to_response(room)

    def delete(self, room_id: int, acting_user_id: int) -> None:
        room = self._owned(room_id, acting_user_id)
        self.close_room(room)

    def join(self, room_id: int, data: JoinRoomRequest) -> RoomResponse:
        room = get_room(self.db, room_id)
        user = get_user(self.db, data.user_id)
        if user.id in room.member_ids:
            raise ConflictError("User is already a member of this room", code="ALREADY_MEMBER")
        if user.current_room_id is not None:
            raise ConflictError(
                "User is already in another room; leave it before joining a new one",
                code="USER_ALREADY_IN_ROOM",
                details={"current_room_id": user.current_room_id},
            )
        if len(room.member_ids) >= room.capacity:
            raise ConflictError(f"Room '{room.name}' is full ({room.capacity}/{room.capacity})",
                                code="ROOM_FULL", details={"capacity": room.capacity})
        if room.is_private and data.access_code != room.access_code:
            raise ForbiddenError("Invalid access code for private room",
                                 code="INVALID_ACCESS_CODE")
        room.member_ids.append(user.id)
        user.current_room_id = room.id
        # a running session now counts as "in this room"
        session = find_active_session(self.db, user.id)
        if session:
            session.room_id = room.id
        return self.to_response(room)

    def remove_member(self, room_id: int, user_id: int, acting_user_id: int) -> dict:
        """Leave (acting user == member) or kick (acting user == owner)."""
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id)
        if user_id not in room.member_ids:
            raise NotFoundError("Member", user_id)
        if acting_user_id != user_id and acting_user_id != room.owner_id:
            raise ForbiddenError("Only the room owner can remove other members",
                                 code="NOT_ROOM_OWNER")
        return self.detach_member(room, user_id, kicked=acting_user_id != user_id)

    def set_track(self, room_id: int, acting_user_id: int, track_id: int) -> RoomResponse:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id)
        if acting_user_id not in room.member_ids:
            raise ForbiddenError("Only room members can change the music", code="NOT_A_MEMBER")
        track = get_track(self.db, track_id)
        if room.current_track_id == track.id:
            raise ConflictError("This track is already playing", code="TRACK_ALREADY_PLAYING")
        room.current_track_id = track.id
        return self.to_response(room)

    def stop_track(self, room_id: int, acting_user_id: int) -> RoomResponse:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id)
        if acting_user_id not in room.member_ids:
            raise ForbiddenError("Only room members can change the music", code="NOT_A_MEMBER")
        if room.current_track_id is None:
            raise ConflictError("Nothing is playing in this room", code="NO_TRACK_PLAYING")
        room.current_track_id = None
        return self.to_response(room)

    # ---------------------------------------------------------------- helpers
    def detach_member(self, room: Room, user_id: int, kicked: bool = False) -> dict:
        room.member_ids.remove(user_id)
        self.db.users[user_id].current_room_id = None
        result = {"room_id": room.id, "user_id": user_id, "kicked": kicked,
                  "new_owner_id": None, "room_deleted": False}

        if not room.member_ids:
            self.close_room(room)
            result["room_deleted"] = True
        elif room.owner_id == user_id:
            room.owner_id = room.member_ids[0]       # longest-standing member
            result["new_owner_id"] = room.owner_id
        return result

    def close_room(self, room: Room) -> None:
        for uid in room.member_ids:
            self.db.users[uid].current_room_id = None
        for session in self.db.sessions.values():
            if session.room_id == room.id:
                session.room_id = None
        del self.db.rooms[room.id]

    def _owned(self, room_id: int, acting_user_id: int) -> Room:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id)
        if room.owner_id != acting_user_id:
            raise ForbiddenError("Only the room owner can perform this action",
                                 code="NOT_ROOM_OWNER", details={"owner_id": room.owner_id})
        return room

    def _ensure_name_free(self, name: str) -> None:
        if any(r.name.lower() == name.lower() for r in self.db.rooms.values()):
            raise ConflictError(f"Room name '{name}' is already taken", code="ROOM_NAME_TAKEN")

    @staticmethod
    def _phase(focusing: int, members: int) -> str:
        return "focus" if focusing > 0 and focusing * 2 >= members else "break"
