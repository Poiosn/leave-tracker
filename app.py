# app.py
import os
import json
import random
import calendar
from datetime import datetime, date, timedelta
from collections import OrderedDict

from flask import Flask, request, redirect, session, render_template_string, url_for
from flask_sqlalchemy import SQLAlchemy

# -------------------- App Config --------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "secret123")  # change for production

# Use DATABASE_URL from environment (Render provides this)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = "sqlite:///local_db.sqlite3"

# Force SQLAlchemy to use psycopg3 instead of psycopg2
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

# simple static password login (Option A)
PASSWORD = "1234"

# filenames (used only for initial import if present)
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
    name = db.Column(db.String(200), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(500), nullable=True)
    half_day = db.Column(db.Boolean, nullable=False, default=False)


# -------------------- Helpers --------------------
def generate_color():
    """Generate a soft pastel rgba color."""
    r = random.randint(120, 230)
    g = random.randint(120, 230)
    b = random.randint(120, 230)
    return f"rgba({r},{g},{b},0.35)"


def get_color_for_employee(name):
    """Get saved color or create a new one for an employee."""
    if not name:
        return "rgba(200,200,200,0.25)"
    emp = EmployeeColor.query.filter_by(name=name).first()
    if emp:
        return emp.color
    color = generate_color()
    emp = EmployeeColor(name=name, color=color)
    db.session.add(emp)
    db.session.commit()
    return color


