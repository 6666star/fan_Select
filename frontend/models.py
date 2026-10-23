# -*- coding: utf-8 -*-
"""
前端数据结构（仅用于绘图）

这些类与 C++ backend 的 models.hpp 对应，
但仅在前端的 plotting 模块中使用，不参与计算。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FanCurvePoint:
    Q:   float
    H:   float
    eta: float


@dataclass
class FanModel:
    model_id:      str
    series:        str
    fan_type:      str
    rated_rpm:     float
    rpm_range:     tuple
    motor_kw:      float
    motor_count:   int
    curve_points:  list

    @property
    def total_motor_kw(self) -> float:
        return self.motor_kw * self.motor_count

    @property
    def Q_min(self) -> float:
        return self.curve_points[0].Q

    @property
    def Q_max(self) -> float:
        return self.curve_points[-1].Q

    @property
    def H_max(self) -> float:
        return max(p.H for p in self.curve_points)

    @property
    def H_min(self) -> float:
        return min(p.H for p in self.curve_points)


@dataclass
class FanInterpolated:
    fan:        FanModel
    H_spline:   object
    eta_spline: object
    Q_min:      float
    Q_max:      float
    R2_H:       float = 0.0
    R2_eta:     float = 0.0
