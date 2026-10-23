# 推荐风机特性曲线绘图指南

本文档面向**前端开发者**，说明如何使用 gRPC 返回的 proto 数据绘制三张推荐风机特性曲线图。
所有绘图数据均来自后端，前端**不需要**存储风机数据库。

---

## 1. 数据来源：需要哪些 proto message

调用 `FanSelectorService.SelectFan()` 后，从 `FanSelectionResponse` 中获取绘图数据。
涉及 3 个 message：


| 数据源           | proto 路径                        | 说明                                   |
| ---------------- | --------------------------------- | -------------------------------------- |
| **PeriodResult** | `response.easy` / `response.hard` | 管道阻力系数 R                         |
| **CandidateFan** | `response.candidates[i]`          | 选型结果（工作点、效率、功率、转速等） |
| **FanPlotData**  | `candidates[i].plotData`          | 风机原始曲线数据（画图核心）           |

### 1.1 PeriodResult（管道数据）

```protobuf
message PeriodResult {
  double flowRate   = 1;   // 计算风量 (m³/s)
  double pressure   = 2;   // 计算风压 (Pa)
  double resistance = 3;   // 管道阻力系数 R (N·s²/m⁸)  ← 画管道抛物线用
}
```

绘图只需要 `resistance` 字段，容易/困难各取一个。

### 1.2 FanPlotData（风机曲线数据）

```protobuf
message CurvePoint {
  double q   = 1;   // 风量 (m³/s)
  double h   = 2;   // 风压 (Pa)
  double eta = 3;   // 效率 (0~1)
}

message FanPlotData {
  repeated CurvePoint curvePoints = 1;  // 额定转速下的性能曲线数据点
  double ratedRpm = 2;   // 额定转速 n₀ (r/min)，相似律计算基准
  double rpmMin   = 3;   // 最低转速 (r/min)，变频范围下限
  double rpmMax   = 4;   // 最高转速 (r/min)，变频范围上限
}
```

这是画图最核心的数据。`curvePoints` 是额定转速下实测的 (Q, H, η) 散点，
前端通过**多项式拟合**生成连续曲线，再通过**相似律**生成变频曲线族。

### 1.3 CandidateFan 中绘图相关字段

```protobuf
message CandidateFan {
  string modelId        = 1;   // 风机型号 → 图标题
  double ratedRpm       = 2;   // 额定转速 → 图标题
  double motorPower     = 3;   // 单台电机功率 (kW) → 装机功率线
  int32  motorCount     = 4;   // 电机数量 → 装机功率 = motorCount × motorPower
  double flowEasy       = 5;   // 容易工作点 Q (m³/s)
  double pressEasy      = 6;   // 容易工作点 H (Pa)
  double flowHard       = 7;   // 困难工作点 Q (m³/s)
  double pressHard      = 8;   // 困难工作点 H (Pa)
  double efficiencyEasy = 9;   // 容易效率 (0~1) → 工作点标注
  double efficiencyHard = 10;  // 困难效率 (0~1) → 工作点标注
  double shaftPowerEasy = 11;  // 容易轴功率 (kW) → N-Q 图工作点
  double shaftPowerHard = 12;  // 困难轴功率 (kW) → N-Q 图工作点
  double speedRatio     = 14;  // 转速比 → 信息面板显示
  double rpmEasy        = 15;  // 容易转速 (r/min) → 变频曲线
  double rpmHard        = 16;  // 困难转速 (r/min) → 变频曲线
  FanPlotData plotData  = 19;  // 绘图数据
  double baseFlowEasy   = 20;  // 基准点风量-容易 (m³/s) → 额定曲线与管道线交点
  double basePressEasy  = 21;  // 基准点风压-容易 (Pa)
  double baseFlowHard   = 22;  // 基准点风量-困难 (m³/s)
  double basePressHard  = 23;  // 基准点风压-困难 (Pa)
}
```

---

## 2. 数据预处理：多项式拟合 + 相似律

从 `plotData.curvePoints` 提取三组数组：

```
Q[] = [pt.q for pt in curvePoints]     // 风量
H[] = [pt.h for pt in curvePoints]     // 风压
η[] = [pt.eta for pt in curvePoints]   // 效率 (0~1)
```

拟合两条多项式曲线：

- **H(Q) 曲线**：二次多项式拟合（degree = 2）
- **η(Q) 曲线**：四次多项式拟合（degree = 4）

