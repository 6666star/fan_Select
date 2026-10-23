# -*- coding: utf-8 -*-
"""前端只读风机数据库。

选型计算仍由 C++ 后端完成；这里直接读取 SQLite，仅用于首页风机库概览。
"""

import sqlite3
from pathlib import Path

import numpy as np
from frontend.models import FanCurvePoint, FanModel, FanInterpolated


FBCDZ6No23_RAW = [
    (9555.650, 742.502, 35.918), (9451.195, 895.548, 40.877),
    (9388.228, 1007.052, 44.626), (9246.774, 1180.590, 48.830),
    (9209.297, 1277.564, 51.612), (9106.291, 1384.896, 53.762),
    (9025.160, 1513.428, 56.740), (8920.353, 1632.692, 59.013),
    (8809.763, 1779.403, 61.869), (8664.286, 1927.954, 63.305),
    (8631.185, 2095.736, 66.284), (8521.308, 2187.972, 66.425),
    (8495.096, 2281.365, 68.048), (8434.312, 2410.125, 69.841),
    (8295.474, 2500.312, 70.378), (8347.981, 2591.257, 72.038),
    (8186.169, 2737.233, 73.184), (8114.174, 2850.657, 75.165),
    (8096.507, 2915.027, 76.743), (7962.382, 3047.536, 77.777),
    (7845.313, 3156.296, 78.125), (7736.817, 3299.928, 78.406),
    (7651.851, 3436.074, 79.800), (7577.307, 3505.013, 79.776),
    (7392.183, 3663.011, 80.649), (7241.752, 3787.322, 81.659),
    (7118.114, 3919.109, 83.129), (7025.422, 4014.220, 81.799),
    (6891.138, 4143.442, 82.250), (6690.955, 4264.774, 81.732),
    (6632.308, 4363.078, 82.793), (6502.665, 4430.736, 82.103),
    (6387.807, 4512.488, 82.518), (6240.800, 4642.862, 83.355),
    (6107.758, 4731.730, 83.223), (6008.163, 4777.594, 82.454),
    (5899.600, 4834.701, 82.453), (5789.629, 4877.954, 81.428),
    (5623.017, 4915.178, 79.980),
]

FBCDZ6No20B_RAW = [
    (7380, 1120, 41.2), (7200, 1380, 48.5), (7010, 1650, 55.7),
    (6800, 1920, 61.4), (6550, 2250, 67.3), (6320, 2580, 72.8),
    (6100, 2890, 77.4), (5850, 3210, 80.5), (5600, 3520, 82.1),
    (5320, 3810, 81.6),
]

FBCDZ6No22B_RAW = [
    (10200, 980, 39.4), (9900, 1260, 46.1), (9650, 1540, 52.8),
    (9360, 1830, 59.9), (9050, 2150, 66.5), (8760, 2470, 72.2),
    (8420, 2820, 77.6), (8090, 3180, 81.2), (7750, 3520, 82.8),
    (7420, 3880, 81.9),
]

FBCDZ8No24B_RAW = [
    (9200, 860, 38.2), (8950, 1140, 45.9), (8680, 1410, 53.1),
    (8420, 1710, 59.7), (8120, 2050, 66.4), (7800, 2380, 72.5),
    (7480, 2730, 77.9), (7120, 3090, 81.6), (6780, 3420, 83.0),
    (6450, 3710, 82.4),
]

FBCDZ8No28B_RAW = [
    (15800, 1320, 42.1), (15200, 1680, 49.7), (14600, 2050, 57.6),
    (13900, 2440, 64.3), (13200, 2860, 70.5), (12500, 3270, 75.9),
    (11800, 3690, 80.1), (11100, 4100, 82.6), (10400, 4470, 83.1),
    (9800, 4820, 81.8),
]


def make_fan_from_data(model_id, series, rpm, rpm_range, motor_kw, motor_count,
                       raw_data, fan_type="counter_rotating"):
    sorted_data = sorted(raw_data, key=lambda x: x[0])
    points = [FanCurvePoint(Q=q / 60.0, H=h, eta=eta / 100.0)
              for q, h, eta in sorted_data]
    return FanModel(model_id=model_id, series=series, fan_type=fan_type,
                    rated_rpm=rpm, rpm_range=rpm_range, motor_kw=motor_kw,
                    motor_count=motor_count, curve_points=points)


def build_fan_interpolated(fan, H_deg=2, eta_deg=4):
    Q = np.array([p.Q for p in fan.curve_points])
    H = np.array([p.H for p in fan.curve_points])
    eta = np.array([p.eta for p in fan.curve_points])

    H_poly = np.poly1d(np.polyfit(Q, H, H_deg))
    eta_poly = np.poly1d(np.polyfit(Q, eta, eta_deg))

    H_pred = H_poly(Q)
    eta_pred = eta_poly(Q)
    R2_H = 1 - np.sum((H - H_pred) ** 2) / np.sum((H - H.mean()) ** 2)
    R2_eta = 1 - np.sum((eta - eta_pred) ** 2) / np.sum((eta - eta.mean()) ** 2)

    return FanInterpolated(fan=fan, H_spline=H_poly, eta_spline=eta_poly,
                           Q_min=Q.min(), Q_max=Q.max(),
                           R2_H=R2_H, R2_eta=R2_eta)


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "fans.db"


def load_fan_db(db_path=DB_PATH):
    """Load enabled fans from SQLite without modifying the database."""
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"风机数据库不存在：{db_path}")

    fans = []
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        fan_rows = connection.execute(
            """
            SELECT id, model_id, series, fan_type, rated_rpm,
                   rpm_min, rpm_max, motor_kw, motor_count
            FROM fans
            WHERE enabled != 0
            ORDER BY id
            """
        ).fetchall()

        for row in fan_rows:
            (fan_id, model_id, series, fan_type, rated_rpm,
             rpm_min, rpm_max, motor_kw, motor_count) = row
            raw_data = connection.execute(
                """
                SELECT q_m3_min, h_pa, eta_percent
                FROM fan_curve_points
                WHERE fan_id = ?
                ORDER BY point_order, id
                """,
                (fan_id,),
            ).fetchall()
            if len(raw_data) < 5:
                raise ValueError(f"风机 {model_id} 的性能曲线点少于 5 个")
            fans.append(make_fan_from_data(
                model_id, series, rated_rpm, (rpm_min, rpm_max),
                motor_kw, motor_count, raw_data, fan_type,
            ))
    finally:
        connection.close()

    return fans


FAN_DB = load_fan_db()

FAN_DB_MAP = {fan.model_id: fan for fan in FAN_DB}
