import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import db, seed_demo_data
from app.config import settings


class TestFocusRadioAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Accelerate timer for tests so 1 minute = 0.01 seconds
        settings.seconds_per_minute = 0.05
        cls.client = TestClient(app)

    def setUp(self):
        db.reset()
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

        bad_res = self.client.post("/users", json={
            "username": "bad_user",
            "display_name": "Bad",
            "email": "not-an-email",
        })
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

        bad_join = self.client.post(f"/rooms/{room_id}/members", json={"user_id": 3, "access_code": "wrong"})
        self.assertEqual(bad_join.status_code, 403)
        self.assertEqual(bad_join.json()["error"]["code"], "INVALID_ACCESS_CODE")

        join_res = self.client.post(f"/rooms/{room_id}/members", json={"user_id": 3, "access_code": "code2026"})
        self.assertEqual(join_res.status_code, 201)
        self.assertEqual(join_res.json()["member_count"], 2)

        track_res = self.client.put(
            f"/rooms/{room_id}/track",
            headers={"X-User-Id": "3"},
            json={"track_id": 9},  # Neon Sprint (synthwave)
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

        leave_res = self.client.delete(f"/rooms/{room_id}/members/2", headers={"X-User-Id": "2"})
        self.assertEqual(leave_res.status_code, 200)
        self.assertEqual(leave_res.json()["new_owner_id"], 3)

        leave_last = self.client.delete(f"/rooms/{room_id}/members/3", headers={"X-User-Id": "3"})
        self.assertEqual(leave_last.status_code, 200)
        self.assertTrue(leave_last.json()["room_deleted"])

        get_res = self.client.get(f"/rooms/{room_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_focus_session_and_task_integration(self):

        task_res = self.client.post("/tasks", json={
            "user_id": 1,
            "title": "Build FastAPI Architecture",
            "description": "Entities, services, routers",
            "priority": "high",
            "estimated_pomodoros": 2,
        })
        self.assertEqual(task_res.status_code, 201)
        task_id = task_res.json()["id"]

        session_res = self.client.post("/sessions", json={
            "user_id": 1,
            "mode": "custom",
            "focus_minutes": 1,
            "break_minutes": 1,
            "task_id": task_id,
            "notes": "Coding services",
        })
        self.assertEqual(session_res.status_code, 201)
        session = session_res.json()
        session_id = session["id"]
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["task_id"], task_id)

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
        import time

        res = self.client.post("/sessions", json={
            "user_id": 2,
            "mode": "custom",
            "focus_minutes": 1,
            "break_minutes": 1,
        })
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

        ach_res = self.client.get("/users/2/achievements?unlocked_only=true")
        self.assertEqual(ach_res.status_code, 200)
        codes = [a["code"] for a in ach_res.json()]
        self.assertIn("first_tune_in", codes)

        lb = self.client.get("/leaderboard?metric=xp")
        self.assertEqual(lb.status_code, 200)
        entries = lb.json()["entries"]
        self.assertTrue(len(entries) >= 2)

        self.assertEqual(entries[0]["user_id"], 2)


if __name__ == "__main__":
    unittest.main()
