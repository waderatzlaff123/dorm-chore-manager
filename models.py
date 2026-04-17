from dataclasses import dataclass
from datetime import datetime

@dataclass
class Chore:
    id: int
    title: str
    description: str
    due_date: str
    status: str = "Pending"

    def mark_complete(self):
        self.status = "Completed"

    def is_overdue(self):
        return datetime.strptime(self.due_date, "%Y-%m-%d") < datetime.now()