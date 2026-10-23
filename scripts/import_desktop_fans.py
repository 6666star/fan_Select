# -*- coding: utf-8 -*-
"""Import the four fan curves under Desktop/data into the V7 SQLite database.

The source X/Y columns are interpreted as flow (m3/s) and pressure (Pa).
The existing database stores flow in m3/min, so flow is multiplied by 60.
Missing efficiencies are completed with shape-preserving PCHIP interpolation.
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "fans.db"
SOURCE_ROOT = Path.home() / "Desktop" / "数据"

FANS = [
    {
        "model_id": "FBCDZ-10-No38LP",
        "series": "FBCDZ-10",
        "rated_rpm": 590.0,
        "rpm_min": 295.0,
        "rpm_max": 590.0,
        "motor_kw": 710.0,
        "motor_count": 2,
        "blade_angle_deg": 0.0,
        "withdrawable_rail_width_mm": 1800.0,
        "image_path": "images/fans/FBCDZ-10-No38LP.jpg",
        "curve_file": SOURCE_ROOT / "FBCDZ-10-No38LP" / "curve_0_perfect.csv",
    },
    {
        "model_id": "FBCDZ-10-No40LP",
        "series": "FBCDZ-10",
        "rated_rpm": 590.0,
        "rpm_min": 295.0,
        "rpm_max": 590.0,
        "motor_kw": 900.0,
        "motor_count": 2,
        "blade_angle_deg": 0.0,
        "withdrawable_rail_width_mm": 2000.0,
        "image_path": "images/fans/FBCDZ-10-No40LP.jpg",
        "curve_file": SOURCE_ROOT / "FBCDZ-10-No40LP" / "curve_0_perfect.csv",
    },
    {
        "model_id": "FBCDZ-12-No33LP",
        "series": "FBCDZ-12",
        "rated_rpm": 490.0,
        "rpm_min": 245.0,
        "rpm_max": 490.0,
        "motor_kw": 355.0,
        "motor_count": 2,
        "blade_angle_deg": 0.0,
        "withdrawable_rail_width_mm": 1600.0,
        "image_path": "images/fans/FBCDZ-12-No33LP.jpg",
        "curve_file": SOURCE_ROOT / "FBCDZ-12-No33LP" / "Default Dataset 3.csv",
    },
    {
        "model_id": "FBCDZ-12-No38LP",
        "series": "FBCDZ-12",
        "rated_rpm": 490.0,
        "rpm_min": 245.0,
        "rpm_max": 490.0,
        "motor_kw": 560.0,
        "motor_count": 2,
        "blade_angle_deg": 0.0,
        "withdrawable_rail_width_mm": 1800.0,
        "image_path": "images/fans/FBCDZ-12-No38LP.jpg",
        "curve_file": SOURCE_ROOT / "FBCDZ-12-No38LP" / "Dataset 3.csv",
    },
]

MANUFACTURER = "平安电气股份有限公司"
PRODUCT_NAME = "煤矿地面用防爆抽出式对旋轴流通风机"
PRODUCT_DETAILS = {
    "FBCDZ-10-No38LP": ("FBCDZ-10№38LP/2×710", "YBF3-450L1-10", "2025-005-06"),
    "FBCDZ-10-No40LP": ("FBCDZ-10№40LP/2×900", "YBF3-500L1-10", "2025-005-07"),
    "FBCDZ-12-No33LP": ("FBCDZ-12№33LP/2×355", "YBF3-400L1-12", "2025-005-08"),
    "FBCDZ-12-No38LP": ("FBCDZ-12№38LP/2×560", "YBF3-450L1-12", "2025-005-09"),
}


def read_curve(path: Path) -> list[tuple[float, float, float]]:
    if not path.is_file():
        raise FileNotFoundError(path)

    raw: list[tuple[float, float, float | None]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            try:
                flow = float(row[0])
                pressure = float(row[1])
            except ValueError:  # header
                continue

            efficiency = None
            # Completed CSV: prefer Completed_Eff (column 4).
            candidates = [row[3] if len(row) > 3 else "", row[2] if len(row) > 2 else ""]
            for value in candidates:
                if value.strip():
                    efficiency = float(value)
                    break
            raw.append((flow, pressure, efficiency))

    if len(raw) < 5:
        raise ValueError(f"{path} has fewer than five curve points")

    known_indices = np.array([i for i, point in enumerate(raw) if point[2] is not None])
    known_efficiencies = np.array([point[2] for point in raw if point[2] is not None])
    if len(known_indices) < 2:
        raise ValueError(f"{path} has insufficient known efficiency values")

    interpolator = PchipInterpolator(known_indices, known_efficiencies, extrapolate=True)
    completed = interpolator(np.arange(len(raw)))

    points = []
    for (flow, pressure, efficiency), filled in zip(raw, completed):
        eta = float(efficiency if efficiency is not None else filled)
        if flow <= 0 or pressure <= 0 or not 0 < eta <= 100:
            raise ValueError(f"invalid point in {path}: Q={flow}, H={pressure}, eta={eta}")
        points.append((flow, pressure, eta))
    return points


def add_column_if_missing(conn: sqlite3.Connection, name: str, declaration: str) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(fans)")}
    if name not in columns:
        conn.execute(f"ALTER TABLE fans ADD COLUMN {name} {declaration}")


def main() -> None:
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    curves = [(fan, read_curve(fan["curve_file"])) for fan in FANS]
    backup = DB_PATH.with_name(f"fans_before_desktop_import_{datetime.now():%Y%m%d_%H%M%S}.db")
    shutil.copy2(DB_PATH, backup)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        add_column_if_missing(conn, "blade_angle_deg", "REAL")
        add_column_if_missing(conn, "withdrawable_rail_width_mm", "REAL")
        add_column_if_missing(conn, "image_path", "TEXT")
        add_column_if_missing(conn, "manufacturer", "TEXT")
        add_column_if_missing(conn, "product_name", "TEXT")
        add_column_if_missing(conn, "product_spec", "TEXT")
        add_column_if_missing(conn, "motor_model", "TEXT")
        add_column_if_missing(conn, "factory_no", "TEXT")

        for fan, points in curves:
            product_spec, motor_model, factory_no = PRODUCT_DETAILS[fan["model_id"]]
            conn.execute(
                """
                INSERT INTO fans (
                    model_id, series, fan_type, rated_rpm, rpm_min, rpm_max,
                    motor_kw, motor_count, enabled, blade_angle_deg,
                    withdrawable_rail_width_mm, image_path, manufacturer,
                    product_name, product_spec, motor_model, factory_no, updated_at
                ) VALUES (?, ?, 'counter_rotating', ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(model_id) DO UPDATE SET
                    series=excluded.series,
                    fan_type=excluded.fan_type,
                    rated_rpm=excluded.rated_rpm,
                    rpm_min=excluded.rpm_min,
                    rpm_max=excluded.rpm_max,
                    motor_kw=excluded.motor_kw,
                    motor_count=excluded.motor_count,
                    enabled=1,
                    blade_angle_deg=excluded.blade_angle_deg,
                    withdrawable_rail_width_mm=excluded.withdrawable_rail_width_mm,
                    image_path=excluded.image_path,
                    manufacturer=excluded.manufacturer,
                    product_name=excluded.product_name,
                    product_spec=excluded.product_spec,
                    motor_model=excluded.motor_model,
                    factory_no=excluded.factory_no,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    fan["model_id"], fan["series"], fan["rated_rpm"], fan["rpm_min"],
                    fan["rpm_max"], fan["motor_kw"], fan["motor_count"],
                    fan["blade_angle_deg"], fan["withdrawable_rail_width_mm"], fan["image_path"],
                    MANUFACTURER, PRODUCT_NAME, product_spec, motor_model, factory_no,
                ),
            )
            fan_id = conn.execute(
                "SELECT id FROM fans WHERE model_id = ?", (fan["model_id"],)
            ).fetchone()[0]
            conn.execute("DELETE FROM fan_curve_points WHERE fan_id = ?", (fan_id,))
            conn.executemany(
                """
                INSERT INTO fan_curve_points (
                    fan_id, q_m3_min, h_pa, eta_percent, point_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (fan_id, flow_m3_s * 60.0, pressure_pa, eta_percent, order)
                    for order, (flow_m3_s, pressure_pa, eta_percent) in enumerate(points)
                ],
            )

        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_key_errors:
            raise RuntimeError(f"database validation failed: {integrity}, {foreign_key_errors}")

    print(f"Backup: {backup}")
    print(f"Imported fan count: {len(FANS)}")
    for fan, points in curves:
        print(f"  {fan['model_id']}: {len(points)} points")


if __name__ == "__main__":
    main()
