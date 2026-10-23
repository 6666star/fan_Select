# -*- coding: utf-8 -*-
"""
矿井通风机选型系统 — Web UI (v4)
前端：Python Streamlit
后端：C++ gRPC Server

运行：
  1. 先启动 C++ 后端：backend/build/fan_selector_server.exe
  2. 再启动前端：streamlit run frontend/app.py（从 v4 根目录）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import matplotlib
matplotlib.use("Agg")

import frontend.plotting.font_config  # noqa: F401
import matplotlib.pyplot as plt
from datetime import datetime

import grpc
from frontend.generated import fan_selector_pb2 as pb
from frontend.generated import fan_selector_pb2_grpc as pb_grpc
from frontend.fan_db import FAN_DB, FAN_DB_MAP, build_fan_interpolated
from frontend.plotting.curves import plot_dual_period
from frontend.plotting.result import plot_fan_result
from frontend.config import GRPC_DEFAULT_HOST, GRPC_DEFAULT_PORT
from frontend.reporting import build_html_report, build_text_report


# ═══════════════════════════════════════════════
# gRPC 连接
# ═══════════════════════════════════════════════

@st.cache_resource
def get_grpc_channel():
    return grpc.insecure_channel(f'{GRPC_DEFAULT_HOST}:{GRPC_DEFAULT_PORT}')


def check_server():
    """检查 C++ 后端是否可用"""
    try:
        ch = get_grpc_channel()
        grpc.channel_ready_future(ch).result(timeout=2)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════

st.set_page_config(
    page_title="矿井通风机选型系统 v4",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("矿井通风机选型系统")
st.caption("v4 — C++ 后端 + Python 前端 | 双工况变频风机自动选型")


# ═══════════════════════════════════════════════
# 侧边栏：参数输入
# ═══════════════════════════════════════════════

with st.sidebar:
    st.header("矿井工况参数")

    st.subheader("容易时期")
    col1, col2 = st.columns(2)
    with col1:
        q_easy_input = st.number_input(
            "风量 (m³/s)", value=114.5,
            min_value=0.1, step=1.0, key="q_easy",
        )
    with col2:
        h_easy_input = st.number_input(
            "风压 (Pa)", value=2276.0, min_value=1.0, step=10.0, key="h_easy",
        )

    st.subheader("困难时期")
    col3, col4 = st.columns(2)
    with col3:
        q_hard_input = st.number_input(
            "风量 (m³/s)", value=129.5,
            min_value=0.1, step=1.0, key="q_hard",
        )
    with col4:
        h_hard_input = st.number_input(
            "风压 (Pa)", value=3050.2, min_value=1.0, step=10.0, key="h_hard",
        )

    with st.expander("选型系数", expanded=False):
        st.caption("风压 h_f 请输入通风网路总阻力（已含全部阻力项）")
        K = st.number_input("K — 备用系数", value=1.00, min_value=1.0, max_value=1.30, step=0.05)
        K_N = st.number_input("K_N — 功率裕量", value=1.15, min_value=1.0, max_value=1.30, step=0.05)
        eta_t = st.number_input("η_t — 传动效率", value=0.95, min_value=0.80, max_value=1.0, step=0.01)
        eta_min = st.number_input("η_min — 最低效率", value=0.70, min_value=0.50, max_value=0.90, step=0.01)

    st.divider()

    server_ok = check_server()
    if server_ok:
        st.success("C++ 后端已连接", icon="✅")
    else:
        st.error("C++ 后端未启动", icon="❌")
        st.caption("请先运行: `python scripts/run_server.py`")

    run_btn = st.button("开始计算并选型", type="primary", use_container_width=True,
                        disabled=not server_ok)


# ═══════════════════════════════════════════════
# 输入预处理
# ═══════════════════════════════════════════════

def validate_inputs():
    errors = []
    if q_easy_input <= 0 or q_hard_input <= 0:
        errors.append("风量必须为正数")
    if h_easy_input <= 0 or h_hard_input <= 0:
        errors.append("风压必须为正数")
    if q_hard_input < q_easy_input:
        errors.append("困难时期风量应 >= 容易时期风量")
    if h_hard_input < h_easy_input:
        errors.append("困难时期风压应 >= 容易时期风压")
    return (len(errors) == 0, errors)


# ═══════════════════════════════════════════════
# 主计算流程（调用 C++ 后端）
# ═══════════════════════════════════════════════

if run_btn:
    ok, errors = validate_inputs()
    if not ok:
        for e in errors:
            st.error(f"输入错误：{e}")
        st.stop()

    with st.spinner("正在通过 gRPC 调用 C++ 后端计算..."):
        try:
            channel = get_grpc_channel()
            stub = pb_grpc.FanSelectorServiceStub(channel)

            resp = stub.SelectFan(pb.FanSelectionRequest(
                airFlowEasy=q_easy_input,
                pressureEasy=h_easy_input,
                airFlowHard=q_hard_input,
                pressureHard=h_hard_input,
                reserveCoeff=K, powerMarginCoeff=K_N,
                transEfficiency=eta_t, minEfficiency=eta_min,
            ))

            st.session_state["resp"] = resp
            st.session_state["eta_min"] = eta_min
            st.session_state["selection_inputs"] = {
                "q_easy": q_easy_input, "h_easy": h_easy_input,
                "q_hard": q_hard_input, "h_hard": h_hard_input,
                "K": K, "K_N": K_N, "eta_t": eta_t, "eta_min": eta_min,
            }
            st.session_state["computed"] = True
            st.success("C++ 后端计算完成！")
        except grpc.RpcError as e:
            st.error(f"gRPC 调用失败: {e.code()} — {e.details()}")
            st.stop()


# ═══════════════════════════════════════════════
# 结果展示
# ═══════════════════════════════════════════════

if st.session_state.get("computed"):
    resp = st.session_state["resp"]
    eta_min_val = st.session_state["eta_min"]

    tab1, tab2, tab3, tab4 = st.tabs(["计算结果", "选型对比", "特性曲线", "计算过程"])

    with tab1:
        st.subheader("双工况计算结果")
        col_e, col_h = st.columns(2)
        with col_e:
            st.markdown("**容易时期**")
            st.metric("Q_f", f"{resp.easy.flowRate:.3f} m³/s")
            st.metric("H_f", f"{resp.easy.pressure:.1f} Pa")
            st.metric("R", f"{resp.easy.resistance:.6f}")
        with col_h:
            st.markdown("**困难时期**")
            st.metric("Q_f", f"{resp.hard.flowRate:.3f} m³/s")
            st.metric("H_f", f"{resp.hard.pressure:.1f} Pa")
            st.metric("R", f"{resp.hard.resistance:.6f}")
        st.divider()
        st.subheader("管道特性曲线")
        fig_pipe = plot_dual_period(
            resp.easy.resistance, resp.hard.resistance,
            resp.easy.flowRate, resp.hard.flowRate,
            resp.easy.pressure, resp.hard.pressure,
        )
        st.pyplot(fig_pipe)
        plt.close(fig_pipe)

    with tab2:
        st.subheader("选型结果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("数据库", f"{resp.totalFans} 款")
        c2.metric("初筛通过", f"{resp.totalFans - resp.screenedOut} 款")
        c3.metric("最终候选", f"{len(resp.candidates)} 款")
        c4.metric("淘汰", f"{resp.screenedOut + resp.rejectedByEff} 款")
        st.divider()

        if len(resp.candidates) == 0:
            st.warning("没有符合要求的机型。")
        else:
            for rank, cand in enumerate(resp.candidates, 1):
                is_best = (rank == 1)
                icon = "🏆" if is_best else f"#{rank}"
                with st.expander(
                    f"{icon}  {cand.modelId}  |  评分 {cand.score:.4f}  |  "
                    f"η困难={cand.efficiencyHard:.1%}  η容易={cand.efficiencyEasy:.1%}",
                    expanded=is_best,
                ):
                    info_col, vfd_col = st.columns(2)
                    with info_col:
                        st.markdown("**基本信息**")
                        st.write(f"- 型号：{cand.modelId}")
                        st.write(f"- 装机：{cand.motorCount}×{cand.motorPower:.0f}"
                                 f" = {cand.motorCount * cand.motorPower:.0f} kW")
                    with vfd_col:
                        st.markdown("**变频参数**")
                        st.write(f"- 转速比：{cand.speedRatio:.4f}")
                        st.write(f"- 功率余量：{cand.powerMargin:.1f}%")

                    st.markdown("**双工况运行参数**")
                    st.table({
                        "参数": ["Q (m³/s)", "H (Pa)", "η", "N轴 (kW)", "n (r/min)"],
                        "容易时期": [f"{cand.flowEasy:.2f}", f"{cand.pressEasy:.1f}",
                                    f"{cand.efficiencyEasy:.2%}", f"{cand.shaftPowerEasy:.1f}",
                                    f"{cand.rpmEasy:.1f}"],
                        "困难时期": [f"{cand.flowHard:.2f}", f"{cand.pressHard:.1f}",
                                    f"{cand.efficiencyHard:.2%}", f"{cand.shaftPowerHard:.1f}",
                                    f"{cand.rpmHard:.1f}"],
                    })

    with tab3:
        if len(resp.candidates) == 0:
            st.warning("没有候选机型。")
        else:
            model_options = [
                f"{'🏆 ' if i == 0 else ''}{c.modelId}（{c.score:.4f}）"
                for i, c in enumerate(resp.candidates)
            ]
            idx = st.selectbox("选择机型", range(len(model_options)),
                               format_func=lambda i: model_options[i])
            cand = resp.candidates[idx]
            fig = plot_fan_result(cand, resp.easy.resistance, resp.hard.resistance, eta_min=eta_min_val)
            st.pyplot(fig)
            plt.close(fig)

    with tab4:
        st.subheader("C++ 后端计算步骤")
        for s in resp.steps:
            st.text(s)

        st.divider()
        st.subheader("导出选型文件")
        report_inputs = st.session_state.get("selection_inputs", {
            "q_easy": resp.easy.flowRate, "h_easy": resp.easy.pressure,
            "q_hard": resp.hard.flowRate, "h_hard": resp.hard.pressure,
            "K": 1.0, "K_N": 1.15, "eta_t": 0.95, "eta_min": eta_min_val,
        })
        generated_at = datetime.now()
        file_stamp = generated_at.strftime("%Y%m%d_%H%M%S")
        html_report = build_html_report(resp, report_inputs, generated_at)
        text_report = build_text_report(resp, report_inputs, generated_at)
        download_col1, download_col2 = st.columns(2)
        with download_col1:
            st.download_button(
                "下载选型报告（HTML）",
                data=html_report.encode("utf-8"),
                file_name=f"fan_selection_report_{file_stamp}.html",
                mime="text/html",
                use_container_width=True,
            )
        with download_col2:
            st.download_button(
                "下载完整计算步骤（TXT）",
                data=("\ufeff" + text_report).encode("utf-8"),
                file_name=f"fan_selection_steps_{file_stamp}.txt",
                mime="text/plain",
                use_container_width=True,
            )

else:
    st.info("请在左侧输入参数，然后点击「开始计算并选型」。")
    if not check_server():
        st.warning("请先启动 C++ 后端：`python scripts/run_server.py`")
    st.divider()
    st.subheader(f"风机数据库（{len(FAN_DB)} 款）")
    db_data = {"型号": [], "装机 (kW)": [], "Q 范围": [], "H 范围": [], "R²(H)": [], "R²(η)": []}
    for fan in FAN_DB:
        fi = build_fan_interpolated(fan)
        db_data["型号"].append(fan.model_id)
        db_data["装机 (kW)"].append(f"{fan.motor_count}×{fan.motor_kw:.0f} = {fan.total_motor_kw:.0f}")
        db_data["Q 范围"].append(f"{fan.Q_min:.1f} ~ {fan.Q_max:.1f}")
        db_data["H 范围"].append(f"{fan.H_min:.0f} ~ {fan.H_max:.0f}")
        db_data["R²(H)"].append(f"{fi.R2_H:.4f}")
        db_data["R²(η)"].append(f"{fi.R2_eta:.4f}")
    st.table(db_data)
