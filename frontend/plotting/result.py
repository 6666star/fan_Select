# -*- coding: utf-8 -*-
"""
推荐风机特性曲线综合绘图（适配 gRPC 响应数据）

移植自 v3 fan_selection/plotting/result.py，保留完整的三面板布局：
  ① H-Q 主图（额定 + 变频工况 + 管道阻力线 + 相似律族曲线）
  ② η 等效率线图（二维效率场 + 高斯平滑）
  ③ N-Q 轴功率特性曲线
"""
import frontend.plotting.font_config  # noqa: F401

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from scipy.optimize import brentq
from scipy.ndimage import gaussian_filter

class _FanInterpolated:
    """从 proto CurvePoint 数据构建的插值对象"""
    def __init__(self, curve_points, H_deg=2, eta_deg=4):
        Q = np.array([p.q for p in curve_points])
        H = np.array([p.h for p in curve_points])
        eta = np.array([p.eta / 100.0 if p.eta > 1.0 else p.eta for p in curve_points])
        self.Q_min = Q.min()
        self.Q_max = Q.max()
        self.H_spline = np.poly1d(np.polyfit(Q, H, H_deg))
        self.eta_spline = np.poly1d(np.polyfit(Q, eta, eta_deg))


BRENTQ_SCAN_POINTS = 500
BRENTQ_XTOL = 1e-6
BRENTQ_RTOL = 1e-8


def _fan_HQ_at_ratio(fi, n_ratio, n_pts=300):
    Q0 = np.linspace(fi.Q_min, fi.Q_max, n_pts)
    H0 = np.maximum(fi.H_spline(Q0), 0.0)
    return Q0 * n_ratio, H0 * n_ratio ** 2


def _fan_eta_at_ratio(fi, n_ratio, n_pts=300):
    Q0 = np.linspace(fi.Q_min, fi.Q_max, n_pts)
    eta = np.clip(fi.eta_spline(Q0), 0.0, 1.0)
    return Q0 * n_ratio, eta


def _fan_shaft_power_at_ratio(fi, n_ratio, eta_t=0.95, n_pts=300):
    Q0 = np.linspace(fi.Q_min, fi.Q_max, n_pts)
    H0 = np.maximum(fi.H_spline(Q0), 0.01)
    e0 = np.clip(fi.eta_spline(Q0), 0.01, 1.0)
    N0 = Q0 * H0 / (1000.0 * e0 * eta_t)
    return Q0 * n_ratio, N0 * n_ratio ** 3


def _solve_base_point(fi, R):
    def f(Q):
        return float(fi.H_spline(Q)) - R * Q ** 2
    Q_scan = np.linspace(fi.Q_max, fi.Q_min, BRENTQ_SCAN_POINTS)
    f_scan = np.array([f(q) for q in Q_scan])
    for i in range(len(f_scan) - 1):
        if f_scan[i] * f_scan[i + 1] < 0:
            a, b = sorted([Q_scan[i], Q_scan[i + 1]])
            try:
                return brentq(f, a, b, xtol=BRENTQ_XTOL, rtol=BRENTQ_RTOL)
            except ValueError:
                continue
    return None


