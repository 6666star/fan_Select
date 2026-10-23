# -*- coding: utf-8 -*-
"""Generate human-readable fan-selection reports from a gRPC response."""

import base64
import io
import mimetypes
import re
from datetime import datetime
from html import escape
from pathlib import Path

import matplotlib.pyplot as plt

from frontend.plotting.result import plot_fan_result


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def explain_step(step):
    """Translate a backend diagnostic line into an understandable Chinese sentence."""
    text = step.strip()
    exact = {
        "fan selection start": "开始风机选型：读取容易时期和困难时期的目标工况。",
        "no intersection found": "未找到风机额定性能曲线与管网阻力曲线的交点，无法形成有效工作点。",
        "reject: no curve intersection": "淘汰原因：至少一个工况没有有效曲线交点。",
        "reject: easy rpm out of range": "淘汰原因：容易时期所需转速超出该风机允许调速范围。",
        "reject: hard rpm out of range": "淘汰原因：困难时期所需转速超出该风机允许调速范围。",
        "reject: efficiency below threshold": "淘汰原因：容易时期或困难时期的效率低于设定下限。",
        "reject: installed motor power is insufficient": "淘汰原因：配置电机总功率小于计算所需功率。",
    }
    if text in exact:
        return exact[text]
    if text.startswith("--- ") and text.endswith(" ---"):
        return f"校核风机型号：{text[4:-4]}。"

    replacements = [
        (r"^easy Q=([^,]+), H=([^,]+), R=(.+)$", r"容易时期目标工况：风量 Q=\1，风压 H=\2，管网阻力系数 R=\3。"),
        (r"^hard Q=([^,]+), H=([^,]+), R=(.+)$", r"困难时期目标工况：风量 Q=\1，风压 H=\2，管网阻力系数 R=\3。"),
        (r"^\[screen\] easy Q=([^,]+), H=(.+)$", r"初筛容易时期能力范围：要求风量 Q=\1，风压 H=\2。"),
        (r"^\[screen\] hard Q=([^,]+), H=(.+)$", r"初筛困难时期能力范围：要求风量 Q=\1，风压 H=\2。"),
        (r"^\[screen\] fan count=(\d+)$", r"本次共有 \1 台启用风机进入初筛。"),
        (r"^\[screen result\] passed=(\d+), rejected=(\d+)$", r"初筛结果：\1 台通过，\2 台淘汰。"),
        (r"^intersection Q=([^,]+), H=(.+)$", r"求得额定曲线与管网曲线交点：基准风量 Q=\1，基准风压 H=\2；随后根据风机相似定律换算目标转速。"),
        (r"^easy eta=([^,]+), shaft=(.+)$", r"容易时期校核：风机效率 η=\1，轴功率 N=\2。轴功率按 N=QH/(1000·η·η_t) 计算。"),
        (r"^hard eta=([^,]+), shaft=(.+)$", r"困难时期校核：风机效率 η=\1，轴功率 N=\2。轴功率按 N=QH/(1000·η·η_t) 计算。"),
        (r"^motor required >= (.+)$", r"电机容量校核：考虑功率余量系数后，装机总功率应不小于 \1。"),
        (r"^score hard=([^,]+), easy=([^,]+), motor=([^,]+), total=(.+)$", r"综合评分：困难时期效率分=\1，容易时期效率分=\2，电机利用率分=\3，最终得分=\4。权重分别为55%、35%和10%。"),
        (r"^pass: score=(.+)$", r"该风机通过全部校核，综合评分为 \1。"),
        (r"^summary total=(\d+), screened_out=(\d+), rejected_after_screen=(\d+), candidates=(\d+)$", r"选型汇总：共 \1 台，初筛淘汰 \2 台，详细校核淘汰 \3 台，最终候选 \4 台。"),
    ]
    for pattern, replacement in replacements:
        if re.match(pattern, text):
            return re.sub(pattern, replacement, text)

    if text.startswith("pass "):
        return f"初筛通过：{text[5:]} 的风量、风压和最低转速能力满足初步要求。"
    if text.startswith("reject "):
        model_reason = text[7:]
        reason_map = {
            "Q_max < hard Q": "最大风量小于困难时期要求",
            "H_max < hard H": "最大风压小于困难时期要求",
            "Q_min > hard Q": "最小风量大于困难时期要求",
            "minimum VFD Q > easy Q": "最低允许转速下的风量仍高于容易时期要求",
        }
        for english, chinese in reason_map.items():
            model_reason = model_reason.replace(english, chinese)
        return f"初筛淘汰：{model_reason}。"
    return f"计算记录：{text}"


