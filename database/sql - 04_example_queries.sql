USE harborwing;

-- Q1a. Reservation summary. Payments and legs are aggregated SEPARATELY,
--      so 3 payments x 2 legs does not become 6 rows and inflate the total.
SELECT r.reservation_id,
       CONCAT(p.first_name, ' ', p.last_name) AS passenger,
       a.agent_name                            AS agent,      -- NULL = direct booking
       r.party_size, r.reservation_status_code,
       pay.payment_count, pay.total_paid,
       lg.leg_count
FROM reservation r
JOIN passenger p ON p.passenger_id = r.main_passenger_id
LEFT JOIN booking_agent a ON a.agent_id = r.agent_id
LEFT JOIN (SELECT rp.reservation_id, COUNT(*) AS payment_count,
                  SUM(py.payment_amount) AS total_paid
           FROM reservation_payment rp
           JOIN payment py ON py.payment_id = rp.payment_id
           GROUP BY rp.reservation_id) pay ON pay.reservation_id = r.reservation_id
LEFT JOIN (SELECT reservation_id, COUNT(*) AS leg_count
           FROM reservation_leg GROUP BY reservation_id) lg
       ON lg.reservation_id = r.reservation_id
WHERE r.reservation_id = 1;

-- Q1b. Same reservation: list each payment (separate query on purpose)
SELECT rp.reservation_id, py.payment_id, py.payment_date,
       py.payment_amount, py.payment_status_code
FROM reservation_payment rp
JOIN payment py ON py.payment_id = rp.payment_id
WHERE rp.reservation_id = 1
ORDER BY py.payment_date;

-- Q1c. Same reservation: list each leg
SELECT rl.reservation_id, l.leg_id, l.flight_number,
       l.origin_airport, l.destination_airport,
       s.scheduled_departure, l.actual_departure
FROM reservation_leg rl
JOIN flight_leg l      ON l.leg_id = rl.leg_id
JOIN flight_schedule s ON s.flight_number = l.flight_number
WHERE rl.reservation_id = 1
ORDER BY s.scheduled_departure;

-- Q2. Reservations that use a particular leg
SELECT r.reservation_id, CONCAT(p.first_name, ' ', p.last_name) AS passenger,
       r.party_size, r.reservation_status_code
FROM reservation_leg rl
JOIN reservation r ON r.reservation_id = rl.reservation_id
JOIN passenger p   ON p.passenger_id = r.main_passenger_id
WHERE rl.leg_id = 1;

-- Q3. Payments linked to a reservation
SELECT py.payment_id, py.payment_date, py.payment_amount, py.payment_status_code
FROM reservation_payment rp
JOIN payment py ON py.payment_id = rp.payment_id
WHERE rp.reservation_id = 1;

-- Q4. Flight cost for a flight, aircraft type and date
--     (replace the sample values with ones that exist in your data)
SELECT flight_number, aircraft_type_code, valid_from, valid_to, cost_amount
FROM flight_cost
WHERE flight_number = 'HW101'
  AND aircraft_type_code = 'AT72'
  AND DATE '2026-05-15' BETWEEN valid_from AND valid_to;

-- Helper: find a real flight/aircraft/date to test Q4
SELECT flight_number, aircraft_type_code, valid_from, valid_to
FROM flight_cost LIMIT 5;

-- Policy check: overlapping cost periods (should return 0 rows)
SELECT a.flight_number, a.aircraft_type_code, a.valid_from AS a_from, b.valid_from AS b_from
FROM flight_cost a
JOIN flight_cost b
  ON a.flight_number = b.flight_number
 AND a.aircraft_type_code = b.aircraft_type_code
 AND a.valid_from < b.valid_from
 AND b.valid_from <= a.valid_to;

-- Evidence for the video: shared and multi-row cases exist
SELECT 'reservations with 3+ payments', COUNT(*) FROM
  (SELECT reservation_id FROM reservation_payment GROUP BY reservation_id HAVING COUNT(*) >= 3) x
UNION ALL SELECT 'payments shared by 2+ reservations', COUNT(*) FROM
  (SELECT payment_id FROM reservation_payment GROUP BY payment_id HAVING COUNT(*) >= 2) x
UNION ALL SELECT 'reservations with 3+ legs', COUNT(*) FROM
  (SELECT reservation_id FROM reservation_leg GROUP BY reservation_id HAVING COUNT(*) >= 3) x
UNION ALL SELECT 'direct reservations', COUNT(*) FROM reservation WHERE agent_id IS NULL
UNION ALL SELECT 'agent-assisted reservations', COUNT(*) FROM reservation WHERE agent_id IS NOT NULL;