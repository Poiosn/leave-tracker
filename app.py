# app.py
import os
import json
import random
import calendar
from datetime import datetime, date, timedelta
from collections import OrderedDict

from flask import Flask, request, redirect, session, render_template_string, url_for
from flask_sqlalchemy import SQLAlchemy

# -------------------- Config --------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret123")  # change in production
DATABASE_URL = os.getenv("DATABASE_URL")  # Render environment variable
if not DATABASE_URL:
    # fallback to local sqlite for local dev if DATABASE_URL not provided
    DATABASE_URL = "sqlite:///local_db.sqlite3"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# simple fixed password login (Option A)
PASSWORD = "1234"

# local JSON filenames (used only for initial import if present)
LEAVE_FILE = "leaves.json"
EMP_FILE = "employees.json"


# -------------------- Models --------------------
class EmployeeColor(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    color = db.Column(db.String(80), nullable=True)


class Leave(db.Model):
    __tablename__ = "leaves"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(500), nullable=True)
    half_day = db.Column(db.Boolean, nullable=False, default=False)


# -------------------- Helpers --------------------
def generate_color():
    """Return a light pastel rgba color with slight transparency."""
    r = random.randint(120, 230)
    g = random.randint(120, 230)
    b = random.randint(120, 230)
    return f"rgba({r},{g},{b},0.45)"


def get_color_for_employee(name):
    """Get or create saved color for employee (DB-backed)."""
    if not name:
        return "rgba(200,200,200,0.35)"
    emp = EmployeeColor.query.filter_by(name=name).first()
    if emp:
        return emp.color
    color = generate_color()
    emp = EmployeeColor(name=name, color=color)
    db.session.add(emp)
    db.session.commit()
    return color


def build_calendar(year, month, leaves):
    """Return weeks matrix for the month with leave names per day (list)."""
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    leave_map = {}
    for lv in leaves:
        iso = lv.date.isoformat()
        label = lv.name + (" (Half)" if lv.half_day else "")
        leave_map.setdefault(iso, []).append(label)

    out = []
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append({"day": 0, "names": []})
            else:
                iso = date(year, month, day).isoformat()
                row.append({"day": day, "names": leave_map.get(iso, [])})
        out.append(row)
    return out


def import_json_to_db():
    """
    If the DB is empty (no leaves), try to import from local JSON files.
    This helps preserve your existing data when switching from json -> db.
    """
    # Only import if tables are empty
    leaves_count = Leave.query.count()
    if leaves_count > 0:
        return

    # Import employees first
    if os.path.exists(EMP_FILE):
        try:
            with open(EMP_FILE, "r") as f:
                emps = json.load(f)
            for name, color in emps.items():
                if not EmployeeColor.query.filter_by(name=name).first():
                    db.session.add(EmployeeColor(name=name, color=color))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Import leaves
    if os.path.exists(LEAVE_FILE):
        try:
            with open(LEAVE_FILE, "r") as f:
                leaves = json.load(f)
            for lv in leaves:
                # expect fields: id, name, date (iso), note, half_day
                try:
                    d = datetime.fromisoformat(lv["date"]).date()
                except Exception:
                    continue
                # avoid duplicates by checking identical record (name+date+note)
                exists = Leave.query.filter_by(name=lv["name"], date=d, note=lv.get("note", "")).first()
                if not exists:
                    leave = Leave(
                        name=lv["name"],
                        date=d,
                        note=lv.get("note", ""),
                        half_day=bool(lv.get("half_day", False))
                    )
                    db.session.add(leave)
            db.session.commit()
        except Exception:
            db.session.rollback()


# -------------------- Auth decorator --------------------
def require_auth(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*a, **k):
        if not session.get("authed"):
            return redirect("/")
        return func(*a, **k)

    return wrapper


