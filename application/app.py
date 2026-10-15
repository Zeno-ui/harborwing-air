"""HarborWing CRUD app. Generic CRUD driven by the ENT config below.
Table/column names come ONLY from this config (never from user input);
all VALUES are passed as %s parameters (prepared-style queries)."""
import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only")


@contextmanager
def tx():
    """One connection = one transaction. Commit on success, rollback on any error."""
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "harborwing"))
    try:
        yield conn.cursor(dictionary=True)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def f(n, k="text", req=True, mx=None, ch=None):
    return dict(n=n, k=k, req=req, mx=mx, ch=ch)

PAY = ["PAID", "PEND", "RFND"]
ENT = {
 "passenger": dict(pk=["passenger_id"], search=["first_name", "last_name", "email_address"], fields=[
    f("first_name", mx=60), f("second_name", req=False, mx=60), f("last_name", mx=60),
    f("phone_number", mx=30), f("email_address", mx=120), f("address_line1", mx=100),
    f("address_line2", req=False, mx=100), f("city", mx=80), f("state_province", mx=80),
    f("country", mx=80), f("other_details", req=False, mx=255)]),
 "booking_agent": dict(pk=["agent_id"], search=["agent_name"], fields=[
    f("agent_name", mx=100), f("agent_details", req=False, mx=255)]),
 "airport": dict(pk=["airport_code"], search=["airport_code", "airport_name", "location"], fields=[
    f("airport_code", mx=3), f("airport_name", mx=120), f("location", mx=120),
    f("other_details", req=False, mx=255)]),
 "payment": dict(pk=["payment_id"], search=["payment_status_code", "payment_id"], fields=[
    f("payment_status_code", ch=PAY), f("payment_date", "dt"), f("payment_amount", "dec")]),
 "flight_schedule": dict(pk=["flight_number"], search=["flight_number", "origin_airport", "destination_airport"], fields=[
    f("flight_number", mx=10), f("airline_code", mx=2), f("usual_aircraft_type_code", mx=6),
    f("origin_airport", mx=3), f("destination_airport", mx=3),
    f("scheduled_departure", "dt"), f("scheduled_arrival", "dt")]),
 "flight_leg": dict(pk=["leg_id"], search=["flight_number", "origin_airport", "destination_airport"], fields=[
    f("flight_number", mx=10), f("origin_airport", mx=3), f("destination_airport", mx=3),
    f("actual_departure", "dt", False), f("actual_arrival", "dt", False)]),
 "flight_cost": dict(pk=["flight_number", "aircraft_type_code", "valid_from"], search=["flight_number", "aircraft_type_code"], fields=[
    f("flight_number", mx=10), f("aircraft_type_code", mx=6), f("valid_from", "date"),
    f("valid_to", "date"), f("cost_amount", "dec")]),
 "reservation": dict(pk=["reservation_id"], search=["reservation_id", "reservation_status_code", "main_passenger_id"], fields=[
    f("main_passenger_id", "int"), f("agent_id", "int", False),
    f("reservation_status_code", ch=["CNF", "PEN", "CXL"]),
    f("ticket_type_code", ch=["ONE", "RTN", "MLT"]), f("travel_class_code", ch=["ECO", "PRE", "BUS"]),
    f("created_at", "dt"), f("party_size", "int")]),
 "calendar_date": dict(pk=["cal_date"], ro=True, search=["cal_date"], fields=[
    f("cal_date", "date"), f("day_of_month", "int"), f("is_business_day", "int")]),
}
AIRPORT_FIELDS = {"airport_code", "origin_airport", "destination_airport"}
MSG = {1451: "Cannot delete: other records still reference this one. Remove or reassign them first.",
       1452: "A referenced record does not exist (check the ID / code).",
       1062: "That record or link already exists.",
       3819: "Business rule violated (CHECK constraint): ",
       1048: "A required value is missing."}


def friendly(e):
    base = MSG.get(e.errno, "Database error: ")
    return base + (e.msg if e.errno not in MSG or e.errno == 3819 else "")


def cols(E):
    return list(dict.fromkeys(E["pk"] + [x["n"] for x in E["fields"]]))