def _build_eta_field(fi, Q_grid, H_grid, r_min=0.50, r_max=1.0):
    Q0_arr = np.linspace(fi.Q_min, fi.Q_max, 3000)
    H0_arr = fi.H_spline(Q0_arr).astype(float)
    eta0_arr = np.clip(fi.eta_spline(Q0_arr), 0.0, 1.0).astype(float)
    R0_arr = np.where(Q0_arr > 1e-6, H0_arr / Q0_arr ** 2, np.inf)

    R_pt = np.where(Q_grid > 1e-6, H_grid / Q_grid ** 2, np.inf)
    R_flat = R_pt.ravel()

    idx_flat = np.searchsorted(-R0_arr, -R_flat).clip(0, len(R0_arr) - 1)
    idx_lo = np.clip(idx_flat - 1, 0, len(R0_arr) - 1)
    idx_hi = np.clip(idx_flat, 0, len(R0_arr) - 1)
    d_lo = np.abs(R0_arr[idx_lo] - R_flat)
    d_hi = np.abs(R0_arr[idx_hi] - R_flat)
    best_idx = np.where(d_lo < d_hi, idx_lo, idx_hi)

    Q0_match = Q0_arr[best_idx]
    eta_match = eta0_arr[best_idx]
    R0_match = R0_arr[best_idx]

    Q_flat = Q_grid.ravel()
    r_ratio = np.where(Q0_match > 1e-6, Q_flat / Q0_match, 999.0)
    rel_err = np.abs(R0_match - R_flat) / np.maximum(R_flat, 1e-6)

    valid = ((r_ratio >= r_min) & (r_ratio <= r_max) &
             (rel_err < 0.02) & (Q_flat > 0) & (H_grid.ravel() > 0))

    eta_field = np.full(Q_grid.shape, np.nan)
    eta_flat = eta_field.ravel()
    eta_flat[valid] = eta_match[valid]
    return eta_field


