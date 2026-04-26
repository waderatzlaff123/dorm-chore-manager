from datetime import date, datetime
from functools import wraps
from typing import Dict, Iterable, List, Optional, Sequence

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
        if not due_date or not due_date.strip():
            raise InvalidChoreError("Due date is required.")
        try:
            return datetime.strptime(due_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise InvalidChoreError("Due date must be in YYYY-MM-DD format.") from exc

    @staticmethod
    def _validate_due_time(due_time: str) -> Optional[str]:
        if not due_time or not due_time.strip():
            return None
        try:
            parsed = datetime.strptime(due_time.strip(), "%H:%M").time()
            return parsed.strftime("%H:%M")
        except ValueError as exc:
            raise InvalidChoreError("Due time must be in HH:MM format.") from exc

    @staticmethod
    def _format_due_label(due_date: Optional[str], due_time: Optional[str]) -> str:
        if not due_date:
            return "No due date"
        parsed_date = datetime.strptime(due_date, "%Y-%m-%d").strftime("%B %d, %Y")
        if due_time:
            parsed_time = datetime.strptime(due_time, "%H:%M").strftime("%I:%M %p").lstrip("0")
            return f"Due: {parsed_date} at {parsed_time}"
        return f"Due: {parsed_date}"

    @staticmethod
    def _parse_assignment_ids(values: Sequence[str]) -> List[int]:
        unique_ids = set()
        for value in values:
            if not value or value.lower() == "all":
                continue
            try:
                unique_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        return sorted(unique_ids)

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

    def _resolve_resident_assignments(self, resident_values: Sequence[str], room_id: int) -> List[int]:
        if not resident_values:
            raise InvalidChoreError("A task must be assigned to at least one resident.")

        if any(value.lower() == "all" for value in resident_values if value):
            conn = get_db_connection()
            rows = conn.execute(
                "SELECT id FROM users WHERE role = 'Resident' AND room_id = ?",
                (room_id,),
            ).fetchall()
            conn.close()
            resident_ids = [row["id"] for row in rows]
            if not resident_ids:
                raise InvalidChoreError("No residents are available to assign this task.")
            return resident_ids

        resident_ids = self._parse_assignment_ids(resident_values)
        if not resident_ids:
            raise InvalidChoreError("A task must be assigned to at least one resident.")

        conn = get_db_connection()
        placeholders = ",".join("?" for _ in resident_ids)
        rows = conn.execute(
            f"SELECT id FROM users WHERE role = 'Resident' AND room_id = ? AND id IN ({placeholders})",
            tuple([room_id] + resident_ids),
        ).fetchall()
        conn.close()

        valid_ids = {row["id"] for row in rows}
        missing = set(resident_ids) - valid_ids
        if missing:
            raise InvalidChoreError("One or more selected residents are invalid.")
        return sorted(valid_ids)

    def _build_chore_record(self, row) -> Dict:
        chore = self._map_chore(row)
        assigned_names = row["assigned_names"] or ""
        if assigned_names:
            assigned_names = ", ".join({name.strip() for name in assigned_names.split(",") if name.strip()})
        display_due = self._format_due_label(row["due_date"], row["due_time"])
        status = "Overdue" if chore.is_overdue() else chore.status
        return {
            "id": chore.id,
            "title": chore.title,
            "description": chore.description,
            "due_date": chore.due_date,
            "due_time": row["due_time"],
            "display_due": display_due,
            "status": status,
            "assigned_names": assigned_names if assigned_names else None,
            "assigned_resident_ids": [int(i) for i in row["assigned_resident_ids"].split(",") if i] if row["assigned_resident_ids"] else [],
            "room_id": row["room_id"],
        }

    def get_chores(self, room_id: Optional[int] = None) -> List[Dict]:
        conn = get_db_connection()
        if room_id:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT u.name) AS assigned_names,
                       GROUP_CONCAT(DISTINCT a.resident_id) AS assigned_resident_ids
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                LEFT JOIN users u ON a.resident_id = u.id
                WHERE c.room_id = ?
                GROUP BY c.id
                ORDER BY c.id DESC
                """,
                (room_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT u.name) AS assigned_names,
                       GROUP_CONCAT(DISTINCT a.resident_id) AS assigned_resident_ids
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                LEFT JOIN users u ON a.resident_id = u.id
                GROUP BY c.id
                ORDER BY c.id DESC
                """
            ).fetchall()
        conn.close()

        return [self._build_chore_record(row) for row in rows]

    def get_chore(self, chore_id: int, room_id: Optional[int] = None) -> Dict:
        conn = get_db_connection()
        if room_id:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT a.resident_id) AS assigned_resident_ids
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                WHERE c.id = ? AND c.room_id = ?
                GROUP BY c.id
                """,
                (chore_id, room_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT a.resident_id) AS assigned_resident_ids
                FROM chores c
                LEFT JOIN assignments a ON c.id = a.chore_id
                WHERE c.id = ?
                GROUP BY c.id
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
            "due_time": row["due_time"] or "",
            "status": row["status"],
            "resident_ids": [int(i) for i in row["assigned_resident_ids"].split(",") if i] if row["assigned_resident_ids"] else [],
            "room_id": row["room_id"],
        }

    @validate_chore_title
    def create_chore(
        self,
        title: str,
        description: str,
        due_date: str,
        due_time: str,
        resident_values: Sequence[str],
        assigned_by: int,
        room_id: int = 1,
    ) -> int:
        clean_due_date = self._validate_due_date(due_date)
        clean_due_time = self._validate_due_time(due_time)
        resident_ids = self._resolve_resident_assignments(resident_values, room_id)

        conn = get_db_connection()
        cursor = conn.execute(
            """
            INSERT INTO chores (title, description, due_date, due_time, status, room_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title.strip(), description.strip(), clean_due_date, clean_due_time, "Pending", room_id, assigned_by),
        )
        chore_id = cursor.lastrowid

        if chore_id is None:
            conn.close()
            raise ChoreError("Failed to create chore.")

        assignment_rows = [
            (chore_id, resident_id, assigned_by, room_id) for resident_id in sorted(set(resident_ids))
        ]
        conn.executemany(
            """
            INSERT INTO assignments (chore_id, resident_id, assigned_by, room_id)
            VALUES (?, ?, ?, ?)
            """,
            assignment_rows,
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
        due_time: str,
        resident_values: Sequence[str],
        room_id: int = 1,
        assigned_by: int = 1,
    ) -> None:
        clean_due_date = self._validate_due_date(due_date)
        clean_due_time = self._validate_due_time(due_time)
        resident_ids = self._resolve_resident_assignments(resident_values, room_id)
        self.get_chore(chore_id, room_id=room_id)

        conn = get_db_connection()
        conn.execute(
            """
            UPDATE chores
            SET title = ?, description = ?, due_date = ?, due_time = ?
            WHERE id = ? AND room_id = ?
            """,
            (title.strip(), description.strip(), clean_due_date, clean_due_time, chore_id, room_id),
        )

        conn.execute("DELETE FROM assignments WHERE chore_id = ?", (chore_id,))
        assignment_rows = [
            (chore_id, resident_id, assigned_by, room_id) for resident_id in sorted(set(resident_ids))
        ]
        conn.executemany(
            """
            INSERT INTO assignments (chore_id, resident_id, assigned_by, room_id)
            VALUES (?, ?, ?, ?)
            """,
            assignment_rows,
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
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT u.name) AS assigned_names
                FROM chores c
                JOIN assignments a ON c.id = a.chore_id
                JOIN users u ON a.resident_id = u.id
                WHERE a.resident_id = ? AND c.room_id = ?
                GROUP BY c.id
                ORDER BY c.id DESC
                """,
                (resident_id, room_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.description, c.due_date, c.due_time, c.status, c.room_id,
                       GROUP_CONCAT(DISTINCT u.name) AS assigned_names
                FROM chores c
                JOIN assignments a ON c.id = a.chore_id
                JOIN users u ON a.resident_id = u.id
                WHERE a.resident_id = ?
                GROUP BY c.id
                ORDER BY c.id DESC
                """,
                (resident_id,),
            ).fetchall()
        conn.close()
        chores = []
        for row in rows:
            chore = self._map_chore(row)
            display_due = self._format_due_label(row["due_date"], row["due_time"])
            chores.append(
                {
                    "id": chore.id,
                    "title": chore.title,
                    "description": chore.description,
                    "due_date": chore.due_date,
                    "due_time": row["due_time"],
                    "display_due": display_due,
                    "status": "Overdue" if chore.is_overdue() else chore.status,
                    "assigned_names": row["assigned_names"],
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