app.jinja_env.globals.update(
    cols=cols, ENT=ENT, PAY=PAY,
    pkey=lambda E, r: "|".join(str(r[c]) for c in E["pk"]))


def clean(t, form):
    vals, errs = {}, []
    for fl in ENT[t]["fields"]:
        n, raw = fl["n"], (form.get(fl["n"]) or "").strip()
        if not raw:
            if fl["req"]:
                errs.append(f"{n} is required.")
            vals[n] = None
            continue
        try:
            k = fl["k"]
            if k == "int": v = int(raw)
            elif k == "dec": v = Decimal(raw)
            elif k == "date": v = datetime.strptime(raw, "%Y-%m-%d").date()
            elif k == "dt": v = datetime.strptime(raw.replace("T", " ")[:16], "%Y-%m-%d %H:%M")
            else: v = raw.upper() if n in AIRPORT_FIELDS else raw
        except (ValueError, InvalidOperation):
            errs.append(f"{n}: invalid {fl['k']} value.")
            continue
        if fl["mx"] and len(raw) > fl["mx"]:
            errs.append(f"{n}: max {fl['mx']} characters.")
        if fl["ch"] and raw not in fl["ch"]:
            errs.append(f"{n}: must be one of {', '.join(fl['ch'])}.")
        vals[n] = v
    return vals, errs


def ent(t, writable=False):
    if t not in ENT or (writable and ENT[t].get("ro")):
        abort(404)
    return ENT[t]


def keyparts(E, key):
    parts = key.split("|")
    if len(parts) != len(E["pk"]):
        abort(404)
    return parts


def where(E):
    return " AND ".join(f"{c}=%s" for c in E["pk"])


@app.route("/")
def home():
    return redirect(url_for("lst", t="passenger"))


@app.get("/<t>/")
def lst(t):
    E, q = ent(t), request.args.get("q", "").strip()
    sql, args = f"SELECT * FROM {t}", []
    if q:
        sql += " WHERE " + " OR ".join(f"{c} LIKE %s" for c in E["search"])
        args = [f"%{q}%"] * len(E["search"])
    sql += f" ORDER BY {', '.join(E['pk'])} LIMIT 200"
    rows = []
    try:
        with tx() as c:
            c.execute(sql, args)
            rows = c.fetchall()
    except mysql.connector.Error as e:
        flash(friendly(e), "err")
    return render_template("list.html", t=t, E=E, rows=rows, q=q)


@app.route("/<t>/new", methods=["GET", "POST"])
def new(t):
    E = ent(t, True)
    if request.method == "POST":
        vals, errs = clean(t, request.form)
        if not errs:
            try:
                with tx() as c:
                    c.execute(f"INSERT INTO {t} ({','.join(vals)}) VALUES ({','.join(['%s'] * len(vals))})",
                              list(vals.values()))
                flash("Record created.", "ok")
                return redirect(url_for("lst", t=t))
            except mysql.connector.Error as e:
                errs.append(friendly(e))
        for m in errs:
            flash(m, "err")
    return render_template("form.html", t=t, E=E, v=request.form, editing=False)


@app.route("/<t>/<key>/edit", methods=["GET", "POST"])
def edit(t, key):
    E = ent(t, True)
    parts = keyparts(E, key)
    try:
        with tx() as c:
            c.execute(f"SELECT * FROM {t} WHERE {where(E)}", parts)
            row = c.fetchone()
            if not row:
                flash("Record not found.", "err")
                return redirect(url_for("lst", t=t))
            if request.method == "POST":
                vals, errs = clean(t, {**request.form.to_dict(), **dict(zip(E["pk"], parts))})
                if not errs:
                    sets = [k for k in vals if k not in E["pk"]]
                    c.execute(f"UPDATE {t} SET {', '.join(k + '=%s' for k in sets)} WHERE {where(E)}",
                              [vals[k] for k in sets] + parts)
                    flash("Record updated.", "ok")
                    return redirect(url_for("lst", t=t))
                for m in errs:
                    flash(m, "err")
                row = request.form
    except mysql.connector.Error as e:
        flash(friendly(e), "err")
        row = request.form
    return render_template("form.html", t=t, E=E, v=row, editing=True)


