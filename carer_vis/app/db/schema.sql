-- patients
CREATE TABLE IF NOT EXISTS patients (
  id         VARCHAR(40) PRIMARY KEY,
  chat_id    BIGINT NOT NULL,
  name       VARCHAR(100) NOT NULL
) ENGINE=InnoDB;
CREATE UNIQUE INDEX IF NOT EXISTS ux_patients_chat ON patients(chat_id);

-- pills_day
CREATE TABLE IF NOT EXISTS pills_day (
  patient_id    VARCHAR(40) NOT NULL,
  date_kyiv     DATE NOT NULL,
  dose          ENUM('morning','evening') NOT NULL,
  label         VARCHAR(120) NOT NULL,
  reminder_ts   DATETIME NULL,
  confirm_ts    DATETIME NULL,
  confirm_via   ENUM('button','text') NULL,
  escalated_ts  DATETIME NULL,
  PRIMARY KEY (patient_id, date_kyiv, dose)
) ENGINE=InnoDB;
CREATE INDEX IF NOT EXISTS ix_pills_sweeper ON pills_day (reminder_ts, confirm_ts, escalated_ts);

-- bp_readings
CREATE TABLE IF NOT EXISTS bp_readings (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  patient_id   VARCHAR(40) NOT NULL,
  ts_utc       DATETIME NOT NULL,
  side         ENUM('left','right') NOT NULL,
  sys          SMALLINT NOT NULL,
  dia          SMALLINT NOT NULL,
  pulse        SMALLINT NOT NULL,
  flags        SET('out_of_range') DEFAULT NULL,
  escalated_ts DATETIME NULL
) ENGINE=InnoDB;
CREATE INDEX IF NOT EXISTS ix_bp_patient_time ON bp_readings(patient_id, ts_utc);

-- health_status
CREATE TABLE IF NOT EXISTS health_status (
  id           BIGINT PRIMARY KEY AUTO_INCREMENT,
  patient_id   VARCHAR(40) NOT NULL,
  ts_utc       DATETIME NOT NULL,
  text         TEXT NOT NULL,
  alert_match  VARCHAR(200) NULL,
  escalated_ts DATETIME NULL
) ENGINE=InnoDB;
CREATE INDEX IF NOT EXISTS ix_status_patient_time ON health_status(patient_id, ts_utc);
