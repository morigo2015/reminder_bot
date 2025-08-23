-- patients
CREATE TABLE IF NOT EXISTS patients (
  id       VARCHAR(40)  NOT NULL,
  chat_id  BIGINT       NOT NULL, -- consider BIGINT UNSIGNED
  name     VARCHAR(100) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY ux_patients_chat (chat_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- pills_day
CREATE TABLE IF NOT EXISTS pills_day (
  patient_id    VARCHAR(40)                                    NOT NULL,
  date_kyiv     DATE                                           NOT NULL,
  dose          ENUM('morning','evening')                      NOT NULL,
  label         VARCHAR(120)                                   NOT NULL,
  reminder_ts   DATETIME                                       NULL,
  confirm_ts    DATETIME                                       NULL,
  confirm_via   ENUM('button','text')                          NULL,
  escalated_ts  DATETIME                                       NULL,
  PRIMARY KEY (patient_id, date_kyiv, dose),
  KEY ix_pills_sweeper (reminder_ts, confirm_ts, escalated_ts),
  CONSTRAINT fk_pills_patient
    FOREIGN KEY (patient_id) REFERENCES patients(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- bp_readings
CREATE TABLE IF NOT EXISTS bp_readings (
  id           BIGINT NOT NULL AUTO_INCREMENT,
  patient_id   VARCHAR(40)           NOT NULL,
  ts_utc       DATETIME              NOT NULL,
  side         ENUM('left','right')  NOT NULL,
  sys          SMALLINT              NOT NULL,
  dia          SMALLINT              NOT NULL,
  pulse        SMALLINT              NOT NULL,
  flags        SET('out_of_range')   DEFAULT NULL,
  escalated_ts DATETIME              NULL,
  PRIMARY KEY (id),
  KEY ix_bp_patient_time (patient_id, ts_utc),
  CONSTRAINT fk_bp_patient
    FOREIGN KEY (patient_id) REFERENCES patients(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- health_status
CREATE TABLE IF NOT EXISTS health_status (
  id           BIGINT NOT NULL AUTO_INCREMENT,
  patient_id   VARCHAR(40)  NOT NULL,
  ts_utc       DATETIME     NOT NULL,
  text         TEXT         NOT NULL,
  alert_match  VARCHAR(200) NULL,
  escalated_ts DATETIME     NULL,
  PRIMARY KEY (id),
  KEY ix_status_patient_time (patient_id, ts_utc),
  CONSTRAINT fk_status_patient
    FOREIGN KEY (patient_id) REFERENCES patients(id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
