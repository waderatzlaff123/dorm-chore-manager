# Dorm Chore Manager

Dorm Chore Manager is a Flask web app for a college dorm where Resident Assistants (RAs) can manage chores and residents can complete assigned tasks.

## Problem Statement

Dorm chores are often tracked informally, which causes missed deadlines and unclear ownership. This project provides a simple, web-based tracker with assignment, due dates, and status visibility.

## Features

- Full chore CRUD (create, read, update, delete)
- Assign chores to residents
- Mark chores complete
- Overdue chore highlighting
- RA dashboard and resident-specific view
- Form validation with friendly error messages

## Tech Stack

- Python
- Flask
- SQLite
- HTML/CSS templates
- pytest
- GitHub Actions

## Installation

1. Create a virtual environment:
   - Windows: `python -m venv .venv`
   - Activate: `.venv\Scripts\activate`
2. Install dependencies:
   - `pip install -r requirements.txt`

## Run the App

`python app.py`

Then open: `http://127.0.0.1:5000/chores`

## Run Tests

`pytest`

## Project Structure

- `app.py` - Flask routes and page handlers
- `database.py` - SQLite connection and table initialization
- `models.py` - OOP data models (User, RA, Resident, Chore)
- `services.py` - business logic for chore operations
- `exceptions.py` - custom exception classes
- `templates/` - Jinja2 page templates
- `static/style.css` - app styling
- `tests/` - pytest test suite
- `.github/workflows/python-ci.yml` - CI workflow

## Advanced Python Concepts Used

- **Dataclasses**: used for `User`, `Resident`, `RA`, and `Chore`
- **Custom exceptions**: `InvalidChoreError` and `ChoreNotFoundError`
- **Decorator**: `validate_chore_title` to enforce valid chore input
- **Generator**: `overdue_chores()` yields overdue chores from a list

## Notes for Demo/Presentation

- Show RA workflow: create, assign, edit, delete, complete
- Show resident workflow: open resident-specific page and complete task
- Highlight overdue badge behavior and error handling