def _candidate_rows(resp):
    rows = []
    for rank, c in enumerate(resp.candidates, 1):
        rows.append(
            f"<tr><td>{rank}</td><td>{escape(c.modelId)}</td><td>{c.ratedRpm:.0f}</td>"
            f"<td>{c.motorCount}×{c.motorPower:.0f}</td><td>{c.efficiencyEasy:.2%}</td>"
            f"<td>{c.efficiencyHard:.2%}</td><td>{c.rpmEasy:.1f}</td><td>{c.rpmHard:.1f}</td>"
            f"<td>{c.shaftPowerEasy:.1f}</td><td>{c.shaftPowerHard:.1f}</td>"
            f"<td>{c.requiredPower:.1f}</td><td>{c.powerMargin:.1f}%</td><td>{c.score:.4f}</td>"
            f"<td>{c.bladeAngleDeg:.1f}°</td>"
            f"<td>{c.railWidthMm / 1000.0:.2f} m</td>"
            f"<td>{escape(c.imagePath) if c.imagePath else '未录入'}</td></tr>"
        )
    return "".join(rows) or '<tr><td colspan="16">没有符合条件的候选风机</td></tr>'


def _recommended_html(resp):
    if not resp.candidates:
        return "<p>本次计算没有符合全部条件的推荐机型。</p>"
    c = resp.candidates[0]
    rail = f"{c.railWidthMm / 1000.0:.2f} m" if c.railWidthMm > 0 else "未录入"
    image_html = _embedded_image_html(c.imagePath, c.modelId)
    poleCount = _motor_pole_count(c.motorModel)
    ratedFrequency = _frequency(c.ratedRpm, poleCount)
    easyFrequency = _frequency(c.rpmEasy, poleCount)
    hardFrequency = _frequency(c.rpmHard, poleCount)
    fanCurveHtml = _figure_html(
        plot_fan_result(c, resp.easy.resistance, resp.hard.resistance),
        "推荐风机综合特性曲线",
    )
    return f"""<p>按照综合评分从高到低排序，推荐采用 <strong>{escape(c.modelId)}</strong>。</p>
    <h3>风机的基本信息</h3>
    {image_html}
    <table>
    <tr><th>制造厂家</th><td>{escape(c.manufacturer or '未录入')}</td><th>产品名称</th><td>{escape(c.productName or '未录入')}</td></tr>
    <tr><th>产品型号规格</th><td>{escape(c.productSpec or c.modelId)}</td><th>电动机型号</th><td>{escape(c.motorModel or '未录入')}</td></tr>
    <tr><th>电机配置</th><td>{c.motorCount}×{c.motorPower:.0f} = {c.motorCount * c.motorPower:.0f} kW</td>
        <th>额定转速（频率）</th><td>{c.ratedRpm:.0f} r/min（{ratedFrequency}）</td></tr>
    <tr><th>抽出式轨道宽度</th><td>{rail}</td><th>出厂编号</th><td>{escape(c.factoryNo or '未录入')}</td></tr>
    </table>
    <h3>风机的特性曲线图</h3>{fanCurveHtml}
    <h3>工况点信息</h3>
    <table><tr><th>工况</th><th>风量</th><th>风压</th><th>效率</th><th>转速</th><th>频率</th><th>扇叶角度</th><th>轴功率</th></tr>
    <tr><td>容易时期</td><td>{c.flowEasy:.2f} m³/s</td><td>{c.pressEasy:.1f} Pa</td><td>{c.efficiencyEasy:.2%}</td>
        <td>{c.rpmEasy:.1f} r/min</td><td>{easyFrequency}</td><td>{c.bladeAngleDeg:.1f}°</td><td>{c.shaftPowerEasy:.1f} kW</td></tr>
    <tr><td>困难时期</td><td>{c.flowHard:.2f} m³/s</td><td>{c.pressHard:.1f} Pa</td><td>{c.efficiencyHard:.2%}</td>
        <td>{c.rpmHard:.1f} r/min</td><td>{hardFrequency}</td><td>{c.bladeAngleDeg:.1f}°</td><td>{c.shaftPowerHard:.1f} kW</td></tr></table>
    <p>频率按同步转速关系 <code>f=n×P/120</code> 计算，其中 P={poleCount if poleCount else '未知'} 为电机极数。</p>"""


