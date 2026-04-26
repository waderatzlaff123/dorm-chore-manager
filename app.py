from calendar import Calendar
from datetime import date, datetime, timedelta

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from auth import AuthError, authenticate_user, get_user_by_id, login_required, register_user
from database import init_db
from exceptions import ChoreError, RoomError
from services import ChoreService

app = Flask(__name__)
app.secret_key = "dev-secret-key"
service = ChoreService()

init_db()


def _format_user_role(role):
    return "Resident's Assistant" if role == "RA" else role


def _calendar_context(chore_list):
    requested_month = request.args.get("calendar_month")
    today = date.today()
    try:
        month_date = datetime.strptime(requested_month, "%Y-%m").date() if requested_month else today
        month_date = month_date.replace(day=1)
    except ValueError:
        month_date = today.replace(day=1)

    cal = Calendar(firstweekday=0)
    month_days = [day for week in cal.monthdatescalendar(month_date.year, month_date.month) for day in week]
    due_days = {
        int(chore["due_date"].split("-")[2])
        for chore in chore_list
        if chore.get("due_date")
        and datetime.strptime(chore["due_date"], "%Y-%m-%d").date().year == month_date.year
        and datetime.strptime(chore["due_date"], "%Y-%m-%d").date().month == month_date.month
    }

    prev_month = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)

    return {
        "calendar_label": month_date.strftime("%B %Y"),
        "calendar_cells": month_days,
        "calendar_due_days": due_days,
        "calendar_current_date": today,
        "calendar_month": month_date.month,
        "calendar_year": month_date.year,
        "calendar_prev": prev_month.strftime("%Y-%m"),
        "calendar_next": next_month.strftime("%Y-%m"),
        "calendar_weekdays": ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"],
    }


def _group_chores_by_date(chores):
    grouped = {}
    for chore in chores:
        due_date = chore.get("due_date")
        if due_date:
            grouped.setdefault(due_date, []).append(chore)
    return grouped


@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    g.current_user = get_user_by_id(user_id) if user_id else None


@app.context_processor
def inject_current_user():
    current_user = g.get("current_user")
    if current_user:
        if current_user["role"] == "RA":
            chore_list = service.get_chores(room_id=current_user["room_id"])
        else:
            chore_list = service.get_resident_chores(current_user["id"], room_id=current_user["room_id"])
        calendar_data = _calendar_context(chore_list)
    else:
        calendar_data = {}
    return {
        "current_user": current_user,
        "current_path": request.path,
        "current_user_role_text": _format_user_role(current_user["role"]) if current_user else None,
        **calendar_data,
    }


def _fetch_dashboard_context():
    room_id = g.current_user["room_id"]
    user_role = g.current_user["role"]
    residents = service.get_residents(room_id=room_id)
    if user_role == "RA":
        all_chores = service.get_chores(room_id=room_id)
    else:
        all_chores = service.get_resident_chores(g.current_user["id"], room_id=room_id)
    completed_count = sum(1 for chore in all_chores if chore.get("status") == "Completed")
    overdue_count = sum(1 for _ in service.overdue_chores(all_chores))
    progress = {}
    if user_role != "RA":
        total_tasks = len(all_chores)
        progress_count = completed_count
        progress_percentage = int((progress_count / total_tasks) * 100) if total_tasks else 0
        progress = {
            "progress_count": progress_count,
            "total_tasks": total_tasks,
            "progress_percentage": progress_percentage,
        }
    return {
        "room_id": room_id,
        "residents": residents,
        "all_chores": all_chores,
        "overdue_count": overdue_count,
        "completed_count": completed_count,
        "user_role": user_role,
        **progress,
    }


@app.route("/")
def home():
    if g.current_user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        user = authenticate_user(email, password)
        if not user:
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.current_user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            user = register_user(
                request.form.get("name", ""),
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("role", ""),
                request.form.get("room_code", ""),
            )
            session["user_id"] = user["id"]
            flash("Account created. You are now connected to your room.", "success")
            if user["role"] == "RA":
                flash(f"Your room code is {user['room_code']}. Share it with residents.", "success")
            return redirect(url_for("dashboard"))
        except AuthError as error:
            flash(str(error), "error")
    return render_template("register.html")


@app.route("/dashboard")
@login_required
def dashboard():
    context = _fetch_dashboard_context()
    section = "assigned"
    return render_template(
        "dashboard.html",
        page_title="To Do",
        section=section,
        **context,
    )


@app.route("/tasks/assigned")
@login_required
def assigned_tasks():
    context = _fetch_dashboard_context()
    section = "assigned"
    page_title = "Assign Tasks" if g.current_user["role"] == "RA" else "To Do"
    return render_template(
        "dashboard.html",
        page_title=page_title,
        section=section,
        **context,
    )


@app.route("/tasks/completed")
@login_required
def completed_tasks():
    context = _fetch_dashboard_context()
    section = "completed"
    return render_template(
        "dashboard.html",
        page_title="Completed Tasks",
        section=section,
        **context,
    )


