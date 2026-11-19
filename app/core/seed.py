from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Room, RoomMember, Track, User
from app.models.enums import Genre, Mood

_DEMO_TRACKS = [
    ("Rainy Library", "LoFi Owl", Genre.LOFI, Mood.FOCUS, 3, 184, 72),
    ("Midnight Notes", "Chillhop Cat", Genre.LOFI, Mood.FOCUS, 4, 201, 80),
    ("Coffee Break Groove", "Bean Beats", Genre.LOFI, Mood.BREAK, 6, 176, 92),
    ("Deep Space Drift", "Nebula", Genre.AMBIENT, Mood.FOCUS, 2, 420, None),
    ("Forest Morning", "Nature Sounds", Genre.NATURE, Mood.CALM, 1, 600, None),
    ("Ocean Waves", "Nature Sounds", Genre.NATURE, Mood.BREAK, 1, 540, None),
    ("Brown Noise 30", "Noise Lab", Genre.WHITE_NOISE, Mood.FOCUS, 1, 1800, None),
    ("Gymnopédie No.1", "Erik Satie", Genre.CLASSICAL, Mood.CALM, 2, 205, 66),
    ("Neon Sprint", "Retro Drive", Genre.SYNTHWAVE, Mood.ENERGIZE, 8, 230, 118),
    ("Code Runner", "Retro Drive", Genre.SYNTHWAVE, Mood.FOCUS, 6, 245, 110),
]

_DEMO_USERS = [
    ("alice", "Alice", "alice@focusradio.dev"),
    ("bob", "Bob", "bob@focusradio.dev"),
    ("carol", "Carol", "carol@focusradio.dev"),
]


def seed_demo_data(db: Session) -> None:
    has_tracks = (db.scalar(select(func.count(Track.id))) or 0) > 0
    has_users = (db.scalar(select(func.count(User.id))) or 0) > 0
    has_rooms = (db.scalar(select(func.count(Room.id))) or 0) > 0

    if has_tracks and has_users and has_rooms:
        return

    first_track: Track | None = None
    if not has_tracks:
        tracks = [
            Track(
                title=title,
                artist=artist,
                genre=genre,
                mood=mood,
                energy=energy,
                duration_seconds=duration,
                bpm=bpm,
            )
            for title, artist, genre, mood, energy, duration, bpm in _DEMO_TRACKS
        ]
        db.add_all(tracks)
        db.flush()
        first_track = tracks[0]
    else:
        first_track = db.scalar(select(Track).order_by(Track.id.asc()).limit(1))

    alice: User | None = None
    if not has_users:
        users = [
            User(username=username, display_name=name, email=email)
            for username, name, email in _DEMO_USERS
        ]
        db.add_all(users)
        db.flush()
        alice = users[0]
    else:
        alice = db.scalar(select(User).where(User.username == "alice"))

    if not has_rooms and alice is not None and alice.current_room_id is None:
        room = Room(
            name="Morning LoFi Library",
            description="Quiet public room for students. Cameras off, focus on.",
            owner_id=alice.id,
            capacity=10,
            preferred_genre=Genre.LOFI,
            tags=["study", "lofi"],
            current_track_id=first_track.id if first_track else None,
        )
        db.add(room)
        db.flush()
        db.add(RoomMember(room_id=room.id, user_id=alice.id))

    db.commit()