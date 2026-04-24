import importlib

import pytest
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


def test_protected_route_redirects_unauthenticated(auth_client):
    response = auth_client.get("/chores")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
