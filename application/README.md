# HarborWing CRUD App (Project 2)
Database: built from the Midterm Drill repo — <LINK + commit/version here>. No schema changes.

## Setup
1. Create DB: run `01_schema.sql` in MySQL 8.0.16+, then `python gen.py` (Midterm Drill).
2. `cd application && python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
3. `pip install -r requirements.txt`
4. `cp .env.example .env` and fill in DB credentials (`.env` is git-ignored).
5. `flask --app app run` then open http://127.0.0.1:5000

## Features
CRUD for passengers, agents, airports, payments, schedules, legs, costs, reservations; reservation detail page with add/remove payment & leg links; search box on every list; read-only calendar view.

## Policies
- Deleting a record still referenced (airport used by a schedule, passenger with reservations, etc.) is blocked by FK RESTRICT; the app shows a clear message.
- Removing a link deletes only the link row. Deleting a reservation/payment/leg cascades to link rows only (schema ON DELETE CASCADE).
- Business rules (CHECK constraints) are enforced by MySQL; violations are shown as messages.

## Known limitations
No login, no pagination (200 rows max), reference codes are fixed lists in app.py.