def build_calendar(year, month, leaves):
    """Return month grid: list of weeks, each week list of {day, names}."""
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    leave_map = {}
    for lv in leaves:
        iso = lv.date.isoformat()
        leave_map.setdefault(iso, []).append(lv.name + (" (Half)" if lv.half_day else ""))

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
    Import local JSON files (if present) into DB the first time (only if DB empty).
    This preserves your existing JSON data when migrating.
    """
    # Only import if no leaves exist
    if Leave.query.count() > 0:
        return

    # Import employees
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
                try:
                    d = datetime.fromisoformat(lv["date"]).date()
                except Exception:
                    continue
                exists = Leave.query.filter_by(name=lv["name"], date=d, note=lv.get("note", "")).first()
                if not exists:
                    leave = Leave(
                        name=lv["name"],
                        date=d,
                        note=lv.get("note", ""),
                        half_day=bool(lv.get("half_day", False)),
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
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Login — Leave Tracker</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
    :root{
      --accent:#3446f1;
      --card: rgba(255,255,255,0.85);
      --glass: rgba(255,255,255,0.12);
      --muted:#6b7280;
      --bg: linear-gradient(135deg,#eef2ff 0%, #f8fbff 100%);
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,system-ui,Arial;background:var(--bg);height:100vh;display:flex;align-items:center;justify-content:center}
    .wrap{width:420px;padding:36px;border-radius:16px;background:var(--card);box-shadow:0 10px 30px rgba(16,24,40,0.12);backdrop-filter:blur(6px);text-align:center}
    h1{margin:0 0 10px;font-size:22px;color:#0f172a}
    p.sub{color:var(--muted);margin:0 0 20px}
    input[type="password"]{width:100%;padding:12px;border-radius:10px;border:1px solid #e6edf8;font-size:14px}
    button{width:100%;padding:12px;background:var(--accent);color:white;border:none;border-radius:10px;margin-top:14px;font-weight:700;cursor:pointer;box-shadow:0 6px 18px rgba(52,70,241,0.18)}
    small.msg{display:block;margin-top:12px;color:#ef4444}
    footer{font-size:12px;color:var(--muted);margin-top:16px}
    </style>
    </head>
    <body>
     <div class="wrap">
       <h1>Leave Tracker</h1>
       <p class="sub">Simple team leave calendar — enter password to continue</p>
       <form method="POST">
         <input autocomplete="off" name="password" type="password" placeholder="Password">
         <button>Sign in</button>
       </form>
       <small class="msg">{{ msg }}</small>
       <footer>Built with ♥ — safe for small teams</footer>
     </div>
    </body>
    </html>
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
    employees = [e.name for e in EmployeeColor.query.order_by(EmployeeColor.name).all()]
    leaves = Leave.query.order_by(Leave.date).all()

    year = int(request.args.get("year", datetime.today().year))
    month = int(request.args.get("month", datetime.today().month))

    month_leaves = [l for l in leaves if l.date.year == year and l.date.month == month]
    weeks = build_calendar(year, month, month_leaves)

    grouped = OrderedDict()
    for lv in leaves:
        key = lv.date.isoformat()
        grouped.setdefault(key, []).append(lv)

    # Modernized dashboard UI
    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Leave Dashboard</title>
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <style>
      :root{
        --bg1: linear-gradient(135deg,#f6f9ff 0,#eef6ff 100%);
        --accent: #2b4bf0;
        --muted: #6b7280;
        --glass: rgba(255,255,255,0.7);
      }
      body{margin:0;font-family:Inter,system-ui,Arial;background:var(--bg1);color:#0f172a}
      .topbar{background:linear-gradient(90deg,#2b4bf0 0%, #4a6fff 120%);padding:20px 24px;display:flex;align-items:center;justify-content:center;position:relative;color:white;box-shadow:0 6px 24px rgba(43,75,240,0.18)}
      .title{font-size:22px;font-weight:800;letter-spacing:0.3px}
      .logout-btn{position:absolute;right:20px;top:12px;background:white;color:var(--accent);border:none;padding:8px 14px;border-radius:999px;font-weight:700;cursor:pointer;box-shadow:0 6px 18px rgba(43,75,240,0.18)}
      .container{max-width:1200px;margin:28px auto;padding:0 18px}
      .grid{display:grid;grid-template-columns:1fr 430px;gap:22px}
      .card{background:var(--glass);padding:18px;border-radius:14px;box-shadow:0 8px 30px rgba(2,6,23,0.06)}
      .calendar-table{width:100%;border-collapse:separate;border-spacing:8px 8px}
      .calendar-table th{padding:10px;color:var(--muted);font-weight:700;text-align:center}
      .calendar-table td{background:white;padding:12px;border-radius:10px;min-height:84px;text-align:center;vertical-align:top;cursor:pointer;transition:transform .13s,box-shadow .13s}
      .calendar-table td:hover{transform:translateY(-4px);box-shadow:0 10px 30px rgba(15,23,42,0.06)}
      .day-num{font-weight:800;font-size:18px;color:#0f172a;margin-bottom:8px}
      .tag{display:inline-block;padding:6px 8px;border-radius:999px;font-size:13px;margin:3px 3px;box-shadow:inset 0 -2px 0 rgba(0,0,0,0.02)}
      .side{max-height:720px;overflow:auto}
      .date-block{margin-bottom:14px;padding:12px;border-radius:12px;background:linear-gradient(180deg,rgba(255,255,255,0.96),rgba(250,250,252,0.98));box-shadow:0 6px 18px rgba(12,18,30,0.04)}
      .date-title{font-weight:800;margin-bottom:10px;display:flex;align-items:center;gap:8px}
      .leave-row{display:flex;align-items:center;justify-content:space-between;padding:10px;border-radius:10px;margin-bottom:8px}
      .leave-left{display:flex;align-items:center;gap:12px}
      .dot{width:14px;height:14px;border-radius:50%}
      .info{font-weight:700}
      .note{color:var(--muted);font-weight:500;font-size:13px;margin-left:6px}
      .del-btn{background:#ff5c5c;border:none;color:white;padding:8px 10px;border-radius:8px;cursor:pointer}
      .controls{display:flex;gap:8px;align-items:center;margin-bottom:12px}
      .input{padding:8px;border-radius:8px;border:1px solid #e9eefb}
      .modal{position:fixed;left:0;top:0;width:100%;height:100%;display:none;align-items:center;justify-content:center;background:rgba(2,6,23,0.42)}
      .modal-card{width:420px;background:white;padding:20px;border-radius:14px;box-shadow:0 18px 50px rgba(2,6,23,0.18)}
      .modal h3{margin:0 0 8px}
      .btn-primary{background:var(--accent);color:white;padding:10px 14px;border-radius:10px;border:none;cursor:pointer;font-weight:700}
      .muted{color:var(--muted)}
      @media(max-width:980px){.grid{grid-template-columns:1fr}}
      </style>
    </head>
    <body>
      <div class="topbar">
        <div class="title">Leave Dashboard</div>
        <form action="{{ url_for('logout') }}" method="GET" style="display:inline">
          <button class="logout-btn">Logout</button>
        </form>
      </div>

      <div class="container">
        <div class="grid">
          <div class="card">
            <div class="controls">
              <form method="GET" style="display:flex;gap:8px;align-items:center">
                <input class="input" name="year" value="{{ year }}" style="width:92px" />
                <input class="input" name="month" value="{{ month }}" style="width:92px" />
                <button class="btn-primary">Go</button>
              </form>
              <div style="margin-left:auto">
                <button class="btn-primary" onclick="openModal(null)">Add Leave</button>
              </div>
            </div>

            <table class="calendar-table">
              <tr>
                <th>Mon</th><th>Tue</th><th>Wed</th><th>Thu</th><th>Fri</th><th>Sat</th><th>Sun</th>
              </tr>
              {% for week in weeks %}
              <tr>
                {% for d in week %}
                  {% if d.day == 0 %}
                    <td></td>
                  {% else %}
                    <td onclick="openModal({{d.day}})">
                      <div class="day-num">{{ d.day }}</div>
                      {% for nm in d.names %}
                        <div class="tag" style="background:{{ get_color_for_employee(nm.split()[0]) }}">{{ nm }}</div>
                      {% endfor %}
                    </td>
                  {% endif %}
                {% endfor %}
              </tr>
              {% endfor %}
            </table>
          </div>

          <div class="card side">
            <h3 style="margin-top:0">All Leaves (by date)</h3>
            {% for d, items in grouped.items() %}
              <div class="date-block">
                <div class="date-title">📅 {{ d }}</div>
                {% for lv in items %}
                <div class="leave-row">
                  <div class="leave-left">
                    <div class="dot" style="background:{{ get_color_for_employee(lv.name) }}"></div>
                    <div>
                      <div class="info">{{ lv.name }} {% if lv.half_day %}<span class="muted">— Half</span>{% endif %}</div>
                      {% if lv.note %}<div class="note">{{ lv.note }}</div>{% endif %}
                    </div>
                  </div>
                  <form method="POST" action="{{ url_for('delete', id=lv.id) }}">
                    <button class="del-btn">Delete</button>
                  </form>
                </div>
                {% endfor %}
              </div>
            {% endfor %}
          </div>
        </div>
      </div>

      <!-- Modal -->
      <div id="modal" class="modal">
        <div class="modal-card">
          <h3>Add Leave</h3>
          <form method="POST" action="{{ url_for('add') }}">
            <label class="muted">From</label>
            <input id="from_date" name="from_date" class="input" type="date" required>

            <label class="muted">To</label>
            <input id="to_date" name="to_date" class="input" type="date" required>

            <label class="muted">Employee</label>
            <select name="name" class="input">
              <option value="">Select one</option>
              {% for nm in employees %}
                <option value="{{ nm }}">{{ nm }}</option>
              {% endfor %}
            </select>

            <label class="muted">Add New Employee</label>
            <input name="new_name" class="input" placeholder="New employee name">

            <div id="half_row" style="margin-top:8px">
              <label class="muted">Type</label>
              <select name="half_day" class="input">
                <option value="no">Full day</option>
                <option value="yes">Half day</option>
              </select>
            </div>

            <label class="muted">Note</label>
            <input name="note" class="input" placeholder="Reason">

            <div style="display:flex;gap:8px;margin-top:12px">
              <button type="submit" class="btn-primary">Save</button>
              <button type="button" onclick="closeModal()" class="input" style="border-radius:10px">Cancel</button>
            </div>
          </form>
        </div>
      </div>

      <script>
        function openModal(day){
          let y = {{ year }}, m = {{ month }};
          if(day !== null){
            let dateStr = y + "-" + String(m).padStart(2,'0') + "-" + String(day).padStart(2,'0');
            document.getElementById("from_date").value = dateStr;
            document.getElementById("to_date").value = dateStr;
          } else {
            // clear for manual add
            document.getElementById("from_date").value = "";
            document.getElementById("to_date").value = "";
          }
          document.getElementById("modal").style.display = "flex";
        }
        function closeModal(){ document.getElementById("modal").style.display = "none"; }
      </script>
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
        db.session.add(Leave(name=name, date=d, note=note, half_day=is_half))
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


# -------------------- Startup: create tables and migrate JSON if present --------------------
with app.app_context():
    db.create_all()
    import_json_to_db()

# -------------------- Run (local) --------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