```
H_poly = polyfit(Q, H, 2)    → H(Q) = a₂Q² + a₁Q + a₀
η_poly = polyfit(Q, η, 4)    → η(Q) = b₄Q⁴ + b₃Q³ + b₂Q² + b₁Q + b₀
```

记录风量范围 `Q_min = min(Q)`, `Q_max = max(Q)`。

### 2.2 相似律（变频曲线核心公式）

变频调速时，转速比 `r = n / n₀`，则：


| 额定转速参数 | 变频后参数 | 公式                        |
| ------------ | ---------- | --------------------------- |
| Q₀          | Q'         | Q' = Q₀ × r               |
| H₀          | H'         | H' = H₀ × r²             |
| N₀          | N'         | N' = N₀ × r³             |
| η₀         | η'        | η' ≈ η₀（效率近似不变） |

### 2.3 转速比计算

```
n₀     = plotData.ratedRpm          // 额定转速
r_easy = cand.rpmEasy / n₀          // 容易时期转速比
r_hard = cand.rpmHard / n₀          // 困难时期转速比（通常 ≈ 1.0）
r_min  = plotData.rpmMin / n₀       // 变频最低转速比
r_max  = plotData.rpmMax / n₀       // 变频最高转速比
```

### 2.4 轴功率计算

```
N(Q) = Q × H(Q) / (1000 × η(Q) × ηt)    [kW]
```

其中 `ηt` 为传动效率（默认 0.95，来自请求参数 `transEfficiency`）。

---

## 3. 三张图的画法

### 图 ① H-Q 特性曲线（主图，最大，左侧）

**目的**：展示风机在不同转速下的风量-风压特性，以及与管道阻力的交点（工作点）。

#### 需要的 proto 字段


| 字段                                     | 用途                                  |
| ---------------------------------------- | ------------------------------------- |
| `plotData.curvePoints`                   | 拟合 H_poly → 生成额定/变频 H-Q 曲线 |
| `plotData.ratedRpm`                      | 相似律基准转速                        |
| `cand.rpmEasy / rpmHard`                 | 计算变频转速比                        |
| `resp.easy.resistance / hard.resistance` | 画管道阻力抛物线 H = R×Q²           |
| `cand.flowEasy / pressEasy`              | 容易工作点坐标                        |
| `cand.flowHard / pressHard`              | 困难工作点坐标                        |
| `cand.efficiencyEasy / Hard`             | 工作点标注文字                        |
| `cand.baseFlowEasy / basePressEasy`      | 基准交叉点坐标-容易（后端已算好）     |
| `cand.baseFlowHard / basePressHard`      | 基准交叉点坐标-困难（后端已算好）     |

#### 绘制元素

1. **额定转速 H-Q 曲线**（黑色实线）

   ```
   Q₀ = linspace(Q_min, Q_max, 300)
   H₀ = H_poly(Q₀)
   plot(Q₀, H₀)
   ```
2. **容易时期变频 H-Q 曲线**（蓝色点划线）

   ```
   r_easy = cand.rpmEasy / plotData.ratedRpm
   Q' = Q₀ × r_easy
   H' = H_poly(Q₀) × r_easy²
   plot(Q', H')
   ```
3. **困难时期变频 H-Q 曲线**（橙色点划线）

   ```
   r_hard = cand.rpmHard / plotData.ratedRpm
   Q' = Q₀ × r_hard
   H' = H_poly(Q₀) × r_hard²
   ```
4. **相似律族曲线**（灰色虚线，r = 0.6, 0.7, 0.8, 0.9）

   - 每条用同样公式，在末端标注 `r × n₀` 的转速值
5. **管道阻力抛物线**（两条虚线）

   ```
   R_easy = resp.easy.resistance
   R_hard = resp.hard.resistance
   Q_pipe = linspace(0, Q_max × 1.15, 300)
   H_easy = R_easy × Q_pipe²
   H_hard = R_hard × Q_pipe²
   ```
6. **工作点**（圆点 + 文字标注）

   ```
   容易: (cand.flowEasy, cand.pressEasy), 标注 "η = cand.efficiencyEasy"
   困难: (cand.flowHard, cand.pressHard), 标注 "η = cand.efficiencyHard"
   ```
7. **基准交叉点**（三角标注，后端已算好，直接取值）

   ```
   容易基准点: (cand.baseFlowEasy, cand.basePressEasy)
   困难基准点: (cand.baseFlowHard, cand.basePressHard)
   // 如果值 > 0 则画三角标记，否则跳过（无交点）
   ```

#### 坐标范围

