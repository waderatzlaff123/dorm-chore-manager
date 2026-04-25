from datetime import date, datetime
from functools import wraps
from typing import Dict, Iterable, List, Optional

from database import get_db_connection
from exceptions import ChoreError, ChoreNotFoundError, InvalidChoreError
from models import Chore


def validate_chore_title(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        title = kwargs.get("title")
        if title is None and len(args) >= 1:
            title = args[0]
        if not title or not title.strip():
            raise InvalidChoreError("Chore title cannot be empty.")
        return func(self, *args, **kwargs)

    return wrapper


class ChoreService:
    @staticmethod
    def _validate_due_date(due_date: str) -> Optional[str]:
        if not due_date:
            return None
        try:
            return datetime.strptime(due_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise InvalidChoreError("Due date must be in YYYY-MM-DD format.") from exc

    @staticmethod
    def _map_chore(row) -> Chore:
        return Chore(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            due_date=row["due_date"],
            status=row["status"],
        )

    def get_residents(self, room_id: Optional[int] = None) -> List[Dict]:
        conn = get_db_connection()
        if room_id:
            rows = conn.execute(
                """
                SELECT id, name, role, room_id
                FROM users
                WHERE role = 'Resident' AND room_id = ?
                ORDER BY name
                """,
                (room_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, role, room_id FROM users WHERE role = 'Resident' ORDER BY name"
            ).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_room(self, room_id: int) -> Dict:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT id, room_name, room_code FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
        conn.close()
        if not row:
            raise ValueError(f"Room with id {room_id} was not found.")
        return dict(row)

    def update_room_name(self, room_id: int, room_name: str) -> None:
        if not room_name or not room_name.strip():
            raise ValueError("Room name cannot be blank.")
        conn = get_db_connection()
        conn.execute(
            "UPDATE rooms SET room_name = ? WHERE id = ?",
            (room_name.strip(), room_id),
        )
        conn.commit()
        conn.close()

    def get_chores(self, room_id: Optional[int] = None) -> List[Dict]:
        conn = get_db_connection()
        if room_id:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status, c.room_id,
                       u.name AS resident_name, a.resident_id
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                LEFT JOIN users u ON a.resident_id = u.id
                WHERE c.room_id = ?
                ORDER BY c.id DESC
                """,
                (room_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status, c.room_id,
                       u.name AS resident_name, a.resident_id
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                LEFT JOIN users u ON a.resident_id = u.id
                ORDER BY c.id DESC
                """
            ).fetchall()
        conn.close()

        chores = []
        for row in rows:
            chore = self._map_chore(row)
            status = "Overdue" if chore.is_overdue() else chore.status
            chores.append(
                {
                    "id": chore.id,
                    "title": chore.title,
                    "description": chore.description,
                    "due_date": chore.due_date,
                    "status": status,
                    "resident_name": row["resident_name"],
                    "resident_id": row["resident_id"],
                    "room_id": row["room_id"],
                }
            )
        return chores

    def get_chore(self, chore_id: int, room_id: Optional[int] = None) -> Dict:
        conn = get_db_connection()
        if room_id:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status, c.room_id, a.resident_id
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                WHERE c.id = ? AND c.room_id = ?
                """,
                (chore_id, room_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status, c.room_id, a.resident_id
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                WHERE c.id = ?
                """,
                (chore_id,),
            ).fetchone()
        conn.close()
        if not row:
            raise ChoreNotFoundError(f"Chore with id {chore_id} was not found.")
        return {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"] or "",
            "due_date": row["due_date"] or "",
            "status": row["status"],
            "resident_id": row["resident_id"],
            "room_id": row["room_id"],
        }

    @validate_chore_title
    def create_chore(
        self,
        title: str,
        description: str,
        due_date: str,
        resident_id: Optional[int],
        assigned_by: int,
        room_id: int = 1,
    ) -> int:
        clean_due_date = self._validate_due_date(due_date)
        conn = get_db_connection()
        cursor = conn.execute(
            """
            INSERT INTO chores (title, description, due_date, status, room_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), description.strip(), clean_due_date, "Pending", room_id, assigned_by),
        )
        chore_id = cursor.lastrowid

        if chore_id is None:
            conn.close()
            raise ChoreError("Failed to create chore.")
        
        if resident_id:
            conn.execute(
                """
                INSERT INTO assignments (chore_id, resident_id, assigned_by, room_id)
                VALUES (?, ?, ?, ?)
                """,
                (chore_id, resident_id, assigned_by, room_id),
            )
        conn.commit()
        conn.close()
        return chore_id

    @validate_chore_title
    def update_chore(
        self,
        chore_id: int,
        title: str,
        description: str,
        due_date: str,
        resident_id: Optional[int],
        room_id: int = 1,
        assigned_by: int = 1,
    ) -> None:
        clean_due_date = self._validate_due_date(due_date)
        self.get_chore(chore_id, room_id=room_id)
        conn = get_db_connection()
        conn.execute(
            """
            UPDATE chores
            SET title = ?, description = ?, due_date = ?
            WHERE id = ? AND room_id = ?
            """,
            (title.strip(), description.strip(), clean_due_date, chore_id, room_id),
        )

        conn.execute("DELETE FROM assignments WHERE chore_id = ?", (chore_id,))
        if resident_id:
            conn.execute(
                """
                INSERT INTO assignments (chore_id, resident_id, assigned_by, room_id)
                VALUES (?, ?, ?, ?)
                """,
                (chore_id, resident_id, assigned_by, room_id),
            )
        conn.commit()
        conn.close()

    def delete_chore(self, chore_id: int, room_id: int = 1) -> None:
        self.get_chore(chore_id, room_id=room_id)
        conn = get_db_connection()
        conn.execute("DELETE FROM assignments WHERE chore_id = ?", (chore_id,))
        conn.execute("DELETE FROM chores WHERE id = ? AND room_id = ?", (chore_id, room_id))
        conn.commit()
        conn.close()

    def mark_complete(self, chore_id: int, room_id: int = 1) -> None:
        self.get_chore(chore_id, room_id=room_id)
        conn = get_db_connection()
        conn.execute(
            "UPDATE chores SET status = 'Completed' WHERE id = ? AND room_id = ?",
            (chore_id, room_id),
        )
        conn.commit()
        conn.close()

    def get_resident_chores(self, resident_id: int, room_id: Optional[int] = None) -> List[Dict]:
        conn = get_db_connection()
        if room_id:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status
                FROM chores c
                JOIN assignments a ON c.id = a.chore_id
                WHERE a.resident_id = ? AND c.room_id = ?
                ORDER BY c.id DESC
                """,
                (resident_id, room_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.status
                FROM chores c
                JOIN assignments a ON c.id = a.chore_id
                WHERE a.resident_id = ?
                ORDER BY c.id DESC
                """,
                (resident_id,),
            ).fetchall()
        conn.close()
        chores = []
        for row in rows:
            chore = self._map_chore(row)
            chores.append(
                {
                    "id": chore.id,
                    "title": chore.title,
                    "description": chore.description,
                    "due_date": chore.due_date,
                    "status": "Overdue" if chore.is_overdue() else chore.status,
                }
            )
        return chores

    def overdue_chores(self, chores: Iterable[Dict]):
        for chore in chores:
            due_date = chore.get("due_date")
            if not due_date or chore.get("status") == "Completed":
                continue
            if datetime.strptime(due_date, "%Y-%m-%d").date() < date.today():
                yield chore
