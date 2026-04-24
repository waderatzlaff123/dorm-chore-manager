from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from auth import AuthError, authenticate_user, get_user_by_id, login_required, register_user
from database import init_db
from exceptions import ChoreError
from services import ChoreService

app = Flask(__name__)
app.secret_key = "dev-secret-key"
service = ChoreService()

init_db()


@app.before_request
def load_current_user():
    user_id = session.get("user_id")
    g.current_user = get_user_by_id(user_id) if user_id else None


@app.context_processor
def inject_current_user():
    return {"current_user": g.get("current_user")}


@app.route("/")
def home():
    if g.current_user:
        return redirect(url_for("chores"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.current_user:
        return redirect(url_for("chores"))
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        user = authenticate_user(email, password)
        if not user:
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("chores"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.current_user:
        return redirect(url_for("chores"))
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
            return redirect(url_for("chores"))
        except AuthError as error:
            flash(str(error), "error")
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/chores")
@login_required
def chores():
    room_id = g.current_user["room_id"]
    residents = service.get_residents(room_id=room_id)
    if g.current_user["role"] == "RA":
        chore_list = service.get_chores(room_id=room_id)
    else:
        chore_list = service.get_resident_chores(g.current_user["id"], room_id=room_id)
    overdue_count = sum(1 for _ in service.overdue_chores(chore_list))
    return render_template(
        "dashboard.html",
        chores=chore_list,
        residents=residents,
        overdue_count=overdue_count,
        user_role=g.current_user["role"],
    )


@app.route("/chores/create", methods=["GET", "POST"])
@login_required
def create_chore():
    if g.current_user["role"] != "RA":
        flash("Only RAs can create tasks.", "error")
        return redirect(url_for("chores"))

    residents = service.get_residents(room_id=g.current_user["room_id"])
    if request.method == "POST":
        try:
            resident_id = request.form.get("resident_id")
            service.create_chore(
                title=request.form.get("title", ""),
                description=request.form.get("description", ""),
                due_date=request.form.get("due_date", ""),
                resident_id=int(resident_id) if resident_id else None,
                assigned_by=g.current_user["id"],
                room_id=g.current_user["room_id"],
            )
            flash("Chore created successfully.", "success")
            return redirect(url_for("chores"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("create_chore.html", residents=residents)


@app.route("/chores/<int:chore_id>/edit", methods=["GET", "POST"])
@login_required
def edit_chore(chore_id):
    if g.current_user["role"] != "RA":
        flash("Only RAs can edit tasks.", "error")
        return redirect(url_for("chores"))

    residents = service.get_residents(room_id=g.current_user["room_id"])
    try:
        chore = service.get_chore(chore_id, room_id=g.current_user["room_id"])
    except ChoreError as error:
        flash(str(error), "error")
        return redirect(url_for("chores"))

    if request.method == "POST":
        try:
            resident_id = request.form.get("resident_id")
            service.update_chore(
                chore_id=chore_id,
                title=request.form.get("title", ""),
                description=request.form.get("description", ""),
                due_date=request.form.get("due_date", ""),
                resident_id=int(resident_id) if resident_id else None,
                room_id=g.current_user["room_id"],
                assigned_by=g.current_user["id"],
            )
            flash("Chore updated successfully.", "success")
            return redirect(url_for("chores"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("edit_chore.html", chore=chore, residents=residents)


@app.route("/chores/<int:chore_id>/delete", methods=["POST"])
@login_required
def delete_chore(chore_id):
    if g.current_user["role"] != "RA":
        flash("Only RAs can delete tasks.", "error")
        return redirect(url_for("chores"))
    try:
        service.delete_chore(chore_id, room_id=g.current_user["room_id"])
        flash("Chore deleted.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("chores"))


@app.route("/chores/<int:chore_id>/complete", methods=["POST"])
@login_required
def complete_chore(chore_id):
    try:
        service.mark_complete(chore_id, room_id=g.current_user["room_id"])
        flash("Chore marked complete.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("chores"))


@app.route("/resident/<int:resident_id>/chores")
@login_required
def resident_chores(resident_id):
    if g.current_user["role"] != "RA":
        flash("Only RAs can access resident overviews.", "error")
        return redirect(url_for("chores"))
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