from flask import Flask, flash, redirect, render_template, request, url_for

from database import init_db
from exceptions import ChoreError
from services import ChoreService

app = Flask(__name__)
app.secret_key = "dev-secret-key"
service = ChoreService()

init_db()


@app.route("/")
def home():
    return redirect(url_for("chores"))


@app.route("/chores")
def chores():
    chore_list = service.get_chores()
    residents = service.get_residents()
    overdue_count = sum(1 for _ in service.overdue_chores(chore_list))
    return render_template(
        "dashboard.html",
        chores=chore_list,
        residents=residents,
        overdue_count=overdue_count,
    )


@app.route("/chores/create", methods=["GET", "POST"])
def create_chore():
    residents = service.get_residents()
    if request.method == "POST":
        try:
            resident_id = request.form.get("resident_id")
            service.create_chore(
                title=request.form.get("title", ""),
                description=request.form.get("description", ""),
                due_date=request.form.get("due_date", ""),
                resident_id=int(resident_id) if resident_id else None,
                assigned_by=1,
            )
            flash("Chore created successfully.", "success")
            return redirect(url_for("chores"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("create_chore.html", residents=residents)


@app.route("/chores/<int:chore_id>/edit", methods=["GET", "POST"])
def edit_chore(chore_id):
    residents = service.get_residents()
    try:
        chore = service.get_chore(chore_id)
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
            )
            flash("Chore updated successfully.", "success")
            return redirect(url_for("chores"))
        except ChoreError as error:
            flash(str(error), "error")
    return render_template("edit_chore.html", chore=chore, residents=residents)


@app.route("/chores/<int:chore_id>/delete", methods=["POST"])
def delete_chore(chore_id):
    try:
        service.delete_chore(chore_id)
        flash("Chore deleted.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("chores"))


@app.route("/chores/<int:chore_id>/complete", methods=["POST"])
def complete_chore(chore_id):
    try:
        service.mark_complete(chore_id)
        flash("Chore marked complete.", "success")
    except ChoreError as error:
        flash(str(error), "error")
    return redirect(url_for("chores"))


@app.route("/resident/<int:resident_id>/chores")
def resident_chores(resident_id):
    chores_for_resident = service.get_resident_chores(resident_id)
    residents = service.get_residents()
    resident = next((r for r in residents if r["id"] == resident_id), None)
    return render_template(
        "resident_chores.html",
        chores=chores_for_resident,
        resident=resident,
    )

if __name__ == "__main__":
    app.run(debug=True)