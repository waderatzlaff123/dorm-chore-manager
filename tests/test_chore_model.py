from datetime import date, timedelta

import pytest

from exceptions import InvalidChoreError
from models import Chore
from services import ChoreService


def test_invalid_chore_title_raises_error():
    service = ChoreService()
    with pytest.raises(InvalidChoreError):
        service.create_chore("", "desc", "", None, 1)


def test_mark_complete_changes_status():
    chore = Chore(1, "Clean kitchen", "Sweep and mop", None, "Pending")
    chore.mark_complete()
    assert chore.status == "Completed"


def test_overdue_detection_works():
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    chore = Chore(1, "Trash", "Take out trash", yesterday, "Pending")
    assert chore.is_overdue() is True