- X 轴：`[Q_min × r_easy × 0.85, Q_max × 1.15]`
- Y 轴：`[0, max(H_rated) × 1.12]`

---

### 图 ② η(Q, H) 等效率线图（右上）

**目的**：在二维 Q-H 平面上用等高线/热力图展示效率分布，判断工作点是否在高效区。

#### 需要的 proto 字段


| 字段                         | 用途                           |
| ---------------------------- | ------------------------------ |
| `plotData.curvePoints`       | 拟合 η_poly → 计算效率场     |
| `plotData.ratedRpm`          | 相似律基准                     |
| `plotData.rpmMin / rpmMax`   | 确定效率场有效范围（变频范围） |
| `cand.flowEasy / pressEasy`  | 标注容易工作点                 |
| `cand.flowHard / pressHard`  | 标注困难工作点                 |
| `cand.efficiencyEasy / Hard` | 工作点效率标注                 |
| 请求参数`minEfficiency`      | 画 η_min 红色警戒线           |

#### 核心算法：构建二维效率场

这张图的难点在于：要把一维的 η(Q) 曲线映射到二维 Q-H 平面。

原理：Q-H 平面上的每个点 (Q, H) 对应一个等效管道阻力 `R = H/Q²`。
在额定曲线上找到同样 R 值的点 Q₀，该点效率即为 η(Q₀)。
再检查转速比 `r = Q/Q₀` 是否在变频范围内。

```
r_min = plotData.rpmMin / plotData.ratedRpm
r_max = plotData.rpmMax / plotData.ratedRpm

对网格上每个点 (Q, H)：
  1. R_pt = H / Q²
  2. 在额定曲线 H_poly(Q₀)/Q₀² 中找到 R 值最接近 R_pt 的 Q₀
  3. r = Q / Q₀
  4. 如果 r_min ≤ r ≤ r_max 且 |R_match - R_pt| / R_pt < 2%:
       η_field[i][j] = η_poly(Q₀)
     否则:
       η_field[i][j] = NaN（不可达区域）
```

#### 绘制步骤

1. 创建 Q×H 网格（建议 400×400）
2. 按上述算法填充效率场
3. 高斯平滑（σ=4.0），NaN 区域不参与
4. `contourf` 填充色 + `contour` 等值线（35%~85%，步长 5%）
5. 画 η_min 红色虚线
6. 画额定转速和最低转速的 H-Q 曲线作为边界参考
7. 标注两个工作点及效率值

#### 坐标范围

- X 轴：`[Q_min × r_min × 0.85, Q_max × r_max × 1.05]`
- Y 轴：`[0, max(H_rated) × 1.05]`

---

### 图 ③ N-Q 轴功率特性曲线（右下）

**目的**：展示不同转速下的轴功率，对比装机功率余量。

#### 需要的 proto 字段


| 字段                            | 用途                               |
| ------------------------------- | ---------------------------------- |
| `plotData.curvePoints`          | 拟合 H_poly + η_poly → 计算 N(Q) |
| `plotData.ratedRpm`             | 相似律基准                         |
| `cand.rpmEasy / rpmHard`        | 变频功率曲线                       |
| `cand.motorPower × motorCount` | 装机功率水平线                     |
| `cand.flowEasy / flowHard`      | 工作点 X 坐标                      |
| `cand.shaftPowerEasy / Hard`    | 工作点 Y 坐标（轴功率）            |

#### 轴功率计算

```
额定转速下：
  N₀(Q) = Q × H_poly(Q) / (1000 × η_poly(Q) × ηt)   [kW]

变频工况（转速比 r）：
  Q' = Q₀ × r
  N' = N₀ × r³        // 功率按转速比三次方缩放
```

#### 绘制元素

1. **额定转速 N-Q 曲线**（黑色实线）
2. **容易时期 N-Q 曲线**（蓝色点划线，r = r_easy）
3. **困难时期 N-Q 曲线**（橙色点划线，r = r_hard）
4. **族曲线**（灰色，r = 0.6, 0.7, 0.8, 0.9）
5. **装机功率线**（红色水平虚线）
   ```
   N_installed = cand.motorCount × cand.motorPower
   ```
6. **工作点标注**
   ```
   容易: (cand.flowEasy, cand.shaftPowerEasy)
   困难: (cand.flowHard, cand.shaftPowerHard)
   ```

#### 坐标范围

- X 轴：`[Q_min × r_easy × 0.85, Q_max × 1.05]`
- Y 轴：`[0, N_installed × 1.35]`

