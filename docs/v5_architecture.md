# 矿井通风机选型系统 V5 — 代码架构说明

## 1. 系统总览

本系统用于矿井通风机的自动选型，支持容易时期和困难时期双工况变频运行分析。

**架构**：C++ gRPC 后端（算法 + 数据） + Python Streamlit 前端（UI + 绘图）

```
┌────────────────────────────────────────────────────────────────┐
│                    Python Streamlit 前端                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  app.py   │  │  plotting/   │  │  generated/              │  │
│  │  Web UI   │  │  curves.py   │  │  fan_selector_pb2.py     │  │
│  │          │  │  result.py   │  │  fan_selector_pb2_grpc.py│  │
│  └────┬─────┘  └──────────────┘  └────────────┬─────────────┘  │
│       │                                        │                │
│       └─────────── gRPC 调用 ──────────────────┘                │
└───────────────────────┬────────────────────────────────────────┘
                        │ Protocol Buffers (端口 50051)
┌───────────────────────┴────────────────────────────────────────┐
│                     C++ gRPC 后端                               │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ server   │  │ engine   │  │ selector  │  │ converters   │  │
│  │ gRPC入口  │→ │ 管道计算  │→ │ 风机选型   │→ │ proto转换    │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘  │
│                               ↑                                │
│                          ┌────┴─────┐                          │
│                          │ fan_db   │                          │
│                          │ 风机数据库 │                          │
│                          └──────────┘                          │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. 目录结构

```
v5/
├── proto/
│   └── fan_selector.proto          # gRPC 接口定义（唯一数据契约）
├── backend/
│   ├── include/
│   │   ├── config.hpp              # 全局常量（默认系数、评分权重等）
│   │   ├── models.hpp              # 数据结构定义
│   │   ├── engine.hpp              # 管道计算引擎接口
│   │   ├── selector.hpp            # 风机选型算法接口
│   │   ├── fan_db.hpp              # 风机数据库接口
│   │   └── converters.hpp          # C++ → proto 转换接口
│   ├── src/
│   │   ├── server.cpp              # gRPC 服务入口
│   │   ├── engine.cpp              # 管道计算实现
│   │   ├── selector.cpp            # 选型算法实现
│   │   ├── fan_db.cpp              # 风机数据库 + 多项式拟合
│   │   └── converters.cpp          # proto 消息构建
│   ├── build/                      # CMake 构建输出
│   └── CMakeLists.txt              # 构建配置
├── frontend/
│   ├── app.py                      # Streamlit Web UI 主程序
│   ├── config.py                   # 前端常量（gRPC 地址等）
│   ├── fan_db.py                   # 前端风机数据副本（仅首页表格用）
│   ├── models.py                   # 前端数据结构
│   ├── generated/                  # protoc 生成的 Python gRPC 代码
│   │   ├── fan_selector_pb2.py
│   │   └── fan_selector_pb2_grpc.py
│   └── plotting/
│       ├── font_config.py          # matplotlib 中文字体配置
│       ├── curves.py               # 管道特性曲线绘图
│       └── result.py               # 风机三面板特性曲线绘图
├── scripts/
│   ├── run_server.py               # 启动 C++ 后端
│   ├── run_web.py                  # 启动 Streamlit 前端
│   ├── run_test.py                 # 5 项闭环集成测试
│   ├── build_backend.py            # CMake 编译脚本
│   └── generate_proto.py           # proto 代码生成脚本
├── data/fonts/msyh.ttc             # 微软雅黑字体（matplotlib 中文）
└── docs/                           # 文档
```

---

## 3. Proto 接口定义（fan_selector.proto）

proto 文件是前后端的唯一数据契约，定义了 6 个 message 和 1 个 service。

### 3.1 请求 — FanSelectionRequest

前端传入矿井工况参数：

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| airFlowEasy | double | m³/min | 容易时期需风量 |
| pressureEasy | double | Pa | 容易时期通风阻力 |
| airFlowHard | double | m³/min | 困难时期需风量 |
| pressureHard | double | Pa | 困难时期通风阻力 |
| reserveCoeff | double | — | 风量备用系数 K（默认 1.0） |
| powerMarginCoeff | double | — | 功率裕量系数 Kn（默认 1.15） |
| transEfficiency | double | — | 传动效率 ηt（默认 0.95） |
| minEfficiency | double | — | 最低效率要求 ηmin（默认 0.70） |

### 3.2 响应 — FanSelectionResponse

| 字段 | 说明 |
|------|------|
| code / msg | 状态码和消息 |
| easy / hard | 两个 PeriodResult，管道计算结果 |
| totalFans | 数据库风机总数 |
| screenedOut | 初筛淘汰数 |
| rejectedByEff | 效率不达标淘汰数 |
| candidates | 候选风机列表（按评分降序） |
| steps | 计算日志 |

### 3.3 子消息

- **PeriodResult**：单工况管道计算结果（flowRate m³/s, pressure Pa, resistance R）
- **CurvePoint**：风机性能曲线数据点（q, h, eta）
- **FanPlotData**：绘图数据包（curvePoints + ratedRpm + rpmMin + rpmMax）
- **CandidateFan**：候选风机完整信息（18 个选型结果字段 + plotData 绘图数据）

### 3.4 单位转换

| 方向 | 风量单位 | 转换 |
|------|---------|------|
| 前端 → 后端 | m³/min | 原始输入 |
| 后端内部计算 | m³/s | ÷ 60 |
| 后端 → 前端 | m³/s | 计算结果 |

---

## 4. C++ 后端各模块详解

### 4.1 server.cpp — gRPC 服务入口

**功能**：监听 gRPC 请求，参数校验，调用计算流程，返回结果。

**调用链**：
```
SelectFan() 请求进入
  → 参数校验（风量/风压必须为正）
  → 读取系数（K, K_N, eta_t, eta_min），为 0 时用默认值
  → run_dual()        管道计算
  → run_selector()    风机选型
  → build_selection_response()  结果转 proto
  → 返回响应
