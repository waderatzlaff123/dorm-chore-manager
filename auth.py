import random
import string
from functools import wraps

from flask import flash, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection


class AuthError(Exception):
    """Raised for authentication and registration errors."""


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


def _normalize_email(email):
    return (email or "").strip().lower()


def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT u.id, u.name, u.email, u.role, u.room_id, r.room_name, r.room_code
        FROM users u
        LEFT JOIN rooms r ON u.room_id = r.id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def authenticate_user(email, password):
    clean_email = _normalize_email(email)
    conn = get_db_connection()
    user = conn.execute(
        """
        SELECT u.id, u.name, u.email, u.password_hash, u.role, u.room_id, r.room_name, r.room_code
        FROM users u
        LEFT JOIN rooms r ON u.room_id = r.id
        WHERE u.email = ?
        """,
        (clean_email,),
    ).fetchone()
    conn.close()
    if not user or not user["password_hash"]:
        return None
    if not check_password_hash(user["password_hash"], password):
        return None
    return dict(user)


def _generate_unique_room_code(conn, length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(50):
        code = "".join(random.choice(alphabet) for _ in range(length))
        existing = conn.execute("SELECT id FROM rooms WHERE room_code = ?", (code,)).fetchone()
        if not existing:
            return code
    raise AuthError("Unable to generate a unique room code. Please try again.")


def register_user(name, email, password, role, room_code):
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)
    clean_role = (role or "").strip()
    clean_room_code = (room_code or "").strip().upper()

    if not clean_name or not clean_email or not password or not clean_role:
        raise AuthError("All fields are required.")
    if clean_role not in {"RA", "Resident"}:
        raise AuthError("Role must be RA or Resident.")

    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (clean_email,)).fetchone()
    if existing:
        conn.close()
        raise AuthError("That email is already registered.")

    room_id = None
    room_name = None

    if clean_role == "RA":
        clean_room_code = _generate_unique_room_code(conn)
        room_name = f"{clean_name}'s Room"
        cursor = conn.execute(
            "INSERT INTO rooms (room_name, room_code, created_by) VALUES (?, ?, ?)",
            (room_name, clean_room_code, None),
        )
        room_id = cursor.lastrowid
    else:
        if not clean_room_code:
            conn.close()
            raise AuthError("Room code is required for resident signup.")
        room = conn.execute(
            "SELECT id, room_name FROM rooms WHERE room_code = ?",
            (clean_room_code,),
        ).fetchone()
        if not room:
            conn.close()
            raise AuthError("Invalid room code for resident signup.")
        room_id = room["id"]
        room_name = room["room_name"]

    password_hash = generate_password_hash(password)
    user_cursor = conn.execute(
        """
        INSERT INTO users (name, email, password_hash, role, room_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (clean_name, clean_email, password_hash, clean_role, room_id),
    )
    user_id = user_cursor.lastrowid

    if clean_role == "RA":
        conn.execute(
            "UPDATE rooms SET created_by = COALESCE(created_by, ?) WHERE id = ?",
            (user_id, room_id),
        )

    conn.commit()
    conn.close()
    return {
        "id": user_id,
        "name": clean_name,
        "email": clean_email,
        "role": clean_role,
        "room_id": room_id,
        "room_name": room_name,
        "room_code": clean_room_code,
    }