# -------------------- Routes --------------------
@app.route("/", methods=["GET", "POST"])
def login():
    html = """
    <html><head>
    <style>
        body { background:#dde7ff; padding:40px; font-family:Arial; }
        .card {
            width:350px; margin:auto; padding:30px;
            background:rgba(255,255,255,0.5);
            backdrop-filter:blur(8px);
            border-radius:16px;
            box-shadow:0 8px 30px rgba(0,0,0,0.15);
            text-align:center;
        }
        input,button {
            width:100%; padding:12px; margin-top:12px;
            border-radius:8px; border:1px solid #ccc;
            font-size:15px;
        }
        button { background:#2563eb; color:white; font-weight:600; }
    </style>
    </head>
    <body>
        <div class="card">
            <h2>Leave Tracker Login</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Enter password" autocomplete="off">
                <button>Login</button>
            </form>
            <p style="color:red">{{msg}}</p>
        </div>
    </body></html>
    """
    msg = ""
    if request.method == "POST":
        if request.form.get("password", "") == PASSWORD:
            session["authed"] = True
            return redirect("/dashboard")
        msg = "Incorrect password"
    return render_template_string(html, msg=msg)


@app.route("/dashboard")
@require_auth
def dashboard():
    # fetch employees & leaves
    employees = [e.name for e in EmployeeColor.query.order_by(EmployeeColor.name).all()]
    leaves = Leave.query.order_by(Leave.date).all()

    year = int(request.args.get("year", datetime.today().year))
    month = int(request.args.get("month", datetime.today().month))

    # only leaves in this month for the calendar
    month_leaves = [l for l in leaves if l.date.year == year and l.date.month == month]
    weeks = build_calendar(year, month, month_leaves)

    # group leaves date-wise preserving order
    grouped = OrderedDict()
    for lv in leaves:
        key = lv.date.isoformat()
        grouped.setdefault(key, []).append(lv)

    # Render the same enhanced UI (single file)
    html = """<!DOCTYPE html>
<html>
<head>
<title>Leave Dashboard</title>
<style>
body { background:#e3eaff; margin:0; font-family:'Segoe UI', Arial; }

.topbar {
    background:#2d4cd3;   
    padding:22px;
    text-align:center;
    color:white;
    font-size:26px;
    font-weight:700;
    letter-spacing:1px;
    position:relative;
    box-shadow:0 3px 15px rgba(0,0,0,0.2);
}

.logout-btn {
    position:absolute;
    right:25px;
    top:18px;
    background:white;
    color:#2d4cd3;
    padding:8px 18px;
    font-weight:600;
    border-radius:25px;
    border:none;
    cursor:pointer;
    transition:0.25s;
    box-shadow:0 2px 8px rgba(0,0,0,0.2);
}
.logout-btn:hover {
    background:#eef2ff;
    transform:scale(1.07);
}

.container { width:90%; max-width:1300px; margin:30px auto; }

.card {
    background:rgba(255,255,255,0.65);
    backdrop-filter:blur(12px);
    padding:25px; margin-top:25px;
    border-radius:20px;
    box-shadow:0 8px 25px rgba(0,0,0,0.15);
}

/* Calendar */
.calendar-card {
    background:rgba(255,255,255,0.7);
    padding:25px;
    border-radius:20px;
    box-shadow:0 8px 25px rgba(0,0,0,0.1);
}

table { width:100%; border-collapse:separate; border-spacing:0; }
th {
    background:#b9ccff;
    padding:12px; border-radius:12px 12px 0 0;
}
td {
    background:rgba(255,255,255,0.9);
    height:110px; padding:10px;
    border:1px solid #e5e7eb;
    border-radius:14px; cursor:pointer;
    transition:0.2s;
    text-align:center;
    vertical-align:top;
}
td:hover {
    background:#e8ecff;
    transform:scale(1.03);
}

.leave-tag {
    padding:3px 6px;
    margin-top:4px;
    border-radius:8px; font-size:12px;
    display:inline-block;
}

/* Date Block */
.date-block {
    background:rgba(255,255,255,0.55);
    padding:20px;
    border-radius:16px;
    margin-bottom:25px;
    box-shadow:0 4px 18px rgba(0,0,0,0.12);
}

.date-title {
    font-size:20px; font-weight:700;
    margin-bottom:15px; display:flex; align-items:center;
}
.date-title span {
    font-size:24px; margin-right:8px; color:#2563eb;
}

.leave-row {
    display:flex; align-items:center; justify-content:space-between;
    background:rgba(255,255,255,0.9);
    padding:12px 14px;
    margin-bottom:10px;
    border-radius:12px;
    box-shadow:0 2px 10px rgba(0,0,0,0.08);
}

.leave-info-line { margin-left:10px; font-size:16px; flex-grow:1; }

.leave-dot { width:16px; height:16px; border-radius:50%; display:inline-block; }

.delete-btn-small {
    background:#ef4444; color:white;
    padding:6px 12px; border:none;
    border-radius:6px; cursor:pointer;
    font-weight:600;
    transition:0.2s;
}
.delete-btn-small:hover {
    transform:scale(1.05);
}

/* MODAL */
.modal-bg {
    position:fixed; top:0; left:0;
    width:100%; height:100%; display:none;
    background:rgba(0,0,0,0.45);
    justify-content:center; align-items:center;
    backdrop-filter:blur(4px);
}

.modal {
    background:rgba(255,255,255,0.97);
    padding:25px 30px; width:360px;
    border-radius:22px;
    box-shadow:0 8px 25px rgba(0,0,0,0.25);
}

.input-box {
    width:100%; padding:12px;
    border-radius:10px; border:1px solid #d1d5db;
    margin-top:8px;
}

.modal-btn {
    width:100%; padding:12px;
    border:none; border-radius:10px;
    background:#2563eb; color:white;
    margin-top:18px; font-weight:600;
}

.modal-close-btn {
    width:100%; padding:10px; margin-top:10px;
    border:none; border-radius:10px;
    background:#e5e7eb; font-weight:600;
}
</style>

<script>
function openModal(day){
    let y={{year}}, m={{month}};
    let dateStr = y + "-" + String(m).padStart(2,'0') + "-" + String(day).padStart(2,'0');
    document.getElementById("from_date").value = dateStr;
    document.getElementById("to_date").value = dateStr;
    document.getElementById("displayDate").innerText = dateStr;
    document.getElementById("modal").style.display = "flex";
}

function closeModal(){
    document.getElementById("modal").style.display = "none";
}

function checkRange(){
    let f = document.getElementById("from_date").value;
    let t = document.getElementById("to_date").value;
    document.getElementById("half_row").style.display = (f===t) ? "block" : "none";
}
</script>
</head>

<body>

<div class="topbar">
    Leave Dashboard
    <form action="{{ url_for('logout') }}" method="GET" style="display:inline;">
        <button class="logout-btn">Logout</button>
    </form>
</div>

<div class="container">

    <!-- Calendar -->
    <div class="calendar-card">
        <form method="GET">
            Year: <input name="year" value="{{year}}" style="width:80px;">
            Month: <input name="month" value="{{month}}" style="width:80px;">
            <button>Go</button>
        </form>

        <table>
            <tr>
                <th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th>
                <th>Fri</th><th>Sat</th><th>Sun</th>
            </tr>

            {% for week in weeks %}
            <tr>
                {% for d in week %}
                    {% if d.day == 0 %}
                        <td></td>
                    {% else %}
                        <td onclick="openModal({{d.day}})">
                            <b style="font-size:18px;">{{d.day}}</b><br>
                            {% for nm in d.names %}
                                <span class="leave-tag"
                                    style="background:{{ get_color_for_employee(nm.split()[0]) }}">
                                    {{ nm }}
                                </span>
                            {% endfor %}
                        </td>
                    {% endif %}
                {% endfor %}
            </tr>
            {% endfor %}
        </table>
    </div>

    <!-- Day-wise Leaves -->
    <div class="card">
        <h3 style="margin-top:0;">All Leaves (Day Wise)</h3>

        {% for d, items in grouped.items() %}
        <div class="date-block">
            <div class="date-title"><span>📅</span> {{ d }}</div>

            {% for lv in items %}
            <div class="leave-row">
                <span class="leave-dot" style="background:{{ get_color_for_employee(lv.name) }}"></span>

                <div class="leave-info-line">
                    <b>{{ lv.name }}</b>
                    {% if lv.half_day %}(Half Day){% endif %}
                    {% if lv.note %} – {{ lv.note }}{% endif %}
                </div>

                <form method="POST" action="{{ url_for('delete', id=lv.id) }}">
                    <button class="delete-btn-small">Delete</button>
                </form>
            </div>
            {% endfor %}
        </div>
        {% endfor %}
    </div>

</div>

<!-- Modal -->
<div class="modal-bg" id="modal">
    <div class="modal">
        <h2>Add Leave</h2>
        <p>Date: <b id="displayDate"></b></p>

        <form method="POST" action="{{ url_for('add') }}">

            <label>From Date</label>
            <input id="from_date" name="from_date" type="date"
                   onchange="checkRange()" class="input-box">

            <label>To Date</label>
            <input id="to_date" name="to_date" type="date"
                   onchange="checkRange()" class="input-box">

            <label>Employee</label>
            <select name="name" class="input-box">
                <option value="">Select</option>
                {% for nm in employees %}
                    <option value="{{nm}}">{{nm}}</option>
                {% endfor %}
            </select>

            <label>Add New Employee</label>
            <input name="new_name" placeholder="New employee name" class="input-box">

            <div id="half_row">
                <label>Leave Type</label>
                <select name="half_day" class="input-box">
                    <option value="no">Full Day</option>
                    <option value="yes">Half Day</option>
                </select>
            </div>

            <label>Note</label>
            <input name="note" placeholder="Reason/Note" class="input-box">

            <button class="modal-btn">Add Leave</button>

        </form>

        <button onclick="closeModal()" class="modal-close-btn">Close</button>
    </div>
</div>

</body>
</html>
"""
    return render_template_string(
        html,
        weeks=weeks,
        year=year,
        month=month,
        employees=employees,
        grouped=grouped,
        get_color_for_employee=get_color_for_employee,
    )


