from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass
class User:
    id: int
    name: str
    role: str


@dataclass
class Resident(User):
    room_number: Optional[str] = None


@dataclass
class RA(User):
    floor: Optional[str] = None

@dataclass
class Chore:
    id: int
    title: str
    description: str
    due_date: Optional[str]
    status: str = "Pending"

    def mark_complete(self):
        self.status = "Completed"

    def is_overdue(self):
        if not self.due_date or self.status == "Completed":
            return False
        due = datetime.strptime(self.due_date, "%Y-%m-%d").date()
        return due < date.today()