```

**监听地址**：`0.0.0.0:{port}`，默认端口 50051，支持命令行参数指定。

### 4.2 engine.cpp — 管道计算引擎

**功能**：根据矿井工况参数计算管道特性。

**核心函数**：

- `run_engine(MineParams, SelectionCoeffs)` → `EngineResult`
  - 计算风量：`Q_f = K × Q1`（m³/min），再 `÷ 60` 转 m³/s
  - 风压直传：`H_f = h_f`（Pa）
  - 管道阻力系数：`R = H_f / Q_f²`

- `run_dual(DualPeriodParams, SelectionCoeffs)` → `DualPeriodResult`
  - 分别计算容易/困难两个工况
  - 生成管道特性曲线数据点 `H = R × Q²`

### 4.3 fan_db.cpp — 风机数据库 + 多项式拟合

**功能**：存储风机性能数据，提供多项式拟合工具。

**数据库内容**（5 款风机）：

| 型号 | 系列 | 额定转速 | 转速范围 | 电机 |
|------|------|---------|---------|------|
| FBCDZ-6No23/2x315 | FBCDZ-6 | 990 | 495~990 | 2×315 kW |
| FBCDZ(B)-6-No20 | FBCDZ(B)-6 | 980 | 490~980 | 2×220 kW |
| FBCDZ(B)-6-No22 | FBCDZ(B)-6 | 980 | 490~980 | 2×315 kW |
| FBCDZ(B)-8-No24 | FBCDZ(B)-8 | 740 | 370~740 | 2×185 kW |
| FBCDZ(B)-8-No28 | FBCDZ(B)-8 | 740 | 370~740 | 2×355 kW |

每款风机包含 10~39 个性能曲线数据点 (Q m³/min, H Pa, η%)。

**数据预处理**（`make_fan_from_data`）：
- 原始数据按 Q 排序
- Q：m³/min → m³/s（÷ 60）
- η：百分比 → 小数（÷ 100）

**多项式拟合**（`build_fan_interpolated`）：
- H(Q)：2 次多项式拟合（最小二乘法，高斯消元求解法方程）
- η(Q)：4 次多项式拟合
- 计算 R² 拟合优度

**线性方程组求解**：实现了完整的高斯消元法（列主元消去），用于多项式拟合的法方程求解。

### 4.4 selector.cpp — 选型算法

**功能**：从风机数据库中筛选、评估、评分，输出排序后的候选列表。

**选型流程**（`run_selector`）：

```
第一步：初筛 screen_by_range()
  ├── Q_max ≥ 困难时期 Q
  ├── H_max ≥ 困难时期 H
  ├── Q_min ≤ 困难时期 Q
  └── 变频最低 Q ≤ 容易时期 Q

