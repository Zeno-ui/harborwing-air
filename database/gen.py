"""
HarborWing Air synthetic data generator.
- Fixed seed (42) => same data on every run.
- Inserts parents before children, using explicit IDs so every FK is valid.
- Safe to re-run: it empties all tables first (see reset_tables).
Connection settings come from env vars DB_HOST, DB_USER, DB_PASSWORD.
"""
import os
import random
import string
from datetime import date, datetime, timedelta

import mysql.connector
from faker import Faker

SEED = 42
random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_US")
fake.seed_instance(SEED)

AS_OF = datetime(2026, 10, 14, 12, 0)   # fixed "now" so output is repeatable

# Externally managed reference codes (NOT stored in lookup tables)
RES_STATUS = ["CNF", "PEN", "CXL"]
TICKET_TYPE = ["ONE", "RTN", "MLT"]       # one-way, return, multi-city
TRAVEL_CLASS = ["ECO", "PRE", "BUS"]
PAY_STATUS = ["PAID", "PEND", "RFND"]
AIRCRAFT = ["AT72", "DH8D", "E175", "B190", "DHC6"]
AIRLINE = "HW"

N_AGENTS, N_PASSENGERS, N_AIRPORTS = 60, 120, 60
N_SCHEDULES, N_EXTRA_LEGS = 80, 70
N_PAYMENTS, N_RESERVATIONS = 120, 120


def rand_dt(start, end):
    secs = int((end - start).total_seconds())
    return (start + timedelta(seconds=random.randint(0, secs))).replace(microsecond=0)


def insert(cur, table, cols, rows):
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    cur.executemany(sql, rows)
    print(f"  {table}: {len(rows)} rows")


def reset_tables(conn):
    """Documented reset: empty every table, children first."""
    cur = conn.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for t in ["reservation_leg", "reservation_payment", "reservation", "flight_cost",
              "flight_leg", "flight_schedule", "payment", "calendar_date",
              "airport", "passenger", "booking_agent"]:
        cur.execute(f"TRUNCATE TABLE {t}")
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()          # TRUNCATE commits implicitly anyway
    cur.close()