---

## 4. 布局

三张图组织在一个画布上：

```
┌──────────────────┬────────────┐
│                  │  ② η 等效  │
│   ① H-Q 主图     │   率线图   │
│  （占左侧全高）   ├────────────┤
│                  │  ③ N-Q 轴  │
│                  │   功率图   │
└──────────────────┴────────────┘
```

- 画布尺寸：15 × 9 英寸
- 左列（H-Q）占宽度比 1.55，右列占 1.0
- 总标题格式：`推荐风机特性曲线 — {modelId} （{motorCount}×{motorPower} kW，额定 {n₀} r/min）`

---

## 5. 完整数据流

```
前端发送 FanSelectionRequest
        ↓
后端返回 FanSelectionResponse
        ↓
┌─ 取 R_easy = response.easy.resistance
│  取 R_hard = response.hard.resistance
│
├─ 选择目标风机 cand = response.candidates[i]
│
├─ 取 plotData = cand.plotData
│  ├─ curvePoints → polyfit → H_poly(Q), η_poly(Q)
│  ├─ ratedRpm → n₀（相似律基准）
│  └─ rpmMin / rpmMax → r_min, r_max（效率场范围）
│
├─ 取 cand.rpmEasy / rpmHard → r_easy, r_hard
├─ 取 cand.flowEasy / pressEasy / flowHard / pressHard → 工作点坐标
├─ 取 cand.baseFlowEasy / basePressEasy → 容易基准交叉点（后端已算）
├─ 取 cand.baseFlowHard / basePressHard → 困难基准交叉点（后端已算）
├─ 取 cand.efficiencyEasy / Hard → 效率标注
├─ 取 cand.shaftPowerEasy / Hard → N-Q 图工作点
└─ 取 cand.motorCount × motorPower → 装机功率线
        ↓
画三张图
```

---

## 6. 完整数据引用汇总


| 数据            | proto 访问路径                                | 用于哪张图        |
| --------------- | --------------------------------------------- | ----------------- |
| 曲线点 Q, H, η | `cand.plotData.curvePoints[i].q / .h / .eta`  | ①②③ 多项式拟合 |
| 额定转速 n₀    | `cand.plotData.ratedRpm`                      | ①②③ 相似律基准 |
| 最低转速        | `cand.plotData.rpmMin`                        | ② η 场下限      |
| 最高转速        | `cand.plotData.rpmMax`                        | ② η 场上限      |
| 管道阻力系数 R  | `resp.easy.resistance / resp.hard.resistance` | ① 管道抛物线     |
| 容易工作点      | `cand.flowEasy / cand.pressEasy`              | ①② 标注         |
| 困难工作点      | `cand.flowHard / cand.pressHard`              | ①② 标注         |
| 容易效率        | `cand.efficiencyEasy`                         | ①② 标注文字     |
| 困难效率        | `cand.efficiencyHard`                         | ①② 标注文字     |
| 容易转速        | `cand.rpmEasy`                                | ①③ 变频曲线     |
| 困难转速        | `cand.rpmHard`                                | ①③ 变频曲线     |
| 容易轴功率      | `cand.shaftPowerEasy`                         | ③ 工作点         |
| 困难轴功率      | `cand.shaftPowerHard`                         | ③ 工作点         |
| 装机功率        | `cand.motorPower × cand.motorCount`          | ③ 水平线         |
| 转速比          | `cand.speedRatio`                             | ① 信息面板       |
| 基准点-容易     | `cand.baseFlowEasy / cand.basePressEasy`      | ① 三角标注       |
| 基准点-困难     | `cand.baseFlowHard / cand.basePressHard`      | ① 三角标注       |
| 型号            | `cand.modelId`                                | 图标题            |

---

## 7. 注意事项

1. `curvePoints` 中的 `eta` 值范围是 0~1（不是百分比）。如果后端数据存的是百分比（>1），前端需要除以 100
2. 所有风量单位统一为 **m³/s**，不需要单位转换
3. 相似律中效率近似不变（`η(Q') ≈ η(Q₀)`），这是工程近似
4. η 等效率场计算量较大（400×400 网格），可根据前端性能调整分辨率
5. 基准交叉点由后端计算并通过 `baseFlowEasy/basePressEasy/baseFlowHard/basePressHard` 传递，前端不需要求根运算。如果值为 0 表示无交点，跳过绘制即可
6. 前端**不需要**维护风机数据库，所有数据都从后端 gRPC 返回