第二步：逐台评估 evaluate_one()
  ├── 多项式拟合 → FanInterpolated
  ├── 求工作点 solve_working_point()    [二分法求根]
  │     H_poly(Q) - R × Q² = 0
  ├── 计算实际转速
  │     n_easy = n_rated × Q_easy / Q_base_easy
  │     n_hard = n_rated × Q_hard / Q_base_hard
  ├── 校验转速范围
  ├── 效率校验 verify_efficiency()
  │     η = η_poly(Q_base)
  │     N_shaft = Q × H / (1000 × η × ηt)
  │     N_motor_req = max(N_easy, N_hard) × K_N
  ├── 装机功率校验
  └── 评分 score_candidate()

第三步：按评分降序排列
```

**评分公式**（`score_candidate`）：
```
score = 0.55 × s_hard + 0.35 × s_easy + 0.10 × s_motor

s_hard = min(η_hard / 0.83, 1.0)
s_easy = min(η_easy / 0.83, 1.0)
s_motor = max(0, 1 - |utilization - 0.80| / 0.80)
    其中 utilization = N_shaft_hard / N_installed
```

**工作点求解**（`solve_working_point`）：
- 在 [Q_min, Q_max] 区间扫描 200 个点
- 找到符号变化的区间
- 二分法求根（精度 xtol = 1e-4，最多 100 次迭代）

### 4.5 converters.cpp — C++ → Proto 转换

**功能**：将 C++ 内部数据结构转为 proto 消息格式。

- `candidate_to_proto(SelectionCandidate)` → `CandidateFan`
  - 映射 18 个选型结果字段
  - 构建 `FanPlotData` 子消息：曲线点 + 转速范围
- `build_selection_response(DualPeriodResult, SelectorResult)` → `FanSelectionResponse`
  - 组装完整响应

### 4.6 config.hpp — 全局常量

| 常量 | 值 | 说明 |
|------|---|------|
| DEFAULT_K | 1.00 | 风量备用系数 |
| DEFAULT_K_N | 1.15 | 功率裕量系数 |
| DEFAULT_ETA_T | 0.95 | 传动效率 |
| DEFAULT_ETA_MIN | 0.70 | 最低效率要求 |
| SCORE_W_ETA_HARD | 0.55 | 困难时期效率评分权重 |
| SCORE_W_ETA_EASY | 0.35 | 容易时期效率评分权重 |
| SCORE_W_MOTOR | 0.10 | 电机匹配评分权重 |
| SCORE_ETA_REF | 0.83 | 效率评分基准值 |
| FIT_H_DEGREE | 2 | H(Q) 拟合多项式阶数 |
| FIT_ETA_DEGREE | 4 | η(Q) 拟合多项式阶数 |
| BRENTQ_SCAN_POINTS | 200 | 求根扫描点数 |
| ROOT_XTOL | 1e-4 | 求根精度 |

### 4.7 models.hpp — 数据结构

| 结构体 | 用途 |
|--------|------|
| MineParams | 矿井工况参数（Q1, h_f） |
| SelectionCoeffs | 选型系数（K） |
| EngineResult | 单工况计算结果（Q_f, H_f, R） |
| DualPeriodParams | 双工况输入参数 |
| DualPeriodResult | 双工况计算结果 |
| FanCurvePoint | 风机性能曲线点（Q, H, η） |
| FanModel | 风机型号完整信息 |
| Polynomial | 多项式（系数 + 求值运算符） |
| FanInterpolated | 拟合后的风机（含 H/η 多项式） |
| SelectionCandidate | 通过选型的候选风机 |
| SelectorResult | 选型结果（候选列表 + 统计） |

---

## 5. Python 前端各模块详解

### 5.1 app.py — Streamlit Web UI

**功能**：提供 Web 界面，接收用户输入，调用 C++ 后端，展示结果。

**页面结构**：

```
侧边栏
├── 风量/风压输入（支持 m³/s 或 m³/min 切换）
├── 选型系数调节（K, K_N, ηt, ηmin）
├── 后端连接状态检测
└── "开始计算" 按钮

主区域（4 个标签页）
├── Tab1: 计算结果 — 双工况 Q/H/R + 管道特性曲线图
├── Tab2: 选型对比 — 候选列表 + 运行参数表
├── Tab3: 特性曲线 — 三面板风机特性图
└── Tab4: 计算过程 — C++ 后端日志
```

**输入单位处理**：
- 用户选择 m³/s 时：`Q × 60` 转为 m³/min 传给后端
- 用户选择 m³/min 时：直接传给后端
- 后端统一接收 m³/min，内部 ÷ 60 转 m³/s

### 5.2 plotting/curves.py — 管道特性曲线

**功能**：绘制容易时期和困难时期两条管道阻力抛物线 `H = R × Q²`。

**绘制内容**：
- 两条阻力曲线
- 两个工况点标注
- 工作范围矩形
- ΔQ / ΔH 差值标注

**数据来源**：`PeriodResult.resistance / flowRate / pressure`

### 5.3 plotting/result.py — 风机三面板特性曲线

**功能**：绘制推荐风机的综合特性曲线（3 个子图）。

V5 的关键改动：从 `cand.plotData.curvePoints` 读取曲线数据，不再依赖前端 fan_db 副本。

**三个面板**：

| 面板 | 内容 |
|------|------|
| H-Q 主图 | 额定/变频 H-Q 曲线 + 管道阻力线 + 族曲线 + 工作点 + 基准点 |
| η 等效率线图 | 二维效率场（高斯平滑） + 等值线 + ηmin 线 + 工作点 |
| N-Q 轴功率图 | 额定/变频功率曲线 + 装机功率线 + 工作点轴功率 |

**数据来源**：`CandidateFan` 的选型结果字段 + `plotData` 的曲线数据

### 5.4 font_config.py — 中文字体

加载 `data/fonts/msyh.ttc`（微软雅黑），解决 matplotlib 中文显示为方框的问题。

### 5.5 config.py — 前端常量

gRPC 连接地址：`localhost:50051`

---

## 6. 构建与运行

### 6.1 编译 C++ 后端

```bash
cd v5/backend/build
cmake .. -G "MinGW Makefiles" \
    -DZLIB_LIBRARY="C:/msys64/mingw64/lib/libz.a" \
    -DZLIB_INCLUDE_DIR="C:/msys64/mingw64/include"
mingw32-make -j8
```

依赖：MinGW-w64、gRPC、Protobuf、zlib（均通过 MSYS2 安装）

### 6.2 生成 Python proto 代码

```bash
python scripts/generate_proto.py
```

或手动：
```bash
python -m grpc_tools.protoc -Iproto \
    --python_out=frontend/generated \
    --grpc_python_out=frontend/generated \
    proto/fan_selector.proto
```

### 6.3 启动系统

```bash
# 终端 1：启动 C++ 后端
python scripts/run_server.py

# 终端 2：启动前端
python scripts/run_web.py
```

### 6.4 运行测试

```bash
python scripts/run_test.py
```

5 项闭环测试：
1. 正常选型 — 验证计算结果和推荐型号
2. 自定义系数 — 验证 K=1.15 时风量计算
3. 全部淘汰 — 极端参数无候选
4. 非法参数 — 负数输入返回错误
5. 一致性校验 — 相同输入返回相同结果

---

## 7. 数据流

```
用户输入 (m³/min, Pa)
    │
    ▼
FanSelectionRequest ──── gRPC ────→ server.cpp
                                      │
                                      ▼
                                 参数校验 + 默认值填充
                                      │
                                      ▼
                                 engine.cpp::run_dual()
                                 ├── Q_f = K × Q1 / 60  (m³/s)
                                 ├── H_f = h_f
                                 └── R = H_f / Q_f²
                                      │
                                      ▼
                                 selector.cpp::run_selector()
                                 ├── screen_by_range()   初筛
                                 ├── evaluate_one() × N  逐台评估
                                 │   ├── polyfit         多项式拟合
                                 │   ├── bisect_root     求工作点
                                 │   ├── verify_eff      效率校验
                                 │   └── score           评分
                                 └── sort by score       排序
                                      │
                                      ▼
                                 converters.cpp
                                 └── build_selection_response()
                                      │
                                      ▼
FanSelectionResponse ←── gRPC ────── 返回
    │
    ▼
前端渲染
├── Tab1: PeriodResult → 管道曲线
├── Tab2: CandidateFan[] → 选型表
├── Tab3: plotData → 三面板特性曲线
└── Tab4: steps[] → 计算日志
```

---

## 8. V5 相对 V4 的改动

| 改动项 | V4 | V5 |
|--------|----|----|
| 曲线数据传输 | 无，前端维护 fan_db 副本 | 后端通过 proto 打包 curvePoints |
| proto 结构 | 曲线数据不在 proto 中 | 新增 CurvePoint + FanPlotData message |
| CandidateFan | 18 个字段 | 18 个字段 + plotData 子消息 |
| plotting/result.py | 依赖 frontend.fan_db | 从 cand.plotData 读取 |
| 前后端耦合 | 前端需同步维护风机数据 | 前端绘图数据全部来自后端 |
