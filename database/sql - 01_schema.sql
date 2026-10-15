-- HarborWing Air schema. Requires MySQL 8.0.16+ (CHECK constraints are enforced).
-- All DATETIME columns are stored in UTC.
DROP DATABASE IF EXISTS harborwing;
CREATE DATABASE harborwing CHARACTER SET utf8mb4;
USE harborwing;

-- 1. Booking agent
CREATE TABLE booking_agent (
  agent_id      INT UNSIGNED NOT NULL AUTO_INCREMENT,
  agent_name    VARCHAR(100) NOT NULL,
  agent_details VARCHAR(255) NULL,
  PRIMARY KEY (agent_id)
) ENGINE=InnoDB;

-- 2. Passenger
CREATE TABLE passenger (
  passenger_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  first_name     VARCHAR(60)  NOT NULL,
  second_name    VARCHAR(60)  NULL,
  last_name      VARCHAR(60)  NOT NULL,
  phone_number   VARCHAR(30)  NOT NULL,
  email_address  VARCHAR(120) NOT NULL,
  address_line1  VARCHAR(100) NOT NULL,
  address_line2  VARCHAR(100) NULL,
  city           VARCHAR(80)  NOT NULL,
  state_province VARCHAR(80)  NOT NULL,
  country        VARCHAR(80)  NOT NULL,
  other_details  VARCHAR(255) NULL,
  PRIMARY KEY (passenger_id),
  INDEX idx_passenger_name  (last_name, first_name),
  INDEX idx_passenger_email (email_address)
) ENGINE=InnoDB;

-- 3. Airport
CREATE TABLE airport (
  airport_code  CHAR(3)      NOT NULL,
  airport_name  VARCHAR(120) NOT NULL,
  location      VARCHAR(120) NOT NULL,
  other_details VARCHAR(255) NULL,
  PRIMARY KEY (airport_code)
) ENGINE=InnoDB;

-- 4. Calendar date
CREATE TABLE calendar_date (
  cal_date        DATE        NOT NULL,
  day_of_month    TINYINT UNSIGNED NOT NULL,
  is_business_day TINYINT(1)  NOT NULL,
  PRIMARY KEY (cal_date),
  CONSTRAINT chk_cal_day CHECK (day_of_month BETWEEN 1 AND 31),
  CONSTRAINT chk_cal_biz CHECK (is_business_day IN (0,1))
) ENGINE=InnoDB;

-- 5. Payment
CREATE TABLE payment (
  payment_id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  payment_status_code VARCHAR(10)  NOT NULL COMMENT 'externally managed code',
  payment_date        DATETIME     NOT NULL COMMENT 'UTC',
  payment_amount      DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (payment_id),
  CONSTRAINT chk_payment_amount CHECK (payment_amount > 0),
  INDEX idx_payment_date (payment_date)
) ENGINE=InnoDB;

-- 6. Flight schedule (flight_number is the unique identifier: simplifying assumption)
CREATE TABLE flight_schedule (
  flight_number            VARCHAR(10) NOT NULL,
  airline_code             CHAR(2)     NOT NULL COMMENT 'externally managed code',
  usual_aircraft_type_code VARCHAR(6)  NOT NULL COMMENT 'externally managed code',
  origin_airport           CHAR(3)     NOT NULL,
  destination_airport      CHAR(3)     NOT NULL,
  scheduled_departure      DATETIME    NOT NULL COMMENT 'UTC',
  scheduled_arrival        DATETIME    NOT NULL COMMENT 'UTC',
  PRIMARY KEY (flight_number),
  CONSTRAINT chk_sched_airports CHECK (origin_airport <> destination_airport),
  CONSTRAINT chk_sched_times    CHECK (scheduled_arrival > scheduled_departure),
  CONSTRAINT fk_sched_origin FOREIGN KEY (origin_airport)
    REFERENCES airport (airport_code) ON DELETE RESTRICT,
  CONSTRAINT fk_sched_dest FOREIGN KEY (destination_airport)
    REFERENCES airport (airport_code) ON DELETE RESTRICT,
  INDEX idx_sched_route (origin_airport, destination_airport),
  INDEX idx_sched_departure (scheduled_departure)
) ENGINE=InnoDB;

