import json
import os
from flask import Flask, request, redirect, session, render_template_string
from datetime import datetime, date, timedelta
import calendar
import random

app = Flask(__name__)
app.secret_key = "secret123"

PASSWORD = "1234"

LEAVE_FILE = "leaves.json"
EMP_FILE = "employees.json"


# ------------------------ JSON Helpers ------------------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


# ------------------------ Employee Colors ------------------------
def load_employees():
    return load_json(EMP_FILE, {})

def save_employees(data):
    save_json(EMP_FILE, data)

def generate_color():
    r = random.randint(120, 230)
    g = random.randint(120, 230)
    b = random.randint(120, 230)
    return f"rgba({r},{g},{b},0.45)"

def get_color_for_employee(name):
    employees = load_employees()
    if name not in employees:
        employees[name] = generate_color()
        save_employees(employees)
    return employees[name]


# ------------------------ Auth ------------------------
def require_auth(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*a, **k):
        if not session.get("authed"):
            return redirect("/")
        return func(*a, **k)
    return wrapper


# ------------------------ Calendar Logic ------------------------
def build_calendar(year, month, leaves):
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    leave_map = {}
    for lv in leaves:
        leave_map.setdefault(lv["date"], []).append(
            lv["name"] + (" (Half)" if lv["half_day"] else "")
        )

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



# ------------------------ Login Page ------------------------
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
                <input type="password" name="password" placeholder="Enter password">
                <button>Login</button>
            </form>
            <p style="color:red">{{msg}}</p>
        </div>
    </body></html>
    """
    msg = ""
    if request.method == "POST":
        if request.form["password"] == PASSWORD:
            session["authed"] = True
            return redirect("/dashboard")
        msg = "Incorrect password"
    return render_template_string(html, msg=msg)



# ------------------------ Dashboard Page ------------------------
@app.route("/dashboard")
@require_auth
def dashboard():

    leaves = load_json(LEAVE_FILE, [])
    employees = load_employees()

    year = int(request.args.get("year", datetime.today().year))
    month = int(request.args.get("month", datetime.today().month))

    month_leaves = [l for l in leaves if l["date"].startswith(f"{year}-{month:02d}")]
    weeks = build_calendar(year, month, month_leaves)

    sorted_leaves = sorted(leaves, key=lambda x: x["date"])

    grouped = {}
    for lv in sorted_leaves:
        grouped.setdefault(lv["date"], []).append(lv)

    html = """
<!DOCTYPE html>
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
    transform:scale(1.1);
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
    <form action="/logout" method="GET" style="display:inline;">
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

                <form method="POST" action="/delete/{{ lv.id }}">
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

        <form method="POST" action="/add">

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
        get_color_for_employee=get_color_for_employee
    )



# ------------------------ Add Leave ------------------------
@app.route("/add", methods=["POST"])
@require_auth
def add():
    leaves = load_json(LEAVE_FILE, [])
    employees = load_employees()

    name = request.form.get("name")
    new_name = request.form.get("new_name", "").strip()

    if new_name:
        name = new_name
        if name not in employees:
            employees[name] = generate_color()
            save_employees(employees)

    if not name:
        return redirect("/dashboard")

    note = request.form.get("note", "")

    start = datetime.strptime(request.form["from_date"], "%Y-%m-%d").date()
    end   = datetime.strptime(request.form["to_date"], "%Y-%m-%d").date()

    half = (request.form.get("half_day") == "yes" and start == end)

    next_id = max([l["id"] for l in leaves], default=0) + 1
    days = (end - start).days + 1

    for i in range(days):
        d = start + timedelta(days=i)
        leaves.append({
            "id": next_id,
            "name": name,
            "date": d.isoformat(),
            "note": note,
            "half_day": (half and i == 0)
        })
        next_id += 1

    save_json(LEAVE_FILE, leaves)
    return redirect("/dashboard")



# ------------------------ Delete ------------------------
@app.route("/delete/<int:id>", methods=["POST"])
@require_auth
def delete(id):
    leaves = load_json(LEAVE_FILE, [])
    leaves = [lv for lv in leaves if lv["id"] != id]
    save_json(LEAVE_FILE, leaves)
    return redirect("/dashboard")



# ------------------------ Logout ------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")



# ------------------------ Run ------------------------
if __name__ == "__main__":
    app.run(debug=True)
