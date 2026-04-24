class ChoreError(Exception):
    """Base exception for chore-related issues."""


class InvalidChoreError(ChoreError):
    """Raised when chore input data is invalid."""


class ChoreNotFoundError(ChoreError):
    """Raised when a chore cannot be found."""


class RoomError(ChoreError):
    """Raised when room settings cannot be updated."""
