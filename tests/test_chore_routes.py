from datetime import date, timedelta

import pytest

import database
from database import get_db_connection, init_db
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
        "",
        None,
        1,
    )
    conn = get_db_connection()
    row = conn.execute("SELECT id, title FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["title"] == "Clean lounge"


def test_mark_complete_updates_status(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Laundry room", "Fold towels", "", None, 1)
    service.mark_complete(chore_id)
    conn = get_db_connection()
    row = conn.execute("SELECT status FROM chores WHERE id = ?", (chore_id,)).fetchone()
    conn.close()
    assert row["status"] == "Completed"


def test_delete_chore_removes_from_database(isolated_db):
    service = ChoreService()
    chore_id = service.create_chore("Study area", "Organize chairs", "", None, 1)
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
    service.create_chore("Bathroom", "Disinfect sinks", yesterday, 2, 1)
    chores = service.get_chores()
    overdue = list(service.overdue_chores(chores))
    assert len(overdue) == 1
