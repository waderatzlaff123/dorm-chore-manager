from datetime import date, timedelta

import pytest

import database
from database import get_db_connection, init_db
from exceptions import InvalidChoreError
from services import ChoreService


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", test_db_path)
    init_db()
    return test_db_path


@pytest.fixture()
def test_client(isolated_db):
    import importlib

    app_module = importlib.reload(importlib.import_module("app"))
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        yield client


def test_create_valid_chore_stores_in_database(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore(
        "Clean lounge",
        "Vacuum and wipe tables",
        "2099-12-31",
        "18:00",
        ["all"],
        1,
    )
    conn = get_db_connection()
    row = conn.execute("SELECT id, title FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["title"] == "Clean lounge"


def test_mark_complete_updates_status(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Laundry room", "Fold towels", "2099-12-31", "08:30", ["all"], 1)
    service.mark_complete(chore_id)
    conn = get_db_connection()
    row = conn.execute("SELECT status FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["status"] == "Completed"


def test_resident_completion_tracks_assignment_rows(isolated_db):
    service = ChoreService()
    conn = get_db_connection()
    resident_rows = conn.execute("SELECT id FROM users WHERE role = 'Resident' ORDER BY id LIMIT 2").fetchall()
    conn.close()
    resident_ids = [str(row["id"]) for row in resident_rows]
    assert len(resident_ids) == 2

    chore_id = service.create_chore("Shared task", "Two residents", "2099-12-31", "09:00", resident_ids, 1)
    first_resident_id = int(resident_ids[0])
    second_resident_id = int(resident_ids[1])

    service.mark_complete(chore_id, room_id=1, resident_id=first_resident_id)

    conn = get_db_connection()
    summary = conn.execute(
        "SELECT status FROM chores WHERE id = ?", (chore_id,)
    ).fetchone()["status"]
    assignment_statuses = conn.execute(
        "SELECT resident_id, status FROM assignments WHERE chore_id = ? ORDER BY resident_id",
        (chore_id,),
    ).fetchall()
    conn.close()

    assert summary == "Partially Completed"
    assert assignment_statuses[0]["status"] == "Completed"
    assert assignment_statuses[1]["status"] == "Pending"

    service.mark_complete(chore_id, room_id=1, resident_id=second_resident_id)
    conn = get_db_connection()
    summary = conn.execute("SELECT status FROM chores WHERE id = ?", (chore_id,)).fetchone()["status"]
    conn.close()
    assert summary == "Completed"


def test_delete_chore_removes_from_database(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Study area", "Organize chairs", "2099-12-31", "", ["all"], 1)
    service.delete_chore(chore_id)
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row is None


def test_resident_route_loads(test_client):
    response = test_client.get("/resident/2/chores")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_overdue_generator_returns_old_chores(isolated_db):
    service = ChoreService()
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    service.create_chore("Bathroom", "Disinfect sinks", yesterday, "", ["2"], 1)
    chores = service.get_chores()
    overdue = list(service.overdue_chores(chores))
    assert len(overdue) == 1


def test_task_can_be_created_with_optional_due_time(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Study hall", "Organize books", "2099-12-31", "19:45", ["all"], 1)
    conn = get_db_connection()
    row = conn.execute("SELECT due_time FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["due_time"] == "19:45"


def test_task_can_be_created_without_due_time(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Kitchen sink", "Wipe counters", "2099-12-31", "", ["all"], 1)
    conn = get_db_connection()
    row = conn.execute("SELECT due_time FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["due_time"] is None


def test_assignment_requires_at_least_one_resident(isolated_db):
    service = ChoreService()
    with pytest.raises(InvalidChoreError):
        service.create_chore("Missing assign", "No residents", "2099-12-31", "", [], 1)


def test_all_residents_assignment_creates_multiple_records(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Hall sweep", "Clean hallway", "2099-12-31", "", ["all"], 1)
    conn = get_db_connection()
    rows = conn.execute("SELECT COUNT(*) AS count FROM assignments WHERE chore_id = ?", (chore_id,)).fetchone()
    conn.close()
    assert rows["count"] > 1


def test_resident_calendar_only_shows_their_tasks(test_client):
    register_ra = test_client.post(
        "/register",
        data={
            "name": "Mia RA",
            "email": "mia@school.edu",
            "password": "pass123",
            "role": "RA",
            "room_code": "IGNORE",
        },
        follow_redirects=True,
    )
    assert register_ra.status_code == 200

    conn = get_db_connection()
    ra_user = conn.execute("SELECT id, room_id FROM users WHERE email = ?", ("mia@school.edu",)).fetchone()
    room_code = conn.execute("SELECT room_code FROM rooms WHERE id = ?", (ra_user["room_id"],)).fetchone()["room_code"]
    conn.close()

    test_client.get("/logout", follow_redirects=True)
    test_client.post(
        "/register",
        data={
            "name": "Alex Resident",
            "email": "alexr@school.edu",
            "password": "pass123",
            "role": "Resident",
            "room_code": room_code,
        },
        follow_redirects=True,
    )
    test_client.get("/logout", follow_redirects=True)
    test_client.post(
        "/register",
        data={
            "name": "Taylor Resident",
            "email": "taylorres@school.edu",
            "password": "pass123",
            "role": "Resident",
            "room_code": room_code,
        },
        follow_redirects=True,
    )

    conn = get_db_connection()
    alex_id = conn.execute("SELECT id FROM users WHERE email = ?", ("alexr@school.edu",)).fetchone()["id"]
    taylor_id = conn.execute("SELECT id FROM users WHERE email = ?", ("taylorres@school.edu",)).fetchone()["id"]
    conn.close()

    service = ChoreService()
    today = date.today().strftime("%Y-%m-%d")
    service.create_chore("Alex only", "Only for Alex", today, "", [str(alex_id)], ra_user["id"], room_id=ra_user["room_id"])
    service.create_chore("Taylor only", "Only for Taylor", today, "", [str(taylor_id)], ra_user["id"], room_id=ra_user["room_id"])

    test_client.get("/logout", follow_redirects=True)
    login_response = test_client.post(
        "/login",
        data={"email": "alexr@school.edu", "password": "pass123"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    response = test_client.get("/calendar")
    assert b"Alex only" in response.data
    assert b"Taylor only" not in response.data


def test_ra_calendar_shows_room_tasks(test_client):
    register_ra = test_client.post(
        "/register",
        data={
            "name": "Noah RA",
            "email": "noah@school.edu",
            "password": "pass123",
            "role": "RA",
            "room_code": "IGNORE",
        },
        follow_redirects=True,
    )
    assert register_ra.status_code == 200

    conn = get_db_connection()
    ra_user = conn.execute("SELECT id, room_id FROM users WHERE email = ?", ("noah@school.edu",)).fetchone()
    room_code = conn.execute("SELECT room_code FROM rooms WHERE id = ?", (ra_user["room_id"],)).fetchone()["room_code"]
    conn.close()

    test_client.get("/logout", follow_redirects=True)
    test_client.post(
        "/register",
        data={
            "name": "Resident One",
            "email": "residentnoah@school.edu",
            "password": "pass123",
            "role": "Resident",
            "room_code": room_code,
        },
        follow_redirects=True,
    )
    conn = get_db_connection()
    resident_id = conn.execute("SELECT id FROM users WHERE email = ?", ("residentnoah@school.edu",)).fetchone()["id"]
    conn.close()

    service = ChoreService()
    today = date.today().strftime("%Y-%m-%d")
    service.create_chore("Room task", "Shared room task", today, "", [str(resident_id)], ra_user["id"], room_id=ra_user["room_id"])

    test_client.get("/logout", follow_redirects=True)
    login_response = test_client.post(
        "/login",
        data={"email": "noah@school.edu", "password": "pass123"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200

    response = test_client.get("/calendar")
    assert b"Room task" in response.data