def plot_fan_result(cand_proto, R_easy, R_hard, eta_min=0.70, eta_t=0.95):
    """
    绘制推荐风机 3 面板综合特性曲线图。

    参数：
        cand_proto : gRPC CandidateFan 消息对象
        R_easy     : 容易时期管道阻力系数
        R_hard     : 困难时期管道阻力系数
        eta_min    : 最低效率要求
        eta_t      : 传动效率
    """
    model_id = cand_proto.modelId
    plot = cand_proto.plotData
    if len(plot.curvePoints) == 0:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, f'型号 {model_id} 无曲线数据',
                ha='center', va='center', fontsize=14)
        return fig

    fi = _FanInterpolated(plot.curvePoints)
    n0 = plot.ratedRpm
    n_easy = cand_proto.rpmEasy
    n_hard = cand_proto.rpmHard
    r_easy = n_easy / n0
    r_hard = n_hard / n0

    Re, Rh = R_easy, R_hard
    Qe, He = cand_proto.flowEasy, cand_proto.pressEasy
    Qh, Hh = cand_proto.flowHard, cand_proto.pressHard

    u_easy = cand_proto.baseFlowEasy if cand_proto.baseFlowEasy > 0 else None
    H_u_easy = cand_proto.basePressEasy if u_easy else None
    u_hard = cand_proto.baseFlowHard if cand_proto.baseFlowHard > 0 else None
    H_u_hard = cand_proto.basePressHard if u_hard else None

    Q_rated, H_rated = _fan_HQ_at_ratio(fi, 1.0)
    Q_at_easy, H_at_easy = _fan_HQ_at_ratio(fi, r_easy)
    Q_at_hard, H_at_hard = _fan_HQ_at_ratio(fi, r_hard)
    family_ratios = np.arange(0.6, 0.91, 0.1)

    Q_N_r, N_r = _fan_shaft_power_at_ratio(fi, 1.0, eta_t)
    Q_N_easy, N_easy_curve = _fan_shaft_power_at_ratio(fi, r_easy, eta_t)
    Q_N_hard, N_hard_curve = _fan_shaft_power_at_ratio(fi, r_hard, eta_t)

    Q_plot_max = fi.Q_max * 1.15
    Q_pipe = np.linspace(0, Q_plot_max, 300)
    H_pipe_easy = Re * Q_pipe ** 2
    H_pipe_hard = Rh * Q_pipe ** 2
    H_plot_max = max(H_rated) * 1.12

    # η 场
    q_lo = max(fi.Q_min * 0.20, 1.0)
    q_hi = fi.Q_max * 1.20
    h_hi = H_plot_max * 1.2
    nq, nh = 400, 400
    q_arr = np.linspace(q_lo, q_hi, nq)
    h_arr = np.linspace(1.0, h_hi, nh)
    Q_grid, H_grid = np.meshgrid(q_arr, h_arr)
    fan_r_min = plot.rpmMin / n0
    fan_r_max = plot.rpmMax / n0
    eta_field = _build_eta_field(fi, Q_grid, H_grid, r_min=fan_r_min, r_max=fan_r_max)

    valid_mask = ~np.isnan(eta_field)
    eta_filled = np.where(valid_mask, eta_field, 0.0)
    weight = valid_mask.astype(float)
    eta_blurred = gaussian_filter(eta_filled, sigma=4.0)
    weight_blurred = gaussian_filter(weight, sigma=4.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        eta_smooth = np.where(weight_blurred > 0.01,
                              eta_blurred / weight_blurred, np.nan)

    # 画布
    fig = plt.figure(figsize=(15, 9))
    N_installed = cand_proto.motorCount * cand_proto.motorPower
    fig.suptitle(
        f"推荐风机特性曲线 — {model_id}  "
        f"（{cand_proto.motorCount}×{cand_proto.motorPower:.0f} kW，额定 {n0:.0f} r/min）",
        fontsize=14, fontweight='bold', y=0.98,
    )
    gs = gridspec.GridSpec(2, 2, figure=fig, width_ratios=[1.55, 1],
                           hspace=0.38, wspace=0.28,
                           left=0.07, right=0.97, top=0.93, bottom=0.08)
    ax_hq = fig.add_subplot(gs[:, 0])
    ax_eta = fig.add_subplot(gs[0, 1])
    ax_nq = fig.add_subplot(gs[1, 1])

    # ── ① H-Q 主图 ──
    for r in family_ratios:
        Qf, Hf = _fan_HQ_at_ratio(fi, r)
        ax_hq.plot(Qf, Hf, color='#cccccc', linewidth=0.9, linestyle='--', zorder=1)
        ax_hq.text(Qf[-1] * 1.005, Hf[-1], f'{r*n0:.0f}', fontsize=7, color='#aaaaaa', va='center')

    ax_hq.plot(Q_rated, H_rated, color='#222222', linewidth=2.5,
               label=f'额定转速  {n0:.0f} r/min', zorder=4)
    ax_hq.plot(Q_at_easy, H_at_easy, color='steelblue', linewidth=2.0, linestyle='-.',
               label=f'容易时期  {n_easy:.0f} r/min  ({r_easy:.3f}×)', zorder=4)
    ax_hq.plot(Q_at_hard, H_at_hard, color='darkorange', linewidth=2.0, linestyle='-.',
               label=f'困难时期  {n_hard:.0f} r/min  ({r_hard:.3f}×)', zorder=4)
    ax_hq.plot(Q_pipe, H_pipe_easy, color='steelblue', linewidth=1.5, linestyle=':',
               label=f'管道阻力（容易）R={Re:.5f}', zorder=3)
    ax_hq.plot(Q_pipe, H_pipe_hard, color='darkorange', linewidth=1.5, linestyle=':',
               label=f'管道阻力（困难）R={Rh:.5f}', zorder=3)

    if u_easy:
        ax_hq.scatter([u_easy], [H_u_easy], marker='^', s=90, color='steelblue', zorder=6,
                      label=f'基准点 u_easy={u_easy:.1f}')
        ax_hq.annotate(f'u_e={u_easy:.1f}', xy=(u_easy, H_u_easy),
                        xytext=(u_easy - 12, H_u_easy + 180),
                        fontsize=8, color='steelblue',
                        arrowprops=dict(arrowstyle='->', color='steelblue', lw=0.9))
    if u_hard:
        ax_hq.scatter([u_hard], [H_u_hard], marker='^', s=90, color='darkorange', zorder=6,
                      label=f'基准点 u_hard={u_hard:.1f}')
        ax_hq.annotate(f'u_h={u_hard:.1f}', xy=(u_hard, H_u_hard),
                        xytext=(u_hard + 3, H_u_hard + 180),
                        fontsize=8, color='darkorange',
                        arrowprops=dict(arrowstyle='->', color='darkorange', lw=0.9))

    ax_hq.scatter([Qe], [He], color='steelblue', s=130, marker='o', zorder=7)
    ax_hq.scatter([Qh], [Hh], color='darkorange', s=130, marker='o', zorder=7)

    ax_hq.annotate(
        f'容易时期工作点\n({Qe:.1f} m³/s, {He:.0f} Pa)\nη={cand_proto.efficiencyEasy:.2%}',
        xy=(Qe, He), xytext=(Qe - 30, He - 650), fontsize=8.5, color='steelblue',
        arrowprops=dict(arrowstyle='->', color='steelblue', lw=1.1),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#e8f4fd', edgecolor='steelblue', alpha=0.92),
    )
    ax_hq.annotate(
        f'困难时期工作点\n({Qh:.1f} m³/s, {Hh:.0f} Pa)\nη={cand_proto.efficiencyHard:.2%}',
        xy=(Qh, Hh), xytext=(Qh + 6, Hh + 350), fontsize=8.5, color='darkorange',
        arrowprops=dict(arrowstyle='->', color='darkorange', lw=1.1),
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff4e6', edgecolor='darkorange', alpha=0.92),
    )

    for Q_val, H_val, col in [(Qe, He, 'steelblue'), (Qh, Hh, 'darkorange')]:
        ax_hq.axvline(Q_val, color=col, linestyle=':', linewidth=0.9, alpha=0.5)
        ax_hq.axhline(H_val, color=col, linestyle=':', linewidth=0.9, alpha=0.5)

    ax_hq.set_xlabel('风量 Q（m³/s）', fontsize=11)
    ax_hq.set_ylabel('全压 H（Pa）', fontsize=11)
    ax_hq.set_title('H-Q 特性曲线（额定 + 变频工况 + 管道阻力线）', fontsize=11)
    ax_hq.legend(fontsize=7.5, loc='upper right', ncol=1, framealpha=0.9, edgecolor='#cccccc')
    ax_hq.grid(True, linestyle='--', alpha=0.3)
    ax_hq.set_xlim(max(0, fi.Q_min * r_easy * 0.85), Q_plot_max)
    ax_hq.set_ylim(0, H_plot_max)

    n_ratio_display = cand_proto.speedRatio
    info = (f"转速比：{n_ratio_display:.4f}\n"
            f"容易：{n_easy:.0f} r/min（{r_easy:.3f}×）\n"
            f"困难：{n_hard:.0f} r/min（{r_hard:.3f}×）")
    ax_hq.text(0.02, 0.98, info, transform=ax_hq.transAxes, fontsize=8.2, va='top',
               bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow', alpha=0.92))

    # ── ② η 等效率线 ──
    eta_pct = eta_smooth * 100
    levels = np.arange(35, 90, 5)
    cf = ax_eta.contourf(Q_grid, H_grid, eta_pct, levels=levels, cmap='RdYlGn',
                          alpha=0.45, zorder=0, extend='both')
    cs = ax_eta.contour(Q_grid, H_grid, eta_pct, levels=levels, colors='#555555',
                         linewidths=0.8, linestyles='-', zorder=1)
    ax_eta.clabel(cs, inline=True, fontsize=7, fmt='%d%%')
    cs_min = ax_eta.contour(Q_grid, H_grid, eta_pct, levels=[eta_min * 100],
                             colors='crimson', linewidths=1.8, linestyles='--', zorder=2)
    ax_eta.clabel(cs_min, inline=True, fontsize=8, fmt=f'η_min={eta_min*100:.0f}%%')

    ax_eta.plot(Q_rated, H_rated, color='#222222', linewidth=1.8, alpha=0.7,
                label=f'{n0:.0f} r/min', zorder=3)
    Q_rmin, H_rmin = _fan_HQ_at_ratio(fi, fan_r_min)
    ax_eta.plot(Q_rmin, H_rmin, color='#222222', linewidth=1.8, alpha=0.7,
                label=f'{plot.rpmMin:.0f} r/min', zorder=3)

    ax_eta.scatter([Qe], [He], color='steelblue', s=100, marker='o',
                   edgecolors='white', linewidths=1.5, zorder=5)
    ax_eta.scatter([Qh], [Hh], color='darkorange', s=100, marker='o',
                   edgecolors='white', linewidths=1.5, zorder=5)
    ax_eta.annotate(f'容易 η={cand_proto.efficiencyEasy:.1%}', xy=(Qe, He),
                    xytext=(Qe - (q_hi - q_lo) * 0.25, He - (h_hi) * 0.12),
                    fontsize=8, color='steelblue', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='steelblue', lw=1.0),
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                              edgecolor='steelblue', alpha=0.9), zorder=6)
    ax_eta.annotate(f'困难 η={cand_proto.efficiencyHard:.1%}', xy=(Qh, Hh),
                    xytext=(Qh + (q_hi - q_lo) * 0.05, Hh + h_hi * 0.08),
                    fontsize=8, color='darkorange', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='darkorange', lw=1.0),
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                              edgecolor='darkorange', alpha=0.9), zorder=6)

    cbar = fig.colorbar(cf, ax=ax_eta, pad=0.03, shrink=0.92)
    cbar.set_label('η（%）', fontsize=9)
    ax_eta.set_xlabel('风量 Q（m³/s）', fontsize=10)
    ax_eta.set_ylabel('全压 H（Pa）', fontsize=10)
    ax_eta.set_title('η(Q, H) 等效率线图', fontsize=10)
    ax_eta.legend(fontsize=7, loc='upper right')
    ax_eta.grid(True, linestyle='--', alpha=0.2)
    ax_eta.set_xlim(max(fi.Q_min * fan_r_min * 0.85, 1.0), fi.Q_max * fan_r_max * 1.05)
    ax_eta.set_ylim(0, max(H_rated) * 1.05)

    # ── ③ N-Q 轴功率 ──
    for r in family_ratios:
        Qf, Nf = _fan_shaft_power_at_ratio(fi, r, eta_t)
        ax_nq.plot(Qf, Nf, color='#dddddd', linewidth=0.8, zorder=1)

    ax_nq.plot(Q_N_r, N_r, color='#222222', linewidth=2.2,
               label=f'{n0:.0f} r/min（额定）', zorder=4)
    ax_nq.plot(Q_N_easy, N_easy_curve, color='steelblue', linewidth=1.8, linestyle='-.',
               label=f'{n_easy:.0f} r/min（容易）', zorder=4)
    ax_nq.plot(Q_N_hard, N_hard_curve, color='darkorange', linewidth=1.8, linestyle='-.',
               label=f'{n_hard:.0f} r/min（困难）', zorder=4)

    ax_nq.axhline(N_installed, color='crimson', linewidth=1.3, linestyle='--',
                  label=f'装机 {N_installed:.0f} kW', alpha=0.8)

    N_shaft_easy = cand_proto.shaftPowerEasy
    N_shaft_hard = cand_proto.shaftPowerHard
    ax_nq.scatter([Qe], [N_shaft_easy], color='steelblue', s=90, zorder=6)
    ax_nq.scatter([Qh], [N_shaft_hard], color='darkorange', s=90, zorder=6)
    ax_nq.annotate(f'{N_shaft_easy:.0f} kW', xy=(Qe, N_shaft_easy),
                   xytext=(Qe - 12, N_shaft_easy + N_installed * 0.04),
                   fontsize=8, color='steelblue')
    ax_nq.annotate(f'{N_shaft_hard:.0f} kW', xy=(Qh, N_shaft_hard),
                   xytext=(Qh + 2, N_shaft_hard + N_installed * 0.04),
                   fontsize=8, color='darkorange')

    ax_nq.set_xlabel('风量 Q（m³/s）', fontsize=10)
    ax_nq.set_ylabel('轴功率 N（kW）', fontsize=10)
    ax_nq.set_title('N-Q 轴功率特性曲线', fontsize=10)
    ax_nq.legend(fontsize=7.5, loc='upper right')
    ax_nq.grid(True, linestyle='--', alpha=0.3)
    ax_nq.set_xlim(max(0, fi.Q_min * r_easy * 0.85), fi.Q_max * 1.05)
    ax_nq.set_ylim(0, N_installed * 1.35)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return fig