-- 7. Flight leg (actual times are NULL until the flight operates)
CREATE TABLE flight_leg (
  leg_id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  flight_number       VARCHAR(10)  NOT NULL,
  origin_airport      CHAR(3)      NOT NULL,
  destination_airport CHAR(3)      NOT NULL,
  actual_departure    DATETIME     NULL COMMENT 'UTC',
  actual_arrival      DATETIME     NULL COMMENT 'UTC',
  PRIMARY KEY (leg_id),
  CONSTRAINT chk_leg_airports CHECK (origin_airport <> destination_airport),
  CONSTRAINT chk_leg_times CHECK (
    actual_departure IS NULL OR actual_arrival IS NULL
    OR actual_arrival > actual_departure),
  CONSTRAINT fk_leg_flight FOREIGN KEY (flight_number)
    REFERENCES flight_schedule (flight_number) ON DELETE RESTRICT,
  CONSTRAINT fk_leg_origin FOREIGN KEY (origin_airport)
    REFERENCES airport (airport_code) ON DELETE RESTRICT,
  CONSTRAINT fk_leg_dest FOREIGN KEY (destination_airport)
    REFERENCES airport (airport_code) ON DELETE RESTRICT,
  INDEX idx_leg_flight (flight_number),
  INDEX idx_leg_route (origin_airport, destination_airport)
) ENGINE=InnoDB;

-- 8. Flight cost (composite primary key keeps cost history)
CREATE TABLE flight_cost (
  flight_number      VARCHAR(10)   NOT NULL,
  aircraft_type_code VARCHAR(6)    NOT NULL COMMENT 'externally managed code',
  valid_from         DATE          NOT NULL,
  valid_to           DATE          NOT NULL,
  cost_amount        DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (flight_number, aircraft_type_code, valid_from),
  CONSTRAINT chk_cost_nonneg CHECK (cost_amount >= 0),
  CONSTRAINT chk_cost_dates  CHECK (valid_to >= valid_from),
  CONSTRAINT fk_cost_flight FOREIGN KEY (flight_number)
    REFERENCES flight_schedule (flight_number) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_from FOREIGN KEY (valid_from)
    REFERENCES calendar_date (cal_date) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_to FOREIGN KEY (valid_to)
    REFERENCES calendar_date (cal_date) ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 9. Reservation
CREATE TABLE reservation (
  reservation_id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
  main_passenger_id       INT UNSIGNED NOT NULL,
  agent_id                INT UNSIGNED NULL,
  reservation_status_code VARCHAR(10)  NOT NULL COMMENT 'externally managed code',
  ticket_type_code        VARCHAR(10)  NOT NULL COMMENT 'externally managed code',
  travel_class_code       VARCHAR(10)  NOT NULL COMMENT 'externally managed code',
  created_at              DATETIME     NOT NULL COMMENT 'UTC',
  party_size              SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (reservation_id),
  CONSTRAINT chk_party_size CHECK (party_size > 0),
  CONSTRAINT fk_res_passenger FOREIGN KEY (main_passenger_id)
    REFERENCES passenger (passenger_id) ON DELETE RESTRICT,
  CONSTRAINT fk_res_agent FOREIGN KEY (agent_id)
    REFERENCES booking_agent (agent_id) ON DELETE SET NULL,
  INDEX idx_res_passenger (main_passenger_id),
  INDEX idx_res_agent (agent_id),
  INDEX idx_res_created (created_at)
) ENGINE=InnoDB;

-- 10. Reservation-payment link (no allocation amount, by design)
CREATE TABLE reservation_payment (
  reservation_id INT UNSIGNED NOT NULL,
  payment_id     INT UNSIGNED NOT NULL,
  PRIMARY KEY (reservation_id, payment_id),
  CONSTRAINT fk_rp_res FOREIGN KEY (reservation_id)
    REFERENCES reservation (reservation_id) ON DELETE CASCADE,
  CONSTRAINT fk_rp_pay FOREIGN KEY (payment_id)
    REFERENCES payment (payment_id) ON DELETE CASCADE,
  INDEX idx_rp_payment (payment_id)
) ENGINE=InnoDB;

-- 11. Reservation-leg link
CREATE TABLE reservation_leg (
  reservation_id INT UNSIGNED NOT NULL,
  leg_id         INT UNSIGNED NOT NULL,
  PRIMARY KEY (reservation_id, leg_id),
  CONSTRAINT fk_rl_res FOREIGN KEY (reservation_id)
    REFERENCES reservation (reservation_id) ON DELETE CASCADE,
  CONSTRAINT fk_rl_leg FOREIGN KEY (leg_id)
    REFERENCES flight_leg (leg_id) ON DELETE CASCADE,
  INDEX idx_rl_leg (leg_id)
) ENGINE=InnoDB;