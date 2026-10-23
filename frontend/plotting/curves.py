# -*- coding: utf-8 -*-
"""
管道特性曲线绘图（适配 gRPC 响应数据）

移植自 v3 fan_selection/plotting/curves.py，保留完整的双工况可视化效果。
"""
import frontend.plotting.font_config  # noqa: F401

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def plot_dual_period(R_easy, R_hard, Q_f_easy, Q_f_hard, H_f_easy, H_f_hard):
    """
    绘制容易时期与困难时期两条管道特性曲线 + 工作范围矩形。

    参数均来自 gRPC SelectionResponse 的 easy/hard PeriodResult。
    """
    Qe, He, Re = Q_f_easy, H_f_easy, R_easy
    Qh, Hh, Rh = Q_f_hard, H_f_hard, R_hard

    Q_max = max(Qh, Qe) * 1.3
    Q_easy_arr = np.linspace(0, Q_max, 300)
    H_easy_arr = Re * Q_easy_arr ** 2
    Q_hard_arr = np.linspace(0, Q_max, 300)
    H_hard_arr = Rh * Q_hard_arr ** 2

    fig, ax = plt.subplots(figsize=(9, 6))

    ax.plot(Q_easy_arr, H_easy_arr,
            color='steelblue', linewidth=2.2, label=f'容易时期  H = {Re:.4f}·Q²')
    ax.plot(Q_hard_arr, H_hard_arr,
            color='darkorange', linewidth=2.2, label=f'困难时期  H = {Rh:.4f}·Q²')

    rect_x, rect_y = Qe, He
    rect_w, rect_h = Qh - Qe, Hh - He
    if rect_w > 0 and rect_h > 0:
        ax.add_patch(mpatches.FancyBboxPatch(
            (rect_x, rect_y), rect_w, rect_h,
            boxstyle="square,pad=0",
            linewidth=1.8, linestyle='--',
            edgecolor='crimson', facecolor='crimson', alpha=0.08,
            zorder=3, label='工作范围矩形',
        ))

    for Q_val, color in [(Qe, 'steelblue'), (Qh, 'darkorange')]:
        ax.axvline(Q_val, color=color, linestyle=':', linewidth=1.0, alpha=0.7)
    for H_val, color in [(He, 'steelblue'), (Hh, 'darkorange')]:
        ax.axhline(H_val, color=color, linestyle=':', linewidth=1.0, alpha=0.7)

    ax.scatter([Qe], [He], color='steelblue', s=90, zorder=6)
    ax.scatter([Qh], [Hh], color='darkorange', s=90, zorder=6)

    ax.annotate(
        f'容易时期\n({Qe:.2f}, {He:.1f})', xy=(Qe, He),
        xytext=(Qe - (Qh - Qe) * 0.55, He - (Hh - He) * 0.38),
        fontsize=9, color='steelblue',
        arrowprops=dict(arrowstyle='->', color='steelblue', lw=1.2),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='steelblue', alpha=0.9),
    )
    ax.annotate(
        f'困难时期\n({Qh:.2f}, {Hh:.1f})', xy=(Qh, Hh),
        xytext=(Qh + (Qh - Qe) * 0.12, Hh + (Hh - He) * 0.15),
        fontsize=9, color='darkorange',
        arrowprops=dict(arrowstyle='->', color='darkorange', lw=1.2),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='darkorange', alpha=0.9),
    )

    mid_Q = (Qe + Qh) / 2
    mid_H = (He + Hh) / 2
    if Qh > Qe:
        ax.annotate('', xy=(Qh, He * 0.97), xytext=(Qe, He * 0.97),
                    arrowprops=dict(arrowstyle='<->', color='crimson', lw=1.2))
        ax.text(mid_Q, He * 0.93, f'ΔQ = {Qh - Qe:.2f} m³/s',
                ha='center', fontsize=8.5, color='crimson')
    if Hh > He:
        ax.annotate('', xy=(Qh * 1.015, Hh), xytext=(Qh * 1.015, He),
                    arrowprops=dict(arrowstyle='<->', color='crimson', lw=1.2))
        ax.text(Qh * 1.022, mid_H, f'ΔH = {Hh - He:.1f} Pa',
                ha='left', fontsize=8.5, color='crimson', rotation=90, va='center')

    info = (f"容易时期  Q={Qe:.2f} m³/s  H={He:.1f} Pa  R={Re:.6f}\n"
            f"困难时期  Q={Qh:.2f} m³/s  H={Hh:.1f} Pa  R={Rh:.6f}")
    ax.text(0.02, 0.98, info, transform=ax.transAxes, fontsize=8.5,
            verticalalignment='top',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.9))

    ax.set_xlabel('风量 Q（m³/s）', fontsize=11)
    ax.set_ylabel('风压 H（Pa）', fontsize=11)
    ax.set_title('矿井通风网路管道特性曲线（容易时期 vs 困难时期）', fontsize=13)
    ax.legend(fontsize=9, loc='upper left', bbox_to_anchor=(0.02, 0.88))
    ax.grid(True, linestyle='--', alpha=0.35)
    ax.set_xlim(0, Q_max * 1.05)
    ax.set_ylim(0)
    plt.tight_layout()
    return fig