@app.post("/<t>/<key>/delete")
def delete(t, key):
    E = ent(t, True)
    parts = keyparts(E, key)
    try:
        with tx() as c:
            c.execute(f"DELETE FROM {t} WHERE {where(E)}", parts)
            ok = c.rowcount > 0
        flash("Record deleted." if ok else "Record not found.", "ok" if ok else "err")
    except mysql.connector.Error as e:
        flash(friendly(e), "err")
    return redirect(url_for("lst", t=t))


# ---------- reservation detail + links ----------
LINK = {"payment": ("reservation_payment", "payment_id", "payment"),
        "leg": ("reservation_leg", "leg_id", "flight_leg")}


@app.get("/reservation/<int:rid>")
def reservation_view(rid):
    with tx() as c:
        c.execute("""SELECT r.*, CONCAT(p.first_name,' ',p.last_name) AS passenger, a.agent_name
                     FROM reservation r JOIN passenger p ON p.passenger_id=r.main_passenger_id
                     LEFT JOIN booking_agent a ON a.agent_id=r.agent_id
                     WHERE r.reservation_id=%s""", (rid,))
        r = c.fetchone()
        if not r:
            flash("Reservation not found.", "err")
            return redirect(url_for("lst", t="reservation"))
        c.execute("""SELECT py.* FROM reservation_payment rp JOIN payment py ON py.payment_id=rp.payment_id
                     WHERE rp.reservation_id=%s ORDER BY py.payment_date""", (rid,))
        pays = c.fetchall()
        c.execute("""SELECT l.*, s.scheduled_departure FROM reservation_leg rl
                     JOIN flight_leg l ON l.leg_id=rl.leg_id
                     JOIN flight_schedule s ON s.flight_number=l.flight_number
                     WHERE rl.reservation_id=%s ORDER BY s.scheduled_departure""", (rid,))
        legs = c.fetchall()
    total = sum((p["payment_amount"] for p in pays), Decimal("0"))
    return render_template("reservation.html", r=r, pays=pays, legs=legs, total=total)


@app.post("/reservation/<int:rid>/link/<kind>/add")
def link_add(rid, kind):
    tbl, col, _ = LINK.get(kind) or abort(404)
    xid = request.form.get("id", "").strip()
    if not xid.isdigit():
        flash("Enter a numeric ID.", "err")
    else:
        try:
            with tx() as c:
                c.execute(f"INSERT INTO {tbl} (reservation_id,{col}) VALUES (%s,%s)", (rid, int(xid)))
            flash(f"{kind.title()} {xid} linked.", "ok")
        except mysql.connector.Error as e:
            flash(friendly(e), "err")
    return redirect(url_for("reservation_view", rid=rid))


@app.post("/reservation/<int:rid>/link/<kind>/remove/<int:xid>")
def link_remove(rid, kind, xid):
    tbl, col, _ = LINK.get(kind) or abort(404)
    with tx() as c:   # deletes ONLY the link row, never the payment/leg
        c.execute(f"DELETE FROM {tbl} WHERE reservation_id=%s AND {col}=%s", (rid, xid))
        ok = c.rowcount > 0
    flash(f"Link removed ({kind} record kept)." if ok else "Link not found.", "ok" if ok else "err")
    return redirect(url_for("reservation_view", rid=rid))


@app.post("/reservation/<int:rid>/payment/new")
def payment_new(rid):
    vals, errs = clean("payment", request.form)
    if not errs:
        try:
            with tx() as c:   # TWO writes, ONE transaction: payment + link
                c.execute("INSERT INTO payment (payment_status_code,payment_date,payment_amount) VALUES (%s,%s,%s)",
                          (vals["payment_status_code"], vals["payment_date"], vals["payment_amount"]))
                c.execute("INSERT INTO reservation_payment (reservation_id,payment_id) VALUES (%s,%s)",
                          (rid, c.lastrowid))
            flash("Payment created and linked.", "ok")
        except mysql.connector.Error as e:
            errs.append(friendly(e))
    for m in errs:
        flash(m, "err")
    return redirect(url_for("reservation_view", rid=rid))


if __name__ == "__main__":
    app.run(debug=True)
