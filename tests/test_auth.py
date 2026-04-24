import importlib
from datetime import date, timedelta

import pytest
from services import ChoreService
from werkzeug.security import check_password_hash

import database
from database import get_db_connection, init_db


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_auth.db"
    monkeypatch.setattr(database, "DB_PATH", test_db_path)
    init_db()

    app_module = importlib.reload(importlib.import_module("app"))
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def test_successful_registration(auth_client):
    response = auth_client.post(
        "/register",
        data={
            "name": "Casey RA",
            "email": "casey@school.edu",
            "password": "securepass123",
            "role": "RA",
            "room_code": "BETA501",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Account created" in response.data


def test_invalid_login(auth_client):
    response = auth_client.post(
        "/login",
        data={"email": "missing@school.edu", "password": "badpass"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_password_is_hashed(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Riley",
            "email": "riley@school.edu",
            "password": "hashedpass1",
            "role": "RA",
            "room_code": "HASH900",
        },
        follow_redirects=True,
    )
    conn = get_db_connection()
    row = conn.execute(
        "SELECT password_hash FROM users WHERE email = ?",
        ("riley@school.edu",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["password_hash"] != "hashedpass1"
    assert check_password_hash(row["password_hash"], "hashedpass1")


def test_room_code_connection(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Jordan RA",
            "email": "jordan@school.edu",
            "password": "pass12345",
            "role": "RA",
            "room_code": "ROOM777",
        },
        follow_redirects=True,
    )
    auth_client.get("/logout")
    auth_client.post(
        "/register",
        data={
            "name": "Sam Resident",
            "email": "sam@school.edu",
            "password": "pass12345",
            "role": "Resident",
            "room_code": "ROOM777",
        },
        follow_redirects=True,
    )

    conn = get_db_connection()
    ra_room = conn.execute(
        "SELECT room_id FROM users WHERE email = ?",
        ("jordan@school.edu",),
    ).fetchone()
    resident_room = conn.execute(
        "SELECT room_id FROM users WHERE email = ?",
        ("sam@school.edu",),
    ).fetchone()
    conn.close()
    assert ra_room["room_id"] == resident_room["room_id"]


def test_ra_can_view_room_code_on_settings(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Jordan RA",
            "email": "jordan@school.edu",
            "password": "pass12345",
            "role": "RA",
            "room_code": "ROOM777",
        },
        follow_redirects=True,
    )

    response = auth_client.get("/settings")
    assert response.status_code == 200
    assert b"Room Code" in response.data
    assert b"ROOM777" in response.data


def test_ra_can_update_room_name(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Taylor RA",
            "email": "taylor@school.edu",
            "password": "roomname123",
            "role": "RA",
            "room_code": "ROOM888",
        },
        follow_redirects=True,
    )

    response = auth_client.post(
        "/settings",
        data={"room_name": "Maple Floor"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Room name updated successfully" in response.data
    assert b"Maple Floor" in response.data


def test_resident_cannot_update_room_name(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Morgan RA",
            "email": "morgan@school.edu",
            "password": "roomprotect1",
            "role": "RA",
            "room_code": "ROOM999",
        },
        follow_redirects=True,
    )
    auth_client.get("/logout")
    auth_client.post(
        "/register",
        data={
            "name": "Sam Resident",
            "email": "sam@school.edu",
            "password": "roomprotect1",
            "role": "Resident",
            "room_code": "ROOM999",
        },
        follow_redirects=True,
    )

    response = auth_client.post(
        "/settings",
        data={"room_name": "Hacked Name"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Only Resident&#39;s Assistants can update room settings." in response.data
    assert b"Hacked Name" not in response.data


def test_completed_tasks_page_only_shows_completed(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Avery RA",
            "email": "avery@school.edu",
            "password": "donepass1",
            "role": "RA",
            "room_code": "ROOM101",
        },
        follow_redirects=True,
    )

    conn = get_db_connection()
    user = conn.execute("SELECT id, room_id FROM users WHERE email = ?", ("avery@school.edu",)).fetchone()
    conn.close()
    service = ChoreService()
    first = service.create_chore("Done Task", "Finish this", "", None, user["id"], room_id=user["room_id"])
    second = service.create_chore("Pending Task", "Keep working", "", None, user["id"], room_id=user["room_id"])
    service.mark_complete(first, room_id=user["room_id"])

    response = auth_client.get("/tasks/completed")
    assert response.status_code == 200
    assert b"Done Task" in response.data
    assert b"Pending Task" not in response.data


def test_navigation_routes_filter_tasks(auth_client):
    auth_client.post(
        "/register",
        data={
            "name": "Casey RA",
            "email": "casey2@school.edu",
            "password": "navpass123",
            "role": "RA",
            "room_code": "ROOM202",
        },
        follow_redirects=True,
    )

    conn = get_db_connection()
    user = conn.execute("SELECT id, room_id FROM users WHERE email = ?", ("casey2@school.edu",)).fetchone()
    conn.close()
    service = ChoreService()
    overdue_date = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    service.create_chore("Overdue Task", "Late chore", overdue_date, None, user["id"], room_id=user["room_id"])
    pending_id = service.create_chore("Open Task", "Work in progress", "", None, user["id"], room_id=user["room_id"])
    completed_id = service.create_chore("Closed Task", "Already done", "", None, user["id"], room_id=user["room_id"])
    service.mark_complete(completed_id, room_id=user["room_id"])

    assigned = auth_client.get("/tasks/assigned")
    assert b"Open Task" in assigned.data
    assert b"Overdue Task" in assigned.data
    assert b"Closed Task" not in assigned.data

    overdue = auth_client.get("/tasks/overdue")
    assert b"Overdue Task" in overdue.data
    assert b"Open Task" not in overdue.data

    completed = auth_client.get("/tasks/completed")
    assert b"Closed Task" in completed.data
    assert b"Open Task" not in completed.data


def test_protected_route_redirects_unauthenticated(auth_client):
    response = auth_client.get("/chores")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