@app.route("/tasks/overdue")
@login_required
def overdue_tasks():
    context = _fetch_dashboard_context()
    section = "overdue"
    return render_template(
        "dashboard.html",
        page_title="Overdue Tasks",
        section=section,
        **context,
    )


@app.route("/residents")
@login_required
def residents():
    if g.current_user["role"] != "RA":
        flash("Only Resident's Assistants can view resident details.", "error")
        return redirect(url_for("dashboard"))
    context = _fetch_dashboard_context()
    return render_template(
        "residents.html",
        page_title="Residents",
        **context,
    )


@app.route("/calendar")
@login_required
def calendar_view():
    context = _fetch_dashboard_context()
    room_id = g.current_user["room_id"]
    if g.current_user["role"] == "RA":
        chore_list = service.get_chores(room_id=room_id)
    else:
        chore_list = service.get_resident_chores(g.current_user["id"], room_id=room_id)
    chores_by_day = _group_chores_by_date(chore_list)
    return render_template(
        "calendar.html",
        page_title="Calendar",
        chores=chore_list,
        chores_by_day=chores_by_day,
        **context,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    room_id = g.current_user["room_id"]
    room = service.get_room(room_id)
    if request.method == "POST":
        if g.current_user["role"] != "RA":
            flash("Only Resident's Assistants can update room settings.", "error")
            return redirect(url_for("settings"))
        new_name = request.form.get("room_name", "").strip()
        try:
            service.update_room_name(room_id, new_name)
            flash("Room name updated successfully.", "success")
            return redirect(url_for("settings"))
        except (ValueError, RoomError) as error:
            flash(str(error), "error")
    room = service.get_room(room_id)
    return render_template(
        "settings.html",
        page_title="Settings",
        room=room,
        user_role=g.current_user["role"],
    )


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/chores")
@login_required
def chores():
    return redirect(url_for("dashboard"))


@app.route("/chores/create", methods=["GET", "POST"])
@login_required
def create_chore():
    if g.current_user["role"] != "RA":
        flash("Only Resident's Assistants can create tasks.", "error")
        return redirect(url_for("dashboard"))

    residents = service.get_residents(room_id=g.current_user["room_id"])
    if request.method == "POST":
        try:
            resident_values = request.form.getlist("resident_ids")
            service.create_chore(
                title=request.form.get("title", ""),
                description=request.form.get("description", ""),
                due_date=request.form.get("due_date", ""),
                due_time=request.form.get("due_time", ""),
                resident_values=resident_values,
                assigned_by=g.current_user["id"],
                room_id=g.current_user["room_id"],
            )
            flash("Chore created successfully.", "success")
            return redirect(url_for("assigned_tasks"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("create_chore.html", residents=residents)


@app.route("/chores/<int:chore_id>/edit", methods=["GET", "POST"])
@login_required
def edit_chore(chore_id):
    if g.current_user["role"] != "RA":
        flash("Only Resident's Assistants can edit tasks.", "error")
        return redirect(url_for("dashboard"))

    residents = service.get_residents(room_id=g.current_user["room_id"])
    try:
        chore = service.get_chore(chore_id, room_id=g.current_user["room_id"])
    except ChoreError as error:
        flash(str(error), "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        try:
            resident_values = request.form.getlist("resident_ids")
            service.update_chore(
                chore_id=chore_id,
                title=request.form.get("title", ""),
                description=request.form.get("description", ""),
                due_date=request.form.get("due_date", ""),
                due_time=request.form.get("due_time", ""),
                resident_values=resident_values,
                room_id=g.current_user["room_id"],
                assigned_by=g.current_user["id"],
            )
            flash("Chore updated successfully.", "success")
            return redirect(url_for("assigned_tasks"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("edit_chore.html", chore=chore, residents=residents)


@app.route("/chores/<int:chore_id>/delete", methods=["POST"])
@login_required
def delete_chore(chore_id):
    if g.current_user["role"] != "RA":
        flash("Only Resident's Assistants can delete tasks.", "error")
        return redirect(url_for("dashboard"))
    try:
        service.delete_chore(chore_id, room_id=g.current_user["room_id"])
        flash("Chore deleted.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("assigned_tasks"))


@app.route("/chores/<int:chore_id>/complete", methods=["POST"])
@login_required
def complete_chore(chore_id):
    try:
        service.mark_complete(chore_id, room_id=g.current_user["room_id"])
        flash("Chore marked complete.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("assigned_tasks"))


@app.route("/resident/<int:resident_id>/chores")
@login_required
def resident_chores(resident_id):
    if g.current_user["role"] != "RA":
        flash("Only Resident's Assistants can access resident overviews.", "error")
        return redirect(url_for("dashboard"))
    chores_for_resident = service.get_resident_chores(resident_id, room_id=g.current_user["room_id"])
    residents = service.get_residents(room_id=g.current_user["room_id"])
    resident = next((r for r in residents if r["id"] == resident_id), None)
    return render_template(
        "resident_chores.html",
        chores=chores_for_resident,
        resident=resident,
        user_role=g.current_user["role"],
    )

if __name__ == "__main__":
    app.run(debug=True)