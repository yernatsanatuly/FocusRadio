"""Coworking room workflow: create/join/leave rooms, ownership transfer,
live activity and adaptive soundtrack backed by PostgreSQL."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.exceptions import BusinessRuleError, ConflictError, ForbiddenError, NotFoundError
from app.models import FocusSession, Room, RoomMember, Track
from app.models.enums import ACTIVE_SESSION_STATUSES, Genre, LeaderboardMetric, Mood, SessionStatus
from app.schemas.leaderboard import Leaderboard
from app.schemas.rooms import (
    JoinRoomRequest,
    RoomActivity,
    RoomCreate,
    RoomMember as RoomMemberSchema,
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
    paginate_query,
)
from app.services.session_service import remaining_seconds


class RoomService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------------- presenters
    def to_response(self, room: Room) -> RoomResponse:
        member_count = len(room.members)
        return RoomResponse(
            id=room.id,
            name=room.name,
            description=room.description,
            owner_id=room.owner_id,
            capacity=room.capacity,
            member_count=member_count,
            available_spots=room.capacity - member_count,
            is_private=room.is_private,
            preferred_genre=room.preferred_genre,
            tags=list(room.tags),
            current_track=(
                TrackResponse.model_validate(room.current_track) if room.current_track else None
            ),
            created_at=room.created_at,
        )

    # ---------------------------------------------------------------- queries
    def list(
        self,
        *,
        search: Optional[str],
        tag: Optional[str],
        genre: Optional[Genre],
        is_private: Optional[bool],
        has_space: Optional[bool],
        limit: int,
        offset: int,
    ) -> dict:
        member_counts = (
            select(RoomMember.room_id, func.count(RoomMember.id).label("member_count"))
            .group_by(RoomMember.room_id)
            .subquery()
        )
        mc = func.coalesce(member_counts.c.member_count, 0)

        stmt = select(Room).outerjoin(member_counts, Room.id == member_counts.c.room_id)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Room.name.ilike(pattern),
                    func.coalesce(Room.description, "").ilike(pattern),
                )
            )
        if tag:
            stmt = stmt.where(Room.tags.contains([tag.lower()]))
        if genre is not None:
            stmt = stmt.where(Room.preferred_genre == genre)
        if is_private is not None:
            stmt = stmt.where(Room.is_private == is_private)
        if has_space is True:
            stmt = stmt.where(mc < Room.capacity)
        elif has_space is False:
            stmt = stmt.where(mc >= Room.capacity)

        stmt = stmt.order_by(mc.desc(), Room.id.asc())

        items, total = paginate_query(
            self.db,
            stmt,
            limit,
            offset,
            options=(joinedload(Room.current_track), selectinload(Room.members)),
        )
        return {
            "items": [self.to_response(r) for r in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get(self, room_id: int) -> RoomResponse:
        return self.to_response(get_room(self.db, room_id, load_relations=True))

    def activity(self, room_id: int) -> RoomActivity:
        room = get_room(self.db, room_id, load_relations=True)
        member_user_ids = [m.user_id for m in room.members]
        active_by_user: dict[int, FocusSession] = {}
        if member_user_ids:
            active_sessions = self.db.scalars(
                select(FocusSession).where(
                    FocusSession.user_id.in_(member_user_ids),
                    FocusSession.status.in_(ACTIVE_SESSION_STATUSES),
                )
            ).all()
            active_by_user = {s.user_id: s for s in active_sessions}

        members: list[RoomMemberSchema] = []
        for membership in room.members:
            user = membership.user
            session = active_by_user.get(user.id)
            if session is None:
                status, sid, remaining = "idle", None, None
            else:
                status = "focusing" if session.status == SessionStatus.ACTIVE else "paused"
                sid, remaining = session.id, remaining_seconds(session)
            members.append(
                RoomMemberSchema(
                    user_id=user.id,
                    username=user.username,
                    display_name=user.display_name,
                    level=gamification.level_for_xp(user.xp),
                    is_owner=user.id == room.owner_id,
                    focus_status=status,
                    session_id=sid,
                    remaining_seconds=remaining,
                )
            )
        focusing = sum(m.focus_status == "focusing" for m in members)
        paused = sum(m.focus_status == "paused" for m in members)
        return RoomActivity(
            room_id=room.id,
            member_count=len(members),
            focusing=focusing,
            paused=paused,
            idle=len(members) - focusing - paused,
            room_phase=self._phase(focusing, len(members)),
            members=members,
        )

    def leaderboard(self, room_id: int, metric: LeaderboardMetric, limit: int) -> Leaderboard:
        room = get_room(self.db, room_id, load_relations=True)
        users = [m.user for m in room.members]
        return Leaderboard(
            metric=metric,
            scope=f"room:{room.id}",
            entries=gamification.build_leaderboard(users, metric, limit),
        )

    def recommend_tracks(self, room_id: int, limit: int) -> TrackRecommendation:
        """Adaptive audio: choose tracks according to what the room is doing right now."""
        room = get_room(self.db, room_id, load_relations=True)
        act = self.activity(room_id)
        if act.room_phase == "focus":
            moods, target_mood, max_energy, target_energy = (
                {Mood.FOCUS, Mood.CALM},
                Mood.FOCUS,
                5,
                3,
            )
            reason = (
                f"{act.focusing}/{act.member_count} members are focusing — "
                "calm, low-energy tracks keep the flow"
            )
        else:
            moods, target_mood, max_energy, target_energy = (
                {Mood.BREAK, Mood.ENERGIZE},
                Mood.BREAK,
                10,
                6,
            )
            reason = "Most members are on a break — lighter, more energetic tracks to recharge"

        stmt = select(Track).where(Track.mood.in_(moods), Track.energy <= max_energy)
        if room.current_track_id is not None:
            stmt = stmt.where(Track.id != room.current_track_id)
        candidates = list(self.db.scalars(stmt).all())
        candidates.sort(
            key=lambda t: (
                t.genre != room.preferred_genre,
                t.mood != target_mood,
                abs(t.energy - target_energy),
                t.id,
            )
        )
        return TrackRecommendation(
            room_id=room.id,
            room_phase=act.room_phase,
            target_mood=target_mood,
            max_energy=max_energy,
            reason=reason,
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

        room = Room(
            name=data.name,
            description=data.description,
            owner_id=owner.id,
            capacity=data.capacity,
            is_private=data.is_private,
            access_code=data.access_code,
            preferred_genre=data.preferred_genre,
            tags=list(data.tags),
        )
        self.db.add(room)
        self.db.flush()
        self.db.add(RoomMember(room_id=room.id, user_id=owner.id))
        self.db.commit()
        return self.to_response(get_room(self.db, room.id, load_relations=True))

    def update(self, room_id: int, acting_user_id: int, data: RoomUpdate) -> RoomResponse:
        room = self._owned(room_id, acting_user_id)
        fields = data.model_fields_set

        if "name" in fields and data.name.lower() != room.name.lower():
            self._ensure_name_free(data.name, exclude_id=room.id)
        if "capacity" in fields and data.capacity < len(room.members):
            raise ConflictError(
                "Capacity cannot be lower than the current number of members",
                code="CAPACITY_BELOW_MEMBERS",
                details={"member_count": len(room.members), "requested": data.capacity},
            )

        new_private = data.is_private if "is_private" in fields else room.is_private
        new_code = data.access_code if "access_code" in fields else room.access_code
        if new_private and not new_code:
            raise BusinessRuleError(
                "Private rooms require an access_code", code="ACCESS_CODE_REQUIRED"
            )
        if not new_private:
            if "access_code" in fields and data.access_code:
                raise BusinessRuleError(
                    "Public rooms must not have an access_code", code="ACCESS_CODE_NOT_ALLOWED"
                )
            new_code = None

        for name in fields - {"is_private", "access_code"}:
            value = getattr(data, name)
            setattr(room, name, list(value) if name == "tags" and value is not None else value)
        room.is_private, room.access_code = new_private, new_code
        self.db.commit()
        return self.to_response(get_room(self.db, room.id, load_relations=True))

    def delete(self, room_id: int, acting_user_id: int) -> None:
        room = self._owned(room_id, acting_user_id)
        self.close_room(room)
        self.db.commit()

    def join(self, room_id: int, data: JoinRoomRequest) -> RoomResponse:
        room = get_room(self.db, room_id, load_relations=True)
        user = get_user(self.db, data.user_id)
        member_ids = {m.user_id for m in room.members}
        if user.id in member_ids:
            raise ConflictError("User is already a member of this room", code="ALREADY_MEMBER")
        if user.current_room_id is not None:
            raise ConflictError(
                "User is already in another room; leave it before joining a new one",
                code="USER_ALREADY_IN_ROOM",
                details={"current_room_id": user.current_room_id},
            )
        if len(room.members) >= room.capacity:
            raise ConflictError(
                f"Room '{room.name}' is full ({room.capacity}/{room.capacity})",
                code="ROOM_FULL",
                details={"capacity": room.capacity},
            )
        if room.is_private and data.access_code != room.access_code:
            raise ForbiddenError(
                "Invalid access code for private room", code="INVALID_ACCESS_CODE"
            )

        self.db.add(RoomMember(room_id=room.id, user_id=user.id))
        session = find_active_session(self.db, user.id)
        if session:
            session.room_id = room.id
        self.db.commit()
        return self.to_response(get_room(self.db, room.id, load_relations=True))

    def remove_member(self, room_id: int, user_id: int, acting_user_id: int) -> dict:
        """Leave (acting user == member) or kick (acting user == owner)."""
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id, load_relations=True)
        if not any(m.user_id == user_id for m in room.members):
            raise NotFoundError("Member", user_id)
        if acting_user_id != user_id and acting_user_id != room.owner_id:
            raise ForbiddenError(
                "Only the room owner can remove other members", code="NOT_ROOM_OWNER"
            )
        result = self.detach_member(room, user_id, kicked=acting_user_id != user_id)
        self.db.commit()
        return result

    def set_track(self, room_id: int, acting_user_id: int, track_id: int) -> RoomResponse:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id, load_relations=True)
        if not any(m.user_id == acting_user_id for m in room.members):
            raise ForbiddenError("Only room members can change the music", code="NOT_A_MEMBER")
        track = get_track(self.db, track_id)
        if room.current_track_id == track.id:
            raise ConflictError("This track is already playing", code="TRACK_ALREADY_PLAYING")
        room.current_track_id = track.id
        self.db.commit()
        return self.to_response(get_room(self.db, room.id, load_relations=True))

    def stop_track(self, room_id: int, acting_user_id: int) -> RoomResponse:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id, load_relations=True)
        if not any(m.user_id == acting_user_id for m in room.members):
            raise ForbiddenError("Only room members can change the music", code="NOT_A_MEMBER")
        if room.current_track_id is None:
            raise ConflictError("Nothing is playing in this room", code="NO_TRACK_PLAYING")
        room.current_track_id = None
        self.db.commit()
        return self.to_response(get_room(self.db, room.id, load_relations=True))

    # ---------------------------------------------------------------- helpers
    def detach_member(self, room: Room, user_id: int, kicked: bool = False) -> dict:
        membership = self.db.scalar(
            select(RoomMember).where(
                RoomMember.room_id == room.id, RoomMember.user_id == user_id
            )
        )
        if membership is not None:
            self.db.delete(membership)
            self.db.flush()
            self.db.expire(room, ["members"])

        remaining = list(
            self.db.scalars(
                select(RoomMember)
                .where(RoomMember.room_id == room.id)
                .order_by(RoomMember.joined_at.asc(), RoomMember.id.asc())
            )
        )
        result = {
            "room_id": room.id,
            "user_id": user_id,
            "kicked": kicked,
            "new_owner_id": None,
            "room_deleted": False,
        }

        if not remaining:
            self.close_room(room)
            result["room_deleted"] = True
        elif room.owner_id == user_id:
            room.owner_id = remaining[0].user_id
            self.db.flush()
            result["new_owner_id"] = room.owner_id
        return result

    def close_room(self, room: Room) -> None:
        self.db.execute(
            update(FocusSession).where(FocusSession.room_id == room.id).values(room_id=None)
        )
        self.db.delete(room)
        self.db.flush()

    def _owned(self, room_id: int, acting_user_id: int) -> Room:
        ensure_actor_exists(self.db, acting_user_id)
        room = get_room(self.db, room_id, load_relations=True)
        if room.owner_id != acting_user_id:
            raise ForbiddenError(
                "Only the room owner can perform this action",
                code="NOT_ROOM_OWNER",
                details={"owner_id": room.owner_id},
            )
        return room

    def _ensure_name_free(self, name: str, *, exclude_id: Optional[int] = None) -> None:
        stmt = select(Room.id).where(func.lower(Room.name) == name.lower())
        if exclude_id is not None:
            stmt = stmt.where(Room.id != exclude_id)
        if self.db.scalar(stmt) is not None:
            raise ConflictError(f"Room name '{name}' is already taken", code="ROOM_NAME_TAKEN")

    @staticmethod
    def _phase(focusing: int, members: int) -> str:
        return "focus" if focusing > 0 and focusing * 2 >= members else "break"