def _motor_pole_count(motorModel):
    match = re.search(r"-(\d+)$", motorModel or "")
    return int(match.group(1)) if match else None


def _frequency(rpm, poleCount):
    return f"{rpm * poleCount / 120.0:.2f} Hz" if poleCount else "无法计算"


def _figure_html(figure, title):
    buffer = io.BytesIO()
    try:
        figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    finally:
        plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f'<div class="report-figure"><img src="data:image/png;base64,{encoded}" alt="{escape(title)}"></div>'


def _embedded_image_html(image_path, model_id):
    """Embed an existing data-relative image so the downloaded HTML is portable."""
    if not image_path:
        return '<p class="image-note">风机图片：数据库未录入图片路径。</p>'
    candidate = (DATA_DIR / image_path).resolve()
    try:
        candidate.relative_to(DATA_DIR.resolve())
    except ValueError:
        return '<p class="image-note">风机图片：图片路径超出项目 data 目录，已拒绝读取。</p>'
    if not candidate.is_file():
        return f'<p class="image-note">风机图片：未找到文件 {escape(image_path)}。</p>'
    mime = mimetypes.guess_type(candidate.name)[0] or "image/jpeg"
    encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
    return (
        '<div class="fan-image"><p><b>推荐风机图片</b></p>'
        f'<img src="data:{mime};base64,{encoded}" alt="{escape(model_id)}"></div>'
    )


def _calculation_groups(resp, inputs):
    """Arrange backend records into four report-oriented calculation stages."""
    groups = {
        "工况点计算": [
            f"容易时期选型风量：Q_f=K·Q₁={inputs['K']:.3f}×{inputs['q_easy']:.3f}={resp.easy.flowRate:.3f} m³/s。",
            f"容易时期管网阻力系数：R=H_f/Q_f²={resp.easy.pressure:.1f}/{resp.easy.flowRate:.3f}²={resp.easy.resistance:.6f}。",
            f"困难时期选型风量：Q_f=K·Q₁={inputs['K']:.3f}×{inputs['q_hard']:.3f}={resp.hard.flowRate:.3f} m³/s。",
            f"困难时期管网阻力系数：R=H_f/Q_f²={resp.hard.pressure:.1f}/{resp.hard.flowRate:.3f}²={resp.hard.resistance:.6f}。",
            "两个时期的管网特性均按 H=R·Q² 建立，目标风量和风压作为最终工作点。",
        ],
        "风机初筛": [],
        "风机优选": [],
        "最后的推荐": [],
    }
    for raw in resp.steps:
        text = raw.strip()
        explained = explain_step(raw)
        if text == "fan selection start" or text.startswith("easy Q=") or text.startswith("hard Q="):
            continue  # 已由工况点公式完整表达
        if (text.startswith("[screen]") or text.startswith("[screen result]")
                or text.startswith("pass ") or text.startswith("reject ")):
            groups["风机初筛"].append(explained)
        elif text.startswith("summary "):
            groups["最后的推荐"].append(explained)
        else:
            groups["风机优选"].append(explained)

    if resp.candidates:
        best = resp.candidates[0]
        groups["最后的推荐"].append(
            f"候选风机按综合评分降序排列，{best.modelId} 得分 {best.score:.4f}，因此确定为本次推荐型号。"
        )
    else:
        groups["最后的推荐"].append("全部风机均未通过完整校核，本次没有可推荐型号。")
    return groups