@app.route("/add", methods=["POST"])
@require_auth
def add():
    name = request.form.get("name")
    new_name = (request.form.get("new_name") or "").strip()
    if new_name:
        name = new_name

    if not name:
        return redirect("/dashboard")

    note = request.form.get("note", "")
    try:
        start = datetime.strptime(request.form["from_date"], "%Y-%m-%d").date()
        end = datetime.strptime(request.form["to_date"], "%Y-%m-%d").date()
    except Exception:
        return redirect("/dashboard")

    half_flag = (request.form.get("half_day") == "yes" and start == end)

    days = (end - start).days + 1
    for i in range(days):
        d = start + timedelta(days=i)
        is_half = (half_flag and i == 0)
        leave = Leave(name=name, date=d, note=note, half_day=is_half)
        db.session.add(leave)

        # ensure employee color exists
        if not EmployeeColor.query.filter_by(name=name).first():
            db.session.add(EmployeeColor(name=name, color=generate_color()))

    db.session.commit()
    return redirect("/dashboard")


@app.route("/delete/<int:id>", methods=["POST"])
@require_auth
def delete(id):
    Leave.query.filter_by(id=id).delete()
    db.session.commit()
    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# -------------------- Startup: create tables & import JSON --------------------
with app.app_context():
    db.create_all()
    import_json_to_db()


# -------------------- Run (local dev) --------------------
if __name__ == "__main__":
    # local development
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
