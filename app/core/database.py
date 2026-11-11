"""In-memory data store.

All application data lives in dictionaries on a single `Database` instance.
Services receive the database through FastAPI dependency injection
(`get_db`) so tests can reset it easily.
"""
from __future__ import annotations

from itertools import count
from typing import Iterator

from app.models.entities import FocusSession, Room, Task, Track, User
from app.models.enums import Genre, Mood


class Database:
    def __init__(self) -> None:
        self.users: dict[int, User] = {}
        self.rooms: dict[int, Room] = {}
        self.tracks: dict[int, Track] = {}
        self.tasks: dict[int, Task] = {}
        self.sessions: dict[int, FocusSession] = {}
        self._counters: dict[str, Iterator[int]] = {
            name: count(1) for name in ("users", "rooms", "tracks", "tasks", "sessions")
        }

    def next_id(self, collection: str) -> int:
        return next(self._counters[collection])

    def reset(self) -> None:
        self.__init__()


db = Database()


def get_db() -> Database:
    return db


# --------------------------------------------------------------------------- #
# Demo data
# --------------------------------------------------------------------------- #
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


def seed_demo_data(database: Database) -> None:
    for title, artist, genre, mood, energy, duration, bpm in _DEMO_TRACKS:
        tid = database.next_id("tracks")
        database.tracks[tid] = Track(
            id=tid, title=title, artist=artist, genre=genre, mood=mood,
            energy=energy, duration_seconds=duration, bpm=bpm,
        )

    for username, name, email in [
        ("alice", "Alice", "alice@focusradio.dev"),
        ("bob", "Bob", "bob@focusradio.dev"),
        ("carol", "Carol", "carol@focusradio.dev"),
    ]:
        uid = database.next_id("users")
        database.users[uid] = User(id=uid, username=username, display_name=name, email=email)

    rid = database.next_id("rooms")
    database.rooms[rid] = Room(
        id=rid,
        name="Morning LoFi Library",
        description="Quiet public room for students. Cameras off, focus on.",
        owner_id=1,
        capacity=10,
        preferred_genre=Genre.LOFI,
        tags=["study", "lofi"],
        member_ids=[1],
        current_track_id=1,
    )
    database.users[1].current_room_id = rid