def build_html_report(resp, inputs, generated_at=None):
    generated_at = generated_at or datetime.now()
    grouped_steps = _calculation_groups(resp, inputs)
    step_cards = "".join(
        f'<section class="stage"><h3>{escape(title)}</h3>'
        + "".join(
            f'<div class="step"><p>{escape(content)}</p></div>'
            for content in contents
        )
        + "</section>"
        for title, contents in grouped_steps.items()
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>矿井通风机选型计算书</title><style>
@page{{size:A4 portrait;margin:14mm 15mm 16mm 15mm}}
*{{box-sizing:border-box}}
html,body{{width:100%;padding:0}}
body{{font-family:"Microsoft YaHei",Arial,sans-serif;color:#222;width:180mm;max-width:180mm;margin:12mm auto;line-height:1.55;font-size:10.5pt}}
h1{{text-align:center;font-size:20pt;margin:0 0 6mm}} h2{{border-bottom:2px solid #3b82f6;padding-bottom:5px;margin:9mm 0 4mm;font-size:15pt;break-after:avoid-page}}
h3{{background:#eaf2ff;border-left:5px solid #3b82f6;padding:7px 10px;margin:6mm 0 3mm;font-size:12pt;break-after:avoid-page}}
table{{width:100%;max-width:100%;table-layout:fixed;border-collapse:collapse;margin:3mm 0;font-size:9pt;break-inside:avoid-page}}
th,td{{border:1px solid #bbb;padding:5px 4px;text-align:center;overflow-wrap:anywhere;word-break:break-word}}
th{{background:#eef4fb}} .meta{{text-align:center;color:#666}} .step{{border-left:4px solid #4c8bf5;background:#f7f9fc;padding:8px 14px;margin:9px 0}}
.step p{{margin:3px 0}} .notice{{background:#fff7df;border-left:4px solid #e5a100;padding:10px 14px;margin-top:24px}}
.fan-image{{text-align:center;margin:5mm 0;break-inside:avoid-page}} .fan-image img{{display:block;max-width:100%;max-height:105mm;width:auto;height:auto;margin:0 auto;border:1px solid #ccc;padding:4px}}
.report-figure{{text-align:center;margin:5mm 0;break-inside:avoid-page}} .report-figure img{{display:block;width:100%;max-width:100%;height:auto;max-height:230mm;object-fit:contain;margin:0 auto;border:1px solid #ccc;padding:4px}}
.image-note{{color:#777}}
section.stage{{break-inside:auto}} p{{orphans:3;widows:3}}
@media print{{html,body{{width:180mm;max-width:180mm;margin:0}} body{{print-color-adjust:exact;-webkit-print-color-adjust:exact}} .step{{break-inside:avoid-page}} .notice{{break-inside:avoid-page}}}}</style></head><body>
<h1>矿井通风机选型计算书</h1><p class="meta">软件版本：V7　生成时间：{generated_at:%Y-%m-%d %H:%M:%S}</p>
<h2>1. 输入参数与管网计算</h2>
<h3>输入参数</h3>
<table><tr><th>参数</th><th>容易时期</th><th>困难时期</th></tr>
<tr><td>需求风量（m³/s）</td><td>{inputs['q_easy']:.3f}</td><td>{inputs['q_hard']:.3f}</td></tr>
<tr><td>风压（Pa）</td><td>{inputs['h_easy']:.1f}</td><td>{inputs['h_hard']:.1f}</td></tr></table>
<p>风量备用系数 K={inputs['K']:.3f}；功率余量系数 K_N={inputs['K_N']:.3f}；传动效率 η_t={inputs['eta_t']:.3f}；最低效率 η_min={inputs['eta_min']:.3f}。</p>
<h3>管网计算结果</h3>
<p>选型风量按 Q_f=K·Q₁ 计算，管网阻力系数按 R=H_f/Q_f² 计算，管网特性满足 H=R·Q²。</p>
<table><tr><th>工况</th><th>选型风量（m³/s）</th><th>风压（Pa）</th><th>阻力系数 R</th></tr>
<tr><td>容易时期</td><td>{resp.easy.flowRate:.3f}</td><td>{resp.easy.pressure:.1f}</td><td>{resp.easy.resistance:.6f}</td></tr>
<tr><td>困难时期</td><td>{resp.hard.flowRate:.3f}</td><td>{resp.hard.pressure:.1f}</td><td>{resp.hard.resistance:.6f}</td></tr></table>
<h2>2. 推荐结果</h2>
<p>数据库启用风机 {resp.totalFans} 款，初筛淘汰 {resp.screenedOut} 款，详细校核淘汰 {resp.rejectedByEff} 款，最终候选 {len(resp.candidates)} 款。</p>
{_recommended_html(resp)}
<h2>3. 详细计算过程</h2>
<p>计算过程按照工况点计算、风机初筛、指标求解和最终推荐四个阶段整理。</p>{step_cards}
<div class="notice">数据说明：本报告由选型程序自动生成。数据库中标记为估算的转速、电机、扇叶角度和抽出式轨道宽度等参数，不得替代厂家正式技术资料；采购、施工和安全验算前必须复核。</div>
</body></html>"""


def build_text_report(resp, inputs, generated_at=None):
    generated_at = generated_at or datetime.now()
    lines = ["矿井通风机选型计算记录", f"生成时间：{generated_at:%Y-%m-%d %H:%M:%S}", "=" * 72,
        "1. 输入参数",
        f"容易时期：需求风量 {inputs['q_easy']:.3f} m³/s，风压 {inputs['h_easy']:.1f} Pa。",
        f"困难时期：需求风量 {inputs['q_hard']:.3f} m³/s，风压 {inputs['h_hard']:.1f} Pa。",
        f"K={inputs['K']:.3f}，K_N={inputs['K_N']:.3f}，η_t={inputs['eta_t']:.3f}，η_min={inputs['eta_min']:.3f}。", "",
        "2. 双工况计算结果", "选型风量 Q_f=K·Q₁；阻力系数 R=H_f/Q_f²；管网特性 H=R·Q²。",
        f"容易时期：Q_f={resp.easy.flowRate:.3f} m³/s，H_f={resp.easy.pressure:.1f} Pa，R={resp.easy.resistance:.6f}。",
        f"困难时期：Q_f={resp.hard.flowRate:.3f} m³/s，H_f={resp.hard.pressure:.1f} Pa，R={resp.hard.resistance:.6f}。", "",
        "3. 推荐结果",
        f"启用风机 {resp.totalFans} 款，初筛淘汰 {resp.screenedOut} 款，详细校核淘汰 {resp.rejectedByEff} 款，最终候选 {len(resp.candidates)} 款。"]
    if resp.candidates:
        c = resp.candidates[0]
        lines.extend([f"推荐型号：{c.modelId}，综合评分 {c.score:.4f}。",
            f"装机总功率 {c.motorCount * c.motorPower:.0f} kW，要求功率 {c.requiredPower:.1f} kW，功率余量 {c.powerMargin:.1f}%。",
            f"扇叶角度 {c.bladeAngleDeg:.1f}°，抽出式轨道宽度 {c.railWidthMm / 1000.0:.2f} m，图片路径 {c.imagePath or '未录入'}。"])
    else:
        lines.append("本次计算没有符合全部条件的推荐机型。")
    lines.extend(["", "4. 风机详细数据"])
    for rank, c in enumerate(resp.candidates, 1):
        lines.extend([f"{rank}. {c.modelId}（评分 {c.score:.4f}）",
            f"   额定转速 {c.ratedRpm:.0f} r/min；电机配置 {c.motorCount}×{c.motorPower:.0f} kW。",
            f"   扇叶角度 {c.bladeAngleDeg:.1f}°；抽出式轨道宽度 {c.railWidthMm / 1000.0:.2f} m；图片路径 {c.imagePath or '未录入'}。",
            f"   容易时期：效率 {c.efficiencyEasy:.2%}，转速 {c.rpmEasy:.1f} r/min，轴功率 {c.shaftPowerEasy:.1f} kW。",
            f"   困难时期：效率 {c.efficiencyHard:.2%}，转速 {c.rpmHard:.1f} r/min，轴功率 {c.shaftPowerHard:.1f} kW。"])
    if not resp.candidates:
        lines.append("没有候选风机。")
    lines.extend(["", "5. 详细计算过程", "说明：依次进行能力初筛、交点求解、转速校核、效率与功率校核和综合评分。"])
    for index, step in enumerate(resp.steps, 1):
        lines.append(f"步骤 {index}：{explain_step(step)}")
    lines.extend(["", "数据说明：估算参数不得替代厂家正式技术资料，采购、施工和安全验算前必须复核。"])
    return "\n".join(lines)
