import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.database import get_db
from app.core.seed import seed_demo_data
from app.main import app
from app.models import FocusSession, Room, RoomMember, Task, Track, User, UserAchievement

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_migrations(database_url: str) -> None:
    alembic_cfg = AlembicConfig(os.path.join(ROOT_DIR, "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


class TestFocusRadioAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_url = settings.test_database_url
        _run_migrations(cls.test_db_url)

        cls.engine = create_engine(cls.test_db_url, pool_pre_ping=True)
        cls.SessionLocal = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        cls._orig_seconds_per_minute = settings.seconds_per_minute
        cls._orig_seed_demo_data = settings.seed_demo_data
        settings.seconds_per_minute = 0.05
        settings.seed_demo_data = False

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        settings.seconds_per_minute = cls._orig_seconds_per_minute
        settings.seed_demo_data = cls._orig_seed_demo_data
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as db:
            db.execute(
                text(
                    "TRUNCATE TABLE "
                    "user_achievements, focus_sessions, room_members, rooms, tasks, tracks, users "
                    "RESTART IDENTITY CASCADE"
                )
            )
            db.commit()
            seed_demo_data(db)

    def test_root_and_docs(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "online")

        docs = self.client.get("/docs")
        self.assertEqual(docs.status_code, 200)

        openapi = self.client.get("/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        self.assertIn("FocusRadio API", openapi.json()["info"]["title"])

    def test_user_crud_and_validation(self):
        payload = {
            "username": "diana_dev",
            "display_name": "Diana",
            "email": "diana@test.com",
            "bio": "Pythonista",
        }
        res = self.client.post("/users", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["username"], "diana_dev")
        self.assertEqual(data["level"], 1)
        user_id = data["id"]

        dup_res = self.client.post("/users", json=payload)
        self.assertEqual(dup_res.status_code, 409)
        self.assertEqual(dup_res.json()["error"]["code"], "USERNAME_TAKEN")

        dup_email = self.client.post(
            "/users",
            json={"username": "diana_2", "display_name": "Diana 2", "email": "DIANA@test.com"},
        )
        self.assertEqual(dup_email.status_code, 409)
        self.assertEqual(dup_email.json()["error"]["code"], "EMAIL_TAKEN")

        bad_res = self.client.post(
            "/users",
            json={
                "username": "bad_user",
                "display_name": "Bad",
                "email": "not-an-email",
            },
        )
        self.assertEqual(bad_res.status_code, 422)
        self.assertEqual(bad_res.json()["error"]["code"], "VALIDATION_ERROR")

        update_res = self.client.patch(
            f"/users/{user_id}",
            headers={"X-User-Id": str(user_id)},
            json={"display_name": "Diana K.", "bio": "Focusing every day"},
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["display_name"], "Diana K.")

        forbidden = self.client.patch(
            f"/users/{user_id}",
            headers={"X-User-Id": "1"},
            json={"display_name": "Hacked"},
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["error"]["code"], "NOT_RESOURCE_OWNER")

        not_found = self.client.get("/users/9999")
        self.assertEqual(not_found.status_code, 404)

        listed = self.client.get("/users?search=diana&sort_by=username")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(listed.json()["items"][0]["id"], user_id)

        stats_res = self.client.get(f"/users/{user_id}/stats")
        self.assertEqual(stats_res.status_code, 200)
        self.assertEqual(stats_res.json()["total_focus_minutes"], 0)

    def test_room_lifecycle_and_adaptive_audio(self):
        room_payload = {
            "name": "Midnight Hackers",
            "description": "Deep synthwave coding",
            "owner_id": 2,
            "capacity": 3,
            "is_private": True,
            "access_code": "code2026",
            "preferred_genre": "synthwave",
            "tags": ["coding", "synthwave"],
        }
        res = self.client.post("/rooms", json=room_payload)
        self.assertEqual(res.status_code, 201)
        room = res.json()
        room_id = room["id"]
        self.assertEqual(room["member_count"], 1)
        self.assertEqual(room["available_spots"], 2)

        # Filter rooms by tag, genre, privacy and availability
        filtered = self.client.get("/rooms?tag=coding&genre=synthwave&is_private=true&has_space=true")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["id"], room_id)

        bad_join = self.client.post(
            f"/rooms/{room_id}/members", json={"user_id": 3, "access_code": "wrong"}
        )
        self.assertEqual(bad_join.status_code, 403)
        self.assertEqual(bad_join.json()["error"]["code"], "INVALID_ACCESS_CODE")

        join_res = self.client.post(
            f"/rooms/{room_id}/members", json={"user_id": 3, "access_code": "code2026"}
        )
        self.assertEqual(join_res.status_code, 201)
        self.assertEqual(join_res.json()["member_count"], 2)

        track_res = self.client.put(
            f"/rooms/{room_id}/track",
            headers={"X-User-Id": "3"},
            json={"track_id": 9},
        )
        self.assertEqual(track_res.status_code, 200)
        self.assertEqual(track_res.json()["current_track"]["title"], "Neon Sprint")

        alice_track = self.client.put(
            f"/rooms/{room_id}/track",
            headers={"X-User-Id": "1"},
            json={"track_id": 2},
        )
        self.assertEqual(alice_track.status_code, 403)

        recom = self.client.get(f"/rooms/{room_id}/recommended-tracks")
        self.assertEqual(recom.status_code, 200)
        self.assertEqual(recom.json()["room_phase"], "break")
        self.assertTrue(len(recom.json()["tracks"]) > 0)

        # Start focus session for Bob -> 1/2 focusing -> room switches to focus phase
        sess_res = self.client.post("/sessions", json={"user_id": 2, "mode": "pomodoro"})
        self.assertEqual(sess_res.status_code, 201)
        recom_focus = self.client.get(f"/rooms/{room_id}/recommended-tracks")
        self.assertEqual(recom_focus.status_code, 200)
        self.assertEqual(recom_focus.json()["room_phase"], "focus")
        self.client.post(f"/sessions/{sess_res.json()['id']}/cancel", headers={"X-User-Id": "2"})

        leave_res = self.client.delete(f"/rooms/{room_id}/members/2", headers={"X-User-Id": "2"})
        self.assertEqual(leave_res.status_code, 200)
        self.assertEqual(leave_res.json()["new_owner_id"], 3)

        leave_last = self.client.delete(f"/rooms/{room_id}/members/3", headers={"X-User-Id": "3"})
        self.assertEqual(leave_last.status_code, 200)
        self.assertTrue(leave_last.json()["room_deleted"])

        get_res = self.client.get(f"/rooms/{room_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_focus_session_and_task_integration(self):
        task_res = self.client.post(
            "/tasks",
            json={
                "user_id": 1,
                "title": "Build FastAPI Architecture",
                "description": "Entities, services, routers",
                "priority": "high",
                "estimated_pomodoros": 2,
            },
        )
        self.assertEqual(task_res.status_code, 201)
        task_id = task_res.json()["id"]

        session_res = self.client.post(
            "/sessions",
            json={
                "user_id": 1,
                "mode": "custom",
                "focus_minutes": 1,
                "break_minutes": 1,
                "task_id": task_id,
                "notes": "Coding services",
            },
        )
        self.assertEqual(session_res.status_code, 201)
        session = session_res.json()
        session_id = session["id"]
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["task_id"], task_id)
        self.assertEqual(session["room_id"], 1)  # Alice is in seeded room 1

        # Task auto-transitioned from todo -> in_progress
        task_after_start = self.client.get(f"/tasks/{task_id}").json()
        self.assertEqual(task_after_start["status"], "in_progress")

        conflict_res = self.client.post("/sessions", json={"user_id": 1, "mode": "pomodoro"})
        self.assertEqual(conflict_res.status_code, 409)
        self.assertEqual(conflict_res.json()["error"]["code"], "SESSION_ALREADY_RUNNING")

        pause_res = self.client.post(f"/sessions/{session_id}/pause", headers={"X-User-Id": "1"})
        self.assertEqual(pause_res.status_code, 200)
        self.assertEqual(pause_res.json()["status"], "paused")
        self.assertEqual(pause_res.json()["pause_count"], 1)

        resume_res = self.client.post(f"/sessions/{session_id}/resume", headers={"X-User-Id": "1"})
        self.assertEqual(resume_res.status_code, 200)
        self.assertEqual(resume_res.json()["status"], "active")

        finish_res = self.client.post(
            f"/sessions/{session_id}/complete?force=true",
            headers={"X-User-Id": "1"},
        )
        self.assertEqual(finish_res.status_code, 200)
        finish_data = finish_res.json()
        self.assertEqual(finish_data["session"]["status"], "ended_early")
        self.assertGreaterEqual(finish_data["total_xp"], 0)

        dup_complete = self.client.post(
            f"/sessions/{session_id}/complete",
            headers={"X-User-Id": "1"},
        )
        self.assertEqual(dup_complete.status_code, 409)

        task_done = self.client.patch(
            f"/tasks/{task_id}",
            headers={"X-User-Id": "1"},
            json={"status": "done"},
        )
        self.assertEqual(task_done.status_code, 200)
        self.assertEqual(task_done.json()["task"]["status"], "done")
        self.assertEqual(task_done.json()["task"]["progress_percent"], 100.0)

    def test_full_completion_xp_streak_and_leaderboard(self):
        task_res = self.client.post(
            "/tasks",
            json={"user_id": 2, "title": "PostgreSQL Migration", "estimated_pomodoros": 2},
        )
        task_id = task_res.json()["id"]

        res = self.client.post(
            "/sessions",
            json={
                "user_id": 2,
                "mode": "custom",
                "focus_minutes": 1,
                "break_minutes": 1,
                "task_id": task_id,
            },
        )
        self.assertEqual(res.status_code, 201)
        session_id = res.json()["id"]

        time.sleep(0.08)

        finish_res = self.client.post(
            f"/sessions/{session_id}/complete",
            headers={"X-User-Id": "2"},
        )
        self.assertEqual(finish_res.status_code, 200)
        data = finish_res.json()
        self.assertEqual(data["session"]["status"], "completed")
        self.assertEqual(data["current_streak"], 1)
        self.assertIn("completion_bonus", data["xp_breakdown"])
        self.assertIn("no_pause_bonus", data["xp_breakdown"])

        # Linked task received +1 completed pomodoro
        task_state = self.client.get(f"/tasks/{task_id}").json()
        self.assertEqual(task_state["completed_pomodoros"], 1)
        self.assertEqual(task_state["progress_percent"], 50.0)

        ach_res = self.client.get("/users/2/achievements?unlocked_only=true")
        self.assertEqual(ach_res.status_code, 200)
        codes = [a["code"] for a in ach_res.json()]
        self.assertIn("first_tune_in", codes)

        lb = self.client.get("/leaderboard?metric=xp")
        self.assertEqual(lb.status_code, 200)
        entries = lb.json()["entries"]
        self.assertTrue(len(entries) >= 2)
        self.assertEqual(entries[0]["user_id"], 2)

    def test_persistence_across_database_sessions(self):
        user_res = self.client.post(
            "/users",
            json={
                "username": "persistent_user",
                "display_name": "Persistent",
                "email": "persist@focusradio.dev",
            },
        )
        self.assertEqual(user_res.status_code, 201)
        uid = user_res.json()["id"]

        room_res = self.client.post(
            "/rooms",
            json={"name": "Persistent Room", "owner_id": uid, "capacity": 4, "tags": ["db"]},
        )
        self.assertEqual(room_res.status_code, 201)
        rid = room_res.json()["id"]

        task_res = self.client.post(
            "/tasks",
            json={"user_id": uid, "title": "Verify Postgres", "estimated_pomodoros": 1},
        )
        self.assertEqual(task_res.status_code, 201)
        tid = task_res.json()["id"]

        # Inspect directly via a brand-new SQLAlchemy Session against PostgreSQL
        with self.SessionLocal() as fresh_db:
            user = fresh_db.get(User, uid)
            self.assertIsNotNone(user)
            self.assertEqual(user.current_room_id, rid)

            room = fresh_db.get(Room, rid)
            self.assertIsNotNone(room)
            self.assertEqual(room.owner_id, uid)
            self.assertEqual(room.tags, ["db"])

            member = fresh_db.scalar(
                select(RoomMember).where(RoomMember.room_id == rid, RoomMember.user_id == uid)
            )
            self.assertIsNotNone(member)

            task = fresh_db.get(Task, tid)
            self.assertIsNotNone(task)
            self.assertEqual(task.user_id, uid)

    def test_relationships_and_cascade_integrity(self):
        # 1. Track deletion protection & force=true sets room.current_track_id = NULL
        conflict_track = self.client.delete("/tracks/1")
        self.assertEqual(conflict_track.status_code, 409)
        self.assertEqual(conflict_track.json()["error"]["code"], "TRACK_IN_USE")

        force_track = self.client.delete("/tracks/1?force=true")
        self.assertEqual(force_track.status_code, 204)
        room1 = self.client.get("/rooms/1").json()
        self.assertIsNone(room1["current_track"])

        # 2. Task deletion blocked while in active session, then SET NULL after cancel
        task_id = self.client.post(
            "/tasks", json={"user_id": 1, "title": "Active Linked Task"}
        ).json()["id"]
        sess_id = self.client.post(
            "/sessions",
            json={"user_id": 1, "mode": "pomodoro", "task_id": task_id},
        ).json()["id"]

        blocked_del = self.client.delete(f"/tasks/{task_id}", headers={"X-User-Id": "1"})
        self.assertEqual(blocked_del.status_code, 409)
        self.assertEqual(blocked_del.json()["error"]["code"], "TASK_IN_ACTIVE_SESSION")

        self.client.post(f"/sessions/{sess_id}/cancel", headers={"X-User-Id": "1"})
        ok_del = self.client.delete(f"/tasks/{task_id}", headers={"X-User-Id": "1"})
        self.assertEqual(ok_del.status_code, 204)
        self.assertIsNone(self.client.get(f"/sessions/{sess_id}").json()["task_id"])

        # 3. Deleting room preserves session history with room_id = NULL
        self.assertEqual(self.client.get(f"/sessions/{sess_id}").json()["room_id"], 1)
        # Bob joins room 1, then Alice deletes her account -> ownership transfers to Bob & Alice's data cascades
        self.client.post("/rooms/1/members", json={"user_id": 2})
        self.client.post("/tasks", json={"user_id": 1, "title": "Will Cascade"})
        alice_active = self.client.post(
            "/sessions", json={"user_id": 1, "mode": "pomodoro"}
        ).json()["id"]
        self.assertIsNotNone(alice_active)

        del_alice = self.client.delete("/users/1", headers={"X-User-Id": "1"})
        self.assertEqual(del_alice.status_code, 204)

        self.assertEqual(self.client.get("/users/1").status_code, 404)
        room1_after = self.client.get("/rooms/1").json()
        self.assertEqual(room1_after["owner_id"], 2)
        self.assertEqual(room1_after["member_count"], 1)

        with self.SessionLocal() as db:
            self.assertEqual(
                db.scalar(select(func.count(Task.id)).where(Task.user_id == 1)), 0
            )
            self.assertEqual(
                db.scalar(select(func.count(FocusSession.id)).where(FocusSession.user_id == 1)), 0
            )
            self.assertEqual(
                db.scalar(
                    select(func.count(UserAchievement.id)).where(UserAchievement.user_id == 1)
                ),
                0,
            )

        # 4. Closing room directly sets remaining session.room_id = NULL
        bob_sess_id = self.client.post(
            "/sessions", json={"user_id": 2, "mode": "pomodoro"}
        ).json()["id"]
        self.assertEqual(self.client.get(f"/sessions/{bob_sess_id}").json()["room_id"], 1)
        del_room = self.client.delete("/rooms/1", headers={"X-User-Id": "2"})
        self.assertEqual(del_room.status_code, 204)
        self.assertIsNone(self.client.get(f"/sessions/{bob_sess_id}").json()["room_id"])

    def test_invalid_relationships_and_business_rules(self):
        # Missing owner FK -> 404
        res = self.client.post("/rooms", json={"name": "Ghost Room", "owner_id": 9999})
        self.assertEqual(res.status_code, 404)

        # Using someone else's task in a session -> 403
        alice_task_id = self.client.post(
            "/tasks", json={"user_id": 1, "title": "Alice Private Task"}
        ).json()["id"]
        forbidden_sess = self.client.post(
            "/sessions", json={"user_id": 2, "mode": "pomodoro", "task_id": alice_task_id}
        )
        self.assertEqual(forbidden_sess.status_code, 403)
        self.assertEqual(forbidden_sess.json()["error"]["code"], "TASK_NOT_OWNED")

        # Duplicate track (case-insensitive) -> 409
        dup_track = self.client.post(
            "/tracks",
            json={
                "title": "rainy library",
                "artist": "LOFI OWL",
                "genre": "lofi",
                "mood": "focus",
                "energy": 3,
                "duration_seconds": 180,
            },
        )
        self.assertEqual(dup_track.status_code, 409)
        self.assertEqual(dup_track.json()["error"]["code"], "TRACK_ALREADY_EXISTS")

        # Pause limit (max 3) -> 422
        sid = self.client.post("/sessions", json={"user_id": 3, "mode": "pomodoro"}).json()["id"]
        for _ in range(3):
            self.assertEqual(
                self.client.post(f"/sessions/{sid}/pause", headers={"X-User-Id": "3"}).status_code,
                200,
            )
            self.assertEqual(
                self.client.post(f"/sessions/{sid}/resume", headers={"X-User-Id": "3"}).status_code,
                200,
            )
        fourth_pause = self.client.post(f"/sessions/{sid}/pause", headers={"X-User-Id": "3"})
        self.assertEqual(fourth_pause.status_code, 422)
        self.assertEqual(fourth_pause.json()["error"]["code"], "PAUSE_LIMIT_REACHED")

        # Completing before planned time without force -> 409
        early = self.client.post(f"/sessions/{sid}/complete", headers={"X-User-Id": "3"})
        self.assertEqual(early.status_code, 409)
        self.assertEqual(early.json()["error"]["code"], "FOCUS_TIME_NOT_REACHED")


if __name__ == "__main__":
    unittest.main()