def main():
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database="harborwing",
    )
    reset_tables(conn)
    cur = conn.cursor()
    try:
        # ---------- 1. booking_agent ----------
        agents = [(i, f"{fake.company()} Travel (demo)", fake.catch_phrase())
                  for i in range(1, N_AGENTS + 1)]
        insert(cur, "booking_agent", ["agent_id", "agent_name", "agent_details"], agents)

        # ---------- 2. passenger ----------
        passengers = []
        for i in range(1, N_PASSENGERS + 1):
            second = fake.first_name() if random.random() < 0.5 else None
            line2 = fake.secondary_address() if random.random() < 0.3 else None
            other = "Frequent flyer (demo)" if random.random() < 0.2 else None
            passengers.append((
                i, fake.first_name(), second, fake.last_name(),
                fake.phone_number()[:30], fake.unique.email(),
                fake.street_address(), line2, fake.city(), fake.state(),
                "United States", other))
        insert(cur, "passenger",
               ["passenger_id", "first_name", "second_name", "last_name", "phone_number",
                "email_address", "address_line1", "address_line2", "city",
                "state_province", "country", "other_details"], passengers)

        # ---------- 3. airport ----------
        codes = set()
        while len(codes) < N_AIRPORTS:
            codes.add("".join(random.choices(string.ascii_uppercase, k=3)))
        airport_codes = sorted(codes)
        airports = []
        for code in airport_codes:
            city = fake.city()
            airports.append((code, f"{city} Harbor Airport", f"{city}, {fake.state()}",
                             "DEMONSTRATION DATA - fictional airport"))
        insert(cur, "airport", ["airport_code", "airport_name", "location", "other_details"],
               airports)

        # ---------- 4. calendar_date (all of 2026) ----------
        cal = []
        d = date(2026, 1, 1)
        while d <= date(2026, 12, 31):
            cal.append((d, d.day, 1 if d.weekday() < 5 else 0))
            d += timedelta(days=1)
        insert(cur, "calendar_date", ["cal_date", "day_of_month", "is_business_day"], cal)

        # ---------- 5. payment ----------
        payments = []
        for i in range(1, N_PAYMENTS + 1):
            payments.append((
                i, random.choices(PAY_STATUS, weights=[80, 15, 5])[0],
                rand_dt(datetime(2026, 1, 2), AS_OF),
                round(random.uniform(50, 2500), 2)))
        insert(cur, "payment",
               ["payment_id", "payment_status_code", "payment_date", "payment_amount"],
               payments)

        # ---------- 6. flight_schedule ----------
        schedules, sched = [], {}
        for n in range(101, 101 + N_SCHEDULES):
            fn = f"{AIRLINE}{n}"
            origin, dest = random.sample(airport_codes, 2)   # always different
            dep = rand_dt(datetime(2026, 2, 1), datetime(2026, 11, 30)).replace(second=0)
            arr = dep + timedelta(minutes=random.randint(45, 240))
            ac = random.choice(AIRCRAFT)
            schedules.append((fn, AIRLINE, ac, origin, dest, dep, arr))
            sched[fn] = dict(dep=dep, arr=arr, origin=origin, dest=dest, ac=ac)
        insert(cur, "flight_schedule",
               ["flight_number", "airline_code", "usual_aircraft_type_code", "origin_airport",
                "destination_airport", "scheduled_departure", "scheduled_arrival"], schedules)

        # ---------- 7. flight_leg ----------
        flight_numbers = list(sched.keys())
        leg_flights = flight_numbers + random.choices(flight_numbers, k=N_EXTRA_LEGS)
        legs = []
        for leg_id, fn in enumerate(leg_flights, start=1):
            s = sched[fn]
            if s["dep"] < AS_OF:        # flight already operated
                a_dep = s["dep"] + timedelta(minutes=random.randint(-5, 45))
                a_arr = a_dep + (s["arr"] - s["dep"]) + timedelta(minutes=random.randint(-10, 20))
            else:                       # future flight: actuals unknown
                a_dep = a_arr = None
            legs.append((leg_id, fn, s["origin"], s["dest"], a_dep, a_arr))
        insert(cur, "flight_leg",
               ["leg_id", "flight_number", "origin_airport", "destination_airport",
                "actual_departure", "actual_arrival"], legs)
        n_legs = len(legs)

        # ---------- 8. flight_cost (non-overlapping validity periods) ----------
        periods = [(date(2026, 1, 1), date(2026, 3, 31)),
                   (date(2026, 4, 1), date(2026, 6, 30)),
                   (date(2026, 7, 1), date(2026, 12, 31))]
        costs = []
        for fn, s in sched.items():
            k = random.choice([1, 2, 3])
            first = random.randint(0, 3 - k)
            for vf, vt in periods[first:first + k]:
                ac = s["ac"] if random.random() < 0.8 else random.choice(AIRCRAFT)
                costs.append((fn, ac, vf, vt, round(random.uniform(1500, 12000), 2)))
        costs = sorted(set(costs), key=lambda r: (r[0], r[1], r[2]))
        insert(cur, "flight_cost",
               ["flight_number", "aircraft_type_code", "valid_from", "valid_to",
                "cost_amount"], costs)

        # ---------- 9. reservation ----------
        reservations = []
        for i in range(1, N_RESERVATIONS + 1):
            agent = random.randint(1, N_AGENTS) if random.random() < 0.4 else None
            reservations.append((
                i, random.randint(1, N_PASSENGERS), agent,
                random.choices(RES_STATUS, weights=[70, 20, 10])[0],
                random.choice(TICKET_TYPE), random.choice(TRAVEL_CLASS),
                rand_dt(datetime(2026, 1, 1), AS_OF), random.randint(1, 6)))
        insert(cur, "reservation",
               ["reservation_id", "main_passenger_id", "agent_id", "reservation_status_code",
                "ticket_type_code", "travel_class_code", "created_at", "party_size"],
               reservations)

        res_ids = list(range(1, N_RESERVATIONS + 1))
        pay_ids = list(range(1, N_PAYMENTS + 1))
        leg_ids = list(range(1, n_legs + 1))

        # ---------- 10. reservation_payment (a set blocks duplicate pairs) ----------
        rp = set()
        for r in res_ids[:20]:                       # reservations with 3 payments
            rp.update((r, p) for p in random.sample(pay_ids, 3))
        for r in res_ids[20:]:                       # the rest: 1-2 payments
            rp.update((r, p) for p in random.sample(pay_ids, random.randint(1, 2)))
        for p in pay_ids[:15]:                       # payments shared by 2-3 reservations
            rp.update((r, p) for r in random.sample(res_ids, random.randint(2, 3)))
        used = {p for _, p in rp}
        for p in pay_ids:                            # every payment linked at least once
            if p not in used:
                rp.add((random.choice(res_ids), p))
        insert(cur, "reservation_payment", ["reservation_id", "payment_id"], sorted(rp))

        # ---------- 11. reservation_leg ----------
        rl = set()
        for r in res_ids[:25]:                       # reservations with 3 legs
            rl.update((r, l) for l in random.sample(leg_ids, 3))
        for r in res_ids[25:]:
            rl.update((r, l) for l in random.sample(leg_ids, random.randint(1, 2)))
        for l in leg_ids[:20]:                       # legs shared by 2-3 reservations
            rl.update((r, l) for r in random.sample(res_ids, random.randint(2, 3)))
        used = {l for _, l in rl}
        for l in leg_ids:
            if l not in used:
                rl.add((random.choice(res_ids), l))
        insert(cur, "reservation_leg", ["reservation_id", "leg_id"], sorted(rl))

        conn.commit()
        print("Done. Data committed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()