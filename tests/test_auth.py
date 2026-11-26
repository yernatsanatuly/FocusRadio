import os
import sys
import unittest
from datetime import timedelta

import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.core.seed import DEMO_PASSWORD, seed_demo_data
from app.main import app
from app.models import User
from app.models.enums import UserRole

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


class TestAuthAndAuthorization(unittest.TestCase):
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

        cls._orig_seed_demo_data = settings.seed_demo_data
        settings.seed_demo_data = False
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
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

        self.admin_headers = self._login("alice")  # id=1, admin
        self.bob_headers = self._login("bob")      # id=2, user
        self.carol_headers = self._login("carol")  # id=3, user

    def _login(
        self,
        username: str | None = None,
        password: str = DEMO_PASSWORD,
        *,
        email: str | None = None,
    ) -> dict[str, str]:
        body: dict[str, str] = {"password": password}
        if username is not None:
            body["username"] = username
        if email is not None:
            body["email"] = email
        res = self.client.post("/auth/login", json=body)
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    # -------------------------------------------------------- Registration
    def test_register_hashes_password_and_prevents_duplicates(self):
        plain = "MyUltraSecret99!"
        res = self.client.post(
            "/auth/register",
            json={
                "username": "NewUser_1",
                "display_name": "New User",
                "email": "NewUser@Example.COM",
                "password": plain,
                "role": "admin",  # must be ignored by RegisterRequest
                "bio": "Hello FocusRadio",
            },
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["username"], "newuser_1")
        self.assertEqual(body["email"], "newuser@example.com")
        self.assertEqual(body["role"], "user")
        self.assertNotIn("password", body)
        self.assertNotIn("hashed_password", body)

        # Verify password is stored as a secure bcrypt hash in PostgreSQL
        with self.SessionLocal() as db:
            db_user = db.get(User, body["id"])
            self.assertIsNotNone(db_user)
            self.assertNotEqual(db_user.hashed_password, plain)
            self.assertTrue(db_user.hashed_password.startswith("$2"))
            self.assertTrue(verify_password(plain, db_user.hashed_password))
            self.assertFalse(verify_password("wrong-password", db_user.hashed_password))

        # Duplicate username (case-insensitive) -> 409
        dup_user = self.client.post(
            "/auth/register",
            json={
                "username": "NEWUSER_1",
                "display_name": "Clone",
                "email": "another@example.com",
                "password": "AnotherPassword123!",
            },
        )
        self.assertEqual(dup_user.status_code, 409)
        self.assertEqual(dup_user.json()["error"]["code"], "USERNAME_TAKEN")

        # Duplicate email (case-insensitive) -> 409
        dup_email = self.client.post(
            "/auth/register",
            json={
                "username": "unique_name",
                "display_name": "Clone",
                "email": "newuser@example.com",
                "password": "AnotherPassword123!",
            },
        )
        self.assertEqual(dup_email.status_code, 409)
        self.assertEqual(dup_email.json()["error"]["code"], "EMAIL_TAKEN")

        # Weak / short password -> 422
        short_pw = self.client.post(
            "/auth/register",
            json={
                "username": "short_pw_user",
                "display_name": "Short",
                "email": "short@example.com",
                "password": "123",
            },
        )
        self.assertEqual(short_pw.status_code, 422)
        self.assertEqual(short_pw.json()["error"]["code"], "VALIDATION_ERROR")

    # -------------------------------------------------------- Login & JWT
    def test_login_by_username_or_email_and_invalid_credentials(self):
        # Login by username
        res_user = self.client.post(
            "/auth/login", json={"username": "BOB", "password": DEMO_PASSWORD}
        )
        self.assertEqual(res_user.status_code, 200)
        data = res_user.json()
        self.assertEqual(data["token_type"], "bearer")
        self.assertTrue(data["access_token"])
        self.assertGreater(data["expires_in"], 0)
        self.assertEqual(data["user"]["username"], "bob")

        # Login by email field
        res_email = self.client.post(
            "/auth/login",
            json={"email": "CAROL@focusradio.dev", "password": DEMO_PASSWORD},
        )
        self.assertEqual(res_email.status_code, 200)
        self.assertEqual(res_email.json()["user"]["username"], "carol")

        # Login by passing email in username field
        res_ident = self.client.post(
            "/auth/login",
            json={"username": "alice@focusradio.dev", "password": DEMO_PASSWORD},
        )
        self.assertEqual(res_ident.status_code, 200)
        self.assertEqual(res_ident.json()["user"]["role"], "admin")

        # Wrong password -> 401
        wrong_pw = self.client.post(
            "/auth/login", json={"username": "bob", "password": "wrong_password"}
        )
        self.assertEqual(wrong_pw.status_code, 401)
        self.assertEqual(wrong_pw.json()["error"]["code"], "INVALID_CREDENTIALS")
        self.assertEqual(wrong_pw.headers.get("www-authenticate"), "Bearer")

        # Unknown user -> 401 (same generic error code)
        unknown = self.client.post(
            "/auth/login", json={"username": "ghost_user", "password": DEMO_PASSWORD}
        )
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json()["error"]["code"], "INVALID_CREDENTIALS")

        # Missing both username and email -> 422
        missing_ident = self.client.post("/auth/login", json={"password": DEMO_PASSWORD})
        self.assertEqual(missing_ident.status_code, 422)

    # -------------------------------------------------------- Protected Endpoints
    def test_protected_endpoints_reject_missing_invalid_and_expired_tokens(self):
        # 1. Missing token -> 401 on protected endpoints
        for method, path in [
            ("GET", "/auth/me"),
            ("GET", "/users"),
            ("GET", "/tasks"),
            ("GET", "/sessions"),
            ("POST", "/rooms"),
            ("POST", "/tracks"),
        ]:
            res = self.client.request(method, path)
            self.assertEqual(res.status_code, 401, f"{method} {path} -> {res.text}")
            self.assertEqual(res.json()["error"]["code"], "NOT_AUTHENTICATED")
            self.assertEqual(res.headers.get("www-authenticate"), "Bearer")

        # 2. Malformed token -> 401
        malformed = self.client.get(
            "/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"}
        )
        self.assertEqual(malformed.status_code, 401)
        self.assertEqual(malformed.json()["error"]["code"], "INVALID_TOKEN")

        # 3. Token signed with wrong secret -> 401
        forged_token = jwt.encode(
            {"sub": "1", "role": "admin", "type": "access", "exp": 9999999999},
            "completely-wrong-secret-key-at-least-32-bytes-long",
            algorithm="HS256",
        )
        forged = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {forged_token}"}
        )
        self.assertEqual(forged.status_code, 401)
        self.assertEqual(forged.json()["error"]["code"], "INVALID_TOKEN")

        # 4. Expired token -> 401 TOKEN_EXPIRED
        expired_token, _ = create_access_token(
            2, UserRole.USER, expires_delta=timedelta(seconds=-10)
        )
        expired = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        )
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(expired.json()["error"]["code"], "TOKEN_EXPIRED")

        # 5. Token for a deleted user -> 401 USER_NOT_FOUND
        ghost_token, _ = create_access_token(9999, UserRole.USER)
        ghost = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {ghost_token}"}
        )
        self.assertEqual(ghost.status_code, 401)
        self.assertEqual(ghost.json()["error"]["code"], "USER_NOT_FOUND")

        # 6. Valid token -> 200
        ok = self.client.get("/auth/me", headers=self.bob_headers)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["id"], 2)
        self.assertEqual(ok.json()["username"], "bob")

    # -------------------------------------------------------- Role-Based Access Control
    def test_role_based_access_control_tracks_and_user_admin(self):
        track_payload = {
            "title": "Deep Focus Rain",
            "artist": "Focus Studio",
            "genre": "ambient",
            "mood": "focus",
            "energy": 2,
            "duration_seconds": 300,
        }

        # Regular user cannot create, update, or delete tracks -> 403
        user_create = self.client.post(
            "/tracks", headers=self.bob_headers, json=track_payload
        )
        self.assertEqual(user_create.status_code, 403)
        self.assertEqual(user_create.json()["error"]["code"], "ADMIN_REQUIRED")

        user_patch = self.client.patch(
            "/tracks/2", headers=self.bob_headers, json={"energy": 5}
        )
        self.assertEqual(user_patch.status_code, 403)

        user_delete = self.client.delete("/tracks/2", headers=self.bob_headers)
        self.assertEqual(user_delete.status_code, 403)

        # Admin can create, update, and delete tracks
        admin_create = self.client.post(
            "/tracks", headers=self.admin_headers, json=track_payload
        )
        self.assertEqual(admin_create.status_code, 201)
        new_track_id = admin_create.json()["id"]

        admin_patch = self.client.patch(
            f"/tracks/{new_track_id}", headers=self.admin_headers, json={"energy": 4}
        )
        self.assertEqual(admin_patch.status_code, 200)
        self.assertEqual(admin_patch.json()["energy"], 4)

        admin_delete = self.client.delete(
            f"/tracks/{new_track_id}", headers=self.admin_headers
        )
        self.assertEqual(admin_delete.status_code, 204)

        # Regular user cannot use admin POST /users or PATCH /users/{id}/role
        forb_create_user = self.client.post(
            "/users",
            headers=self.bob_headers,
            json={
                "username": "sneaky_admin",
                "display_name": "Sneaky",
                "email": "sneaky@example.com",
                "password": "SneakyPassword123!",
                "role": "admin",
            },
        )
        self.assertEqual(forb_create_user.status_code, 403)

        forb_role = self.client.patch(
            "/users/2/role", headers=self.bob_headers, json={"role": "admin"}
        )
        self.assertEqual(forb_role.status_code, 403)

        # Cannot demote the last admin
        last_admin = self.client.patch(
            "/users/1/role", headers=self.admin_headers, json={"role": "user"}
        )
        self.assertEqual(last_admin.status_code, 409)
        self.assertEqual(last_admin.json()["error"]["code"], "LAST_ADMIN_REQUIRED")

        # Admin promotes Bob -> now Bob can create tracks
        promote = self.client.patch(
            "/users/2/role", headers=self.admin_headers, json={"role": "admin"}
        )
        self.assertEqual(promote.status_code, 200)
        self.assertEqual(promote.json()["role"], "admin")

        bob_now_admin = self.client.post(
            "/tracks", headers=self.bob_headers, json=track_payload
        )
        self.assertEqual(bob_now_admin.status_code, 201)

    # -------------------------------------------------------- Ownership Access Control
    def test_task_and_session_ownership_restrictions(self):
        # Bob creates a task and starts a focus session
        bob_task = self.client.post(
            "/tasks", headers=self.bob_headers, json={"title": "Bob Secret Task"}
        )
        self.assertEqual(bob_task.status_code, 201)
        bob_task_id = bob_task.json()["id"]

        carol_task = self.client.post(
            "/tasks", headers=self.carol_headers, json={"title": "Carol Own Task"}
        )
        self.assertEqual(carol_task.status_code, 201)

        # Carol sees ONLY her own tasks in GET /tasks
        carol_list = self.client.get("/tasks", headers=self.carol_headers)
        self.assertEqual(carol_list.status_code, 200)
        self.assertEqual(carol_list.json()["total"], 1)
        self.assertEqual(carol_list.json()["items"][0]["user_id"], 3)

        # Carol cannot filter tasks by Bob's user_id or read/update/delete Bob's task
        self.assertEqual(
            self.client.get("/tasks?user_id=2", headers=self.carol_headers).status_code, 403
        )
        self.assertEqual(
            self.client.get(f"/tasks/{bob_task_id}", headers=self.carol_headers).status_code, 403
        )
        self.assertEqual(
            self.client.patch(
                f"/tasks/{bob_task_id}",
                headers=self.carol_headers,
                json={"title": "Tampered"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/tasks/{bob_task_id}", headers=self.carol_headers).status_code,
            403,
        )

        # Admin can view all tasks and moderate Bob's task
        admin_tasks = self.client.get("/tasks", headers=self.admin_headers)
        self.assertEqual(admin_tasks.status_code, 200)
        self.assertEqual(admin_tasks.json()["total"], 2)

        # Bob starts a focus session
        bob_sess = self.client.post(
            "/sessions",
            headers=self.bob_headers,
            json={"mode": "pomodoro", "task_id": bob_task_id},
        )
        self.assertEqual(bob_sess.status_code, 201)
        bob_sess_id = bob_sess.json()["id"]

        # Carol cannot view, update, pause, complete, cancel, or delete Bob's session
        self.assertEqual(
            self.client.get("/sessions?user_id=2", headers=self.carol_headers).status_code, 403
        )
        self.assertEqual(
            self.client.get(f"/sessions/{bob_sess_id}", headers=self.carol_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/sessions/{bob_sess_id}",
                headers=self.carol_headers,
                json={"notes": "Injected"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/sessions/{bob_sess_id}/pause", headers=self.carol_headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/sessions/{bob_sess_id}/complete?force=true", headers=self.carol_headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/sessions/{bob_sess_id}/cancel", headers=self.carol_headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/sessions/{bob_sess_id}", headers=self.carol_headers).status_code,
            403,
        )

        # Carol's session list does not expose Bob's session
        carol_sessions = self.client.get("/sessions", headers=self.carol_headers)
        self.assertEqual(carol_sessions.status_code, 200)
        self.assertEqual(carol_sessions.json()["total"], 0)

    def test_room_and_user_ownership_vs_admin_moderation(self):
        # Bob creates a room and Carol joins
        room_res = self.client.post(
            "/rooms",
            headers=self.bob_headers,
            json={"name": "Bob Study Lounge", "capacity": 5},
        )
        self.assertEqual(room_res.status_code, 201)
        room_id = room_res.json()["id"]

        join_res = self.client.post(f"/rooms/{room_id}/members", headers=self.carol_headers)
        self.assertEqual(join_res.status_code, 201)

        # Carol (member, not owner) cannot edit/close the room or kick Bob
        self.assertEqual(
            self.client.patch(
                f"/rooms/{room_id}",
                headers=self.carol_headers,
                json={"name": "Hijacked Room"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(f"/rooms/{room_id}", headers=self.carol_headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                f"/rooms/{room_id}/members/2", headers=self.carol_headers
            ).status_code,
            403,
        )

        # Carol cannot edit or delete Bob's account
        self.assertEqual(
            self.client.patch(
                "/users/2", headers=self.carol_headers, json={"bio": "Not allowed"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete("/users/2", headers=self.carol_headers).status_code,
            403,
        )

        # Admin Alice CAN moderate Bob's room (update, kick, close) and update Bob's profile
        admin_update_room = self.client.patch(
            f"/rooms/{room_id}",
            headers=self.admin_headers,
            json={"description": "Moderated by admin"},
        )
        self.assertEqual(admin_update_room.status_code, 200)

        admin_kick = self.client.delete(
            f"/rooms/{room_id}/members/3", headers=self.admin_headers
        )
        self.assertEqual(admin_kick.status_code, 200)
        self.assertTrue(admin_kick.json()["kicked"])

        admin_close = self.client.delete(f"/rooms/{room_id}", headers=self.admin_headers)
        self.assertEqual(admin_close.status_code, 204)

        admin_del_carol = self.client.delete("/users/3", headers=self.admin_headers)
        self.assertEqual(admin_del_carol.status_code, 204)


if __name__ == "__main__":
    unittest.main()
