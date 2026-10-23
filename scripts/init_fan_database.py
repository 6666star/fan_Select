# -*- coding: utf-8 -*-
"""
Initialize the V7 SQLite fan database from the existing fan data.

Usage:
    python scripts/init_fan_database.py
"""
import os
import sqlite3
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "fans.db")

sys.path.insert(0, ROOT)

from frontend.fan_db import FAN_DB  # noqa: E402


MANUFACTURER = "平安电气股份有限公司"
PRODUCT_NAME = "煤矿地面用防爆抽出式对旋轴流通风机"
PRODUCT_DETAILS = {
    "FBCDZ-6No23/2x315": ("FBCDZ-6№23/2×315", "YBF3-355L2-6", "2025-005-01"),
    "FBCDZ(B)-6-No20": ("FBCDZ(B)-6№20/2×220", "YBF3-355M1-6", "2025-005-02"),
    "FBCDZ(B)-6-No22": ("FBCDZ(B)-6№22/2×315", "YBF3-355L2-6", "2025-005-03"),
    "FBCDZ(B)-8-No24": ("FBCDZ(B)-8№24/2×185", "YBF3-355M2-8", "2025-005-04"),
    "FBCDZ(B)-8-No28": ("FBCDZ(B)-8№28/2×355", "YBF3-400L1-8", "2025-005-05"),
    "FBCDZ-10-No38LP": ("FBCDZ-10№38LP/2×710", "YBF3-450L1-10", "2025-005-06"),
    "FBCDZ-10-No40LP": ("FBCDZ-10№40LP/2×900", "YBF3-500L1-10", "2025-005-07"),
    "FBCDZ-12-No33LP": ("FBCDZ-12№33LP/2×355", "YBF3-400L1-12", "2025-005-08"),
    "FBCDZ-12-No38LP": ("FBCDZ-12№38LP/2×560", "YBF3-450L1-12", "2025-005-09"),
}


SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fan_curve_points;
DROP TABLE IF EXISTS fans;

CREATE TABLE fans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL UNIQUE,
    series TEXT NOT NULL,
    fan_type TEXT NOT NULL DEFAULT 'counter_rotating',
    manufacturer TEXT,
    product_name TEXT,
    product_spec TEXT,
    motor_model TEXT,
    factory_no TEXT,
    rated_rpm REAL NOT NULL,
    rpm_min REAL NOT NULL,
    rpm_max REAL NOT NULL,
    motor_kw REAL NOT NULL,
    motor_count INTEGER NOT NULL,
    blade_angle_deg REAL,
    withdrawable_rail_width_mm REAL,
    image_path TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE fan_curve_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fan_id INTEGER NOT NULL,
    q_m3_min REAL NOT NULL,
    h_pa REAL NOT NULL,
    eta_percent REAL NOT NULL,
    point_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (fan_id) REFERENCES fans(id) ON DELETE CASCADE
);

CREATE INDEX idx_fan_curve_points_fan_order
    ON fan_curve_points(fan_id, point_order, id);
"""


def init_database(db_path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)

        for fan in FAN_DB:
            rpm_min, rpm_max = fan.rpm_range
            product_spec, motor_model, factory_no = PRODUCT_DETAILS[fan.model_id]
            cur = conn.execute(
                """
                INSERT INTO fans (
                    model_id, series, fan_type, manufacturer, product_name,
                    product_spec, motor_model, factory_no, rated_rpm,
                    rpm_min, rpm_max, motor_kw, motor_count, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    fan.model_id,
                    fan.series,
                    fan.fan_type,
                    MANUFACTURER,
                    PRODUCT_NAME,
                    product_spec,
                    motor_model,
                    factory_no,
                    fan.rated_rpm,
                    rpm_min,
                    rpm_max,
                    fan.motor_kw,
                    fan.motor_count,
                ),
            )
            fan_id = cur.lastrowid

            for idx, point in enumerate(fan.curve_points):
                conn.execute(
                    """
                    INSERT INTO fan_curve_points (
                        fan_id, q_m3_min, h_pa, eta_percent, point_order
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        fan_id,
                        point.Q * 60.0,
                        point.H,
                        point.eta * 100.0,
                        idx,
                    ),
                )


if __name__ == "__main__":
    init_database()
    print(f"Initialized fan database: {DB_PATH}")
    print(f"Fan count: {len(FAN_DB)}")
