# V7 风机选型后端架构与详细执行流程

## 1. 文档目的

本文说明 V7 风机选型系统后端的整体结构、各源文件职责、gRPC 请求处理过程、SQLite 数据库加载过程，以及风机选型算法的详细执行顺序。

本文只关注正式后端。`frontend/` 下的 Streamlit 程序是测试和演示客户端，不属于后端核心架构。

---

## 2. 后端总体架构

后端采用 C++17 开发，通过 gRPC 对外提供风机选型服务，使用 SQLite 保存风机基础信息和性能曲线数据。

```text
正式前端或其他客户端
        │
        │ gRPC：SelectFan
        ▼
┌─────────────────────────────┐
│ server.cpp                  │
│ 接口入口、参数校验、异常转换 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ engine.cpp                  │
│ 双工况风量、阻力和管网曲线   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ selector.cpp                │
│ 初筛、交点、转速、效率、功率 │
│ 校核和候选评分              │
└──────────────┬──────────────┘
               │ fanDb()
               ▼
┌─────────────────────────────┐
│ fan_db.cpp                  │
│ SQLite读取、单位转换、曲线拟合│
└──────────────┬──────────────┘
               │ SQLite C API
               ▼
        data/fans.db
```

后端并不通过 Proto “请求数据库”。Proto 是客户端与后端之间的通信协议；后端内部通过 SQLite C API 直接查询数据库，这是正常的数据访问方式。

---

## 3. 目录和程序职责

### 3.1 通信协议

#### `proto/fan_selector.proto`

定义客户端与 C++ 后端之间的 gRPC 契约，包括：

- `FanSelectionRequest`：选型输入参数；
- `PeriodResult`：单时期管网计算结果；
- `CurvePoint`：风机原始性能点；
- `FanPlotData`：风机绘图数据；
- `CandidateFan`：通过校核的候选风机；
- `FanSelectionResponse`：完整选型响应；
- `FanSelectorService.SelectFan`：当前唯一的远程过程调用。

当前 Proto 只提供业务选型接口：

```proto
rpc SelectFan(FanSelectionRequest) returns (FanSelectionResponse);
```

数据库连接、SQL 查询和内部模型不应暴露在该 Proto 中。

### 3.2 公共数据模型

#### `backend/include/models.hpp`

定义算法各阶段使用的 C++ 内部数据结构。

| 结构 | 作用 |
|---|---|
| `MineParams` | 单时期原始风量、风压输入 |
| `SelectionCoeffs` | 风量备用系数 `K` |
| `EngineResult` | 单时期选型风量、风压、阻力系数 |
| `DualPeriodParams` | 容易时期和困难时期的输入 |
| `DualPeriodResult` | 双时期计算结果及管网曲线 |
| `FanCurvePoint` | 内部性能点，风量为 m³/s，效率为 0～1 |
| `FanModel` | 一台风机的基础信息和性能曲线 |
| `Polynomial` | 多项式及其求值方法 |
| `FanInterpolated` | 风压和效率拟合多项式及拟合质量 |
| `SelectionCandidate` | 一台通过全部校核的候选风机 |
| `SelectorResult` | 候选列表、最佳候选和淘汰统计 |

这些结构是算法层内部模型，与数据库表结构和 Proto 消息相互独立。

### 3.3 算法配置

#### `backend/include/config.hpp`

保存默认参数和算法常量：

| 常量 | 默认值 | 含义 |
|---|---:|---|
| `DEFAULT_K` | 1.00 | 风量备用系数 |
| `DEFAULT_K_N` | 1.15 | 功率裕量系数 |
| `DEFAULT_ETA_T` | 0.95 | 传动效率 |
| `DEFAULT_ETA_MIN` | 0.70 | 最低风机效率 |
| `FIT_H_DEGREE` | 2 | 风压曲线拟合阶数 |
| `FIT_ETA_DEGREE` | 4 | 效率曲线拟合阶数 |
| `BRENTQ_SCAN_POINTS` | 200 | 寻找交点时的扫描点数 |
| `ROOT_XTOL` | 0.0001 | 二分法求根精度 |
| `GRPC_DEFAULT_PORT` | 50051 | 默认 gRPC 端口 |

综合评分权重为：

```text
困难时期效率：55%
容易时期效率：35%
电机利用率：10%
```

### 3.4 gRPC 服务入口

#### `backend/src/server.cpp`

后端可执行程序入口，主要职责为：

1. 读取命令行端口，默认端口为 `50051`；
2. 创建 `FanSelectorServiceImpl`；
3. 监听 `0.0.0.0:<port>`；
4. 接收 `SelectFan` 请求；
5. 校验请求参数；
6. 调用管网计算和选型算法；
7. 将 C++ 结果转换为 Proto 响应；
8. 将异常转换为 gRPC 状态。

它不包含具体选型算法，也不直接编写 SQL。

### 3.5 双工况管网计算

#### `backend/src/engine.cpp`

负责从用户输入得到实际选型工况和管网阻力。

核心公开函数：

```cpp
EngineResult runEngine(...);
DualPeriodResult runDual(...);
```

`runEngine()` 计算单个时期，`runDual()` 依次计算容易时期和困难时期。

### 3.6 数据库访问和曲线拟合

#### `backend/src/fan_db.cpp`

当前文件同时承担三类职责：

1. 使用 SQLite C API 查询风机数据库；
2. 将数据库记录转换为 `FanModel`；
3. 对风压、效率性能点进行多项式拟合。

公开接口位于 `backend/include/fan_db.hpp`：

```cpp
FanModel makeFanFromData(...);
FanInterpolated buildFanInterpolated(...);
const std::vector<FanModel>& fanDb();
```

其中 `fanDb()` 是选型算法取得全部启用风机的统一入口。

### 3.7 选型算法

#### `backend/src/selector.cpp`

负责完整选型过程：

- 能力范围初筛；
- 风机曲线和管网曲线交点求解；
- 变频转速计算；
- 转速范围校核；
- 效率计算和最低效率校核；
- 轴功率、所需电机功率计算；
- 装机功率校核；
- 综合评分；
- 候选排序。

入口函数是：

```cpp
SelectorResult runSelector(...);
```

### 3.8 C++ 模型到 Proto 的转换

#### `backend/src/converters.cpp`

负责把算法内部结构转换成对外响应：

```cpp
CandidateFan candidateToProto(...);
FanSelectionResponse buildSelectionResponse(...);
```

这样算法层不需要依赖界面展示逻辑。

### 3.9 构建系统

#### `backend/CMakeLists.txt`

主要完成：

- 使用 C++17；
- 查找 gRPC、Protobuf、SQLite3 和线程库；
- 根据 Proto 自动生成 C++ 消息和服务代码；
- 编译 `fan_selection_core` 算法静态库；
- 编译 `fan_selector_server` 服务程序；
- 将 SQLite、gRPC 和 Protobuf 链接到最终程序。

---

## 4. 后端启动流程

通常使用：

```powershell
python scripts/run_server.py
```

也可以向脚本传入端口：

```powershell
python scripts/run_server.py 50052
```

启动过程如下：

```text
scripts/run_server.py
    │
    ├─ 定位 backend/build/fan_selector_server.exe
    ├─ 将 MSYS2 动态库目录加入 PATH
    ├─ 设置 FAN_DB_PATH
    │      默认：<项目根目录>/data/fans.db
    └─ 启动 fan_selector_server.exe <port>
           │
           └─ server.cpp::main()
                  └─ runServer("0.0.0.0:<port>")
```

数据库不会在服务刚启动时立即加载。当前实现采用首次使用时加载，也就是第一条进入选型算法的请求触发数据库读取。

---

## 5. 一次 `SelectFan` 请求的完整调用链

```text
客户端
  │
  │ FanSelectionRequest
  ▼
server.cpp::SelectFan()
  │
  ├─ 请求参数校验
  ├─ 提取参数或使用默认值
  │
  ├─ engine.cpp::runDual()
  │    ├─ runEngine(easy)
  │    ├─ runEngine(hard)
  │    └─ 生成两条管网曲线
  │
  ├─ selector.cpp::runSelector()
  │    ├─ fan_db.cpp::fanDb()
  │    │    └─ 首次调用时查询 SQLite
  │    ├─ screenByRange()
  │    ├─ evaluateOne() × 初筛通过风机
  │    │    ├─ buildFanInterpolated()
  │    │    ├─ solveWorkingPoint(easy)
  │    │    ├─ solveWorkingPoint(hard)
  │    │    ├─ 转速范围校核
  │    │    ├─ verifyEfficiency()
  │    │    ├─ 装机功率校核
  │    │    └─ scoreCandidate()
  │    └─ 按 score 降序排序
  │
  └─ converters.cpp::buildSelectionResponse()
       │
       └─ FanSelectionResponse
              ▼
             客户端
```

---

## 6. 请求参数处理

`server.cpp::SelectFan()` 首先检查：

```text
airFlowEasy > 0
airFlowHard > 0
pressureEasy > 0
pressureHard > 0
```

不满足时返回：

```text
gRPC StatusCode::INVALID_ARGUMENT
```

以下可选参数如果大于 0，就使用请求值；否则使用后端默认值：

| Proto 字段 | C++ 参数 | 默认值 |
|---|---|---:|
| `reserveCoeff` | `K` | 1.00 |
| `powerMarginCoeff` | `K_N` | 1.15 |
| `transEfficiency` | `eta_t` | 0.95 |
| `minEfficiency` | `eta_min` | 0.70 |

数据库异常、曲线异常或算法异常会被 `catch` 捕获，并返回：

```text
gRPC StatusCode::INTERNAL
```

---

## 7. 双工况和管网计算

### 7.1 选型风量

对于容易时期和困难时期，分别计算：

```text
Q_f = K × Q_1
```

其中：

- `Q_1` 是客户端输入的需求风量；
- `K` 是风量备用系数；
- `Q_f` 是进入风机选型的计算风量。

### 7.2 管网阻力系数

根据用户输入风压计算：

```text
R = H_f / Q_f²
```

管网曲线为：

```text
H = R × Q²
```

### 7.3 双时期结果

`runDual()` 分别得到：

- 容易时期 `Q、H、R`；
- 困难时期 `Q、H、R`。

同时生成两条管网曲线。绘图范围上限当前取：

```text
Q_max = 困难时期选型风量 × 1.3
```

管网曲线主要用于展示；选型算法直接使用两个时期的阻力系数 `R`。

---

## 8. 后端如何调用数据库

### 8.1 数据库路径

`fan_db.cpp::fan_db_path()` 按以下规则确定路径：

1. 如果环境变量 `FAN_DB_PATH` 非空，则使用该路径；
2. 否则使用相对路径 `data/fans.db`。

`scripts/run_server.py` 会默认把 `FAN_DB_PATH` 设置为项目中的绝对路径，因此通过该脚本启动时不依赖当前工作目录。

### 8.2 数据库连接

后端通过 SQLite C API 打开数据库：

```cpp
sqlite3_open_v2(
    path.c_str(),
    &raw,
    SQLITE_OPEN_READONLY,
    nullptr
);
```

关键点：

- 使用只读模式；
- 后端选型不会修改数据库；
- 数据库连接由 `std::unique_ptr` 和自定义删除器自动关闭；
- SQL 语句由封装的 `Statement` 类自动释放。

### 8.3 查询启用风机

`loadFansFromSqlite()` 查询 `fans` 表：

```sql
SELECT
    id,
    model_id,
    series,
    fan_type,
    rated_rpm,
    rpm_min,
    rpm_max,
    motor_kw,
    motor_count,
    COALESCE(blade_angle_deg, 0),
    COALESCE(withdrawable_rail_width_mm, 0),
    COALESCE(image_path, ''),
    COALESCE(manufacturer, ''),
    COALESCE(product_name, ''),
    COALESCE(product_spec, ''),
    COALESCE(motor_model, ''),
    COALESCE(factory_no, '')
FROM fans
WHERE enabled != 0
ORDER BY id;
```

只有启用的风机会进入算法。

### 8.4 查询每台风机的性能点

对于每条风机记录，再按 `fan_id` 查询：

```sql
SELECT q_m3_min, h_pa, eta_percent
FROM fan_curve_points
WHERE fan_id = ?
ORDER BY point_order, id;
```

使用参数绑定：

```cpp
sqlite3_bind_int64(stmt.get(), 1, fan_id);
```

而不是拼接 SQL，可以避免类型和注入问题。

### 8.5 数据校验

加载过程中检查：

- `model_id` 不能为空；
- 额定、最低、最高转速必须为正数；
- `rpm_min <= rpm_max`；
- 单台电机功率必须为正数；
- 电机数量必须为正数；
- 每台风机至少有 5 个曲线点；
- 曲线点风量、风压和效率必须为正数。

任意一台启用风机存在以上错误，当前实现都会抛出异常，导致本次选型请求返回 `INTERNAL`。

### 8.6 单位转换

数据库保存原始工程单位：

```text
风量：m³/min
风压：Pa
效率：%
```

进入 C++ 算法模型时转换为：

```text
Q = q_m3_min / 60        → m³/s
H = h_pa                 → Pa
eta = eta_percent / 100  → 0～1
```

曲线点随后按风量从小到大排序。

### 8.7 数据库缓存

`fanDb()` 当前实现为：

```cpp
const std::vector<FanModel>& fanDb() {
    static const std::vector<FanModel> db =
        loadFansFromSqlite(fan_db_path());
    return db;
}
```

这意味着：

1. 第一条实际调用 `fanDb()` 的请求读取数据库；
2. 读取结果保存为进程级静态只读对象；
3. 后续请求直接复用内存数据，不重复查询 SQLite；
4. 服务运行期间修改 `fans.db` 不会自动生效；
5. 数据库变更后需要重启后端。

这种方式适合风机数据较少、读取频繁、更新不频繁的场景。

---

## 9. 数据库表结构

### 9.1 `fans`

一台风机对应一条主表记录，主要字段如下：

| 字段 | 含义 |
|---|---|
| `id` | 数据库主键 |
| `model_id` | 唯一风机型号 |
| `series` | 风机系列 |
| `fan_type` | 风机类型 |
| `manufacturer` | 制造厂家 |
| `product_name` | 产品名称 |
| `product_spec` | 产品规格 |
| `motor_model` | 电机型号 |
| `factory_no` | 出厂编号 |
| `rated_rpm` | 额定转速 |
| `rpm_min` | 最低允许转速 |
| `rpm_max` | 最高允许转速 |
| `motor_kw` | 单台电机功率 |
| `motor_count` | 电机数量 |
| `blade_angle_deg` | 叶片角度 |
| `withdrawable_rail_width_mm` | 抽出式轨道宽度 |
| `image_path` | 图片相对路径 |
| `enabled` | 是否参与选型 |

### 9.2 `fan_curve_points`

一台风机对应多个性能点：

| 字段 | 含义 |
|---|---|
| `id` | 性能点主键 |
| `fan_id` | 关联 `fans.id` |
| `q_m3_min` | 原始风量，m³/min |
| `h_pa` | 风压，Pa |
| `eta_percent` | 效率，% |
| `point_order` | 曲线点顺序 |

外键关系：

```text
fans.id 1 ───── N fan_curve_points.fan_id
```

---

## 10. 曲线拟合过程

每台通过初筛的风机在详细校核前调用：

```cpp
buildFanInterpolated(fan, FIT_H_DEGREE, FIT_ETA_DEGREE);
```

### 10.1 风压曲线

使用二次多项式拟合：

```text
H_fan(Q) = aQ² + bQ + c
```

### 10.2 效率曲线

使用四次多项式拟合：

```text
eta(Q) = aQ⁴ + bQ³ + cQ² + dQ + e
```

`fan_db.cpp` 自己构造最小二乘正规方程，并通过带主元选择的高斯消元求解多项式系数。

同时计算：

- `r2H`：风压曲线拟合决定系数；
- `r2Eta`：效率曲线拟合决定系数。

当前后端会计算 R²，但没有根据 `FIT_R2_WARNING` 自动警告或淘汰风机。

---

## 11. 风机初筛

`runSelector()` 首先调用：

```cpp
screenByRange(...);
```

每台风机检查以下条件。

### 11.1 困难时期最大风量

```text
fan.qMax >= qHard
```

### 11.2 困难时期最大风压

```text
fan.hMax >= hHard
```

### 11.3 困难时期风量不能低于额定曲线最小风量

```text
fan.qMin <= qHard
```

### 11.4 容易时期最低变频能力

先计算最低转速比：

```text
r_min = rpm_min / rated_rpm
```

最低转速对应的最小风量：

```text
Q_min_vfd = fan.qMin × r_min
```

要求：

```text
Q_min_vfd <= qEasy
```

初筛只进行能力范围排除，不完成最终的工作点、效率和功率判断。

---

## 12. 工作点求解

对于每台初筛通过的风机，分别求容易时期和困难时期的基准工作点。

风机额定风压曲线为：

```text
H_fan(Q)
```

管网曲线为：

```text
H_pipe(Q) = RQ²
```

交点满足：

```text
H_fan(Q) - RQ² = 0
```

### 12.1 求解方法

`solveWorkingPoint()`：

1. 在风机额定曲线的 `qMax` 到 `qMin` 范围扫描 200 个点；
2. 找到函数值发生异号的相邻区间；
3. 使用二分法求根；
4. 精度由 `ROOT_XTOL = 1e-4` 控制；
5. 返回额定曲线上的基准风量和基准风压。

若某一时期没有交点，该风机直接淘汰。

---

## 13. 变频转速计算和校核

设额定曲线与管网曲线交点风量为 `u`，目标选型风量为 `q`。

根据风机相似定律：

```text
Q ∝ n
```

所需转速为：

```text
n_required = rated_rpm × q / u
```

分别计算：

```text
nEasyRpm = rated_rpm × qEasy / uEasy
nHardRpm = rated_rpm × qHard / uHard
```

两个时期均必须满足：

```text
rpm_min <= n_required <= rpm_max
```

任一时期转速越界，该风机淘汰。

当前代码保存的 `nRatio` 为：

```text
nRatio = nHardRpm / nEasyRpm
```

Proto 中关于该字段的注释应与这个实际方向保持一致。

---

## 14. 效率和功率校核

### 14.1 效率

风机效率在额定曲线基准交点处计算：

```text
etaEasy = etaPoly(uEasy)
etaHard = etaPoly(uHard)
```

计算结果被限制在：

```text
0.01 <= eta <= 1.0
```

要求两个时期均满足：

```text
eta >= etaMin
```

否则淘汰。

### 14.2 轴功率

轴功率公式：

```text
N_shaft = Q × H / (1000 × eta × eta_t)
```

其中：

- `Q`：目标选型风量，m³/s；
- `H`：目标工况风压，Pa；
- `eta`：风机效率；
- `eta_t`：传动效率；
- 结果单位为 kW。

分别计算容易时期和困难时期轴功率。

### 14.3 所需电机功率

```text
N_motor_required =
    max(N_shaft_easy, N_shaft_hard) × K_N
```

风机装机总功率：

```text
N_motor_installed = motor_kw × motor_count
```

要求：

```text
N_motor_installed >= N_motor_required
```

否则淘汰。

### 14.4 响应中的功率余量

当前代码使用困难时期轴功率计算：

```text
powerMargin =
    (N_motor_installed - N_shaft_hard)
    / N_motor_installed × 100%
```

该值不是按照已经乘过 `K_N` 的 `N_motor_required` 计算。正式确定接口定义时，应明确功率余量采用哪一种口径。

---

## 15. 候选评分

通过所有校核后，调用：

```cpp
scoreCandidate(...);
```

### 15.1 困难时期效率分

```text
sHard = min(etaHard / 0.83, 1)
```

### 15.2 容易时期效率分

```text
sEasy = min(etaEasy / 0.83, 1)
```

### 15.3 电机利用率分

困难时期电机利用率：

```text
utilization = N_shaft_hard / N_motor_installed
```

以 80% 利用率为最佳点：

```text
sMotor = max(0, 1 - abs(utilization - 0.80) / 0.80)
```

### 15.4 总分

```text
score =
    0.55 × sHard
  + 0.35 × sEasy
  + 0.10 × sMotor
```

所有候选按 `score` 降序排序，第一台保存为 `best`。Proto 响应目前没有独立的 `best` 字段，客户端应把 `candidates[0]` 视为最佳候选。

---

## 16. 响应生成

`converters.cpp::buildSelectionResponse()` 将内部结果转换为 Proto。

响应内容包括：

- 容易时期 `Q、H、R`；
- 困难时期 `Q、H、R`；
- 启用风机总数；
- 初筛淘汰数；
- 初筛后淘汰数；
- 按评分排序的候选列表；
- 算法步骤日志。

每个候选包含：

- 型号和电机配置；
- 双时期目标工作点；
- 双时期效率；
- 双时期轴功率；
- 所需电机功率；
- 双时期转速；
- 功率余量；
- 综合评分；
- 原始性能曲线点；
- 风机产品和安装信息。

`candidateToProto()` 会把数据库加载的性能点也放入 `plotData.curvePoints`，因此正式客户端可以直接使用响应绘制风机曲线，不需要访问数据库。

---

## 17. 错误处理

| 场景 | 当前处理 |
|---|---|
| 风量或风压不为正数 | `INVALID_ARGUMENT` |
| 数据库文件不存在 | `INTERNAL` |
| 数据库无法打开 | `INTERNAL` |
| 表或字段不存在 | `INTERNAL` |
| 没有启用风机 | `INTERNAL` |
| 启用风机基础数据非法 | `INTERNAL` |
| 曲线点少于 5 个 | `INTERNAL` |
| 多项式拟合矩阵奇异 | `INTERNAL` |
| 某台风机没有工作点 | 正常淘汰该风机 |
| 转速越界 | 正常淘汰该风机 |
| 效率不合格 | 正常淘汰该风机 |
| 装机功率不足 | 正常淘汰该风机 |
| 所有风机都被淘汰 | 正常响应，候选列表为空 |

需要注意：当前只要一台启用风机在数据库加载或拟合阶段抛出异常，就可能中断整次请求。后续可考虑把“数据库整体错误”和“单台风机数据错误”分开处理。

---

## 18. 数据库初始化与正式读取的区别

### 18.1 正式运行链路

正式服务运行时：

```text
C++ fan_db.cpp
    → SQLite只读查询
    → FanModel
    → 选型算法
```

正式后端不会调用 Python 前端。

### 18.2 初始化脚本

`scripts/init_fan_database.py` 用于开发阶段重建数据库：

```text
frontend/fan_db.py 中的 FAN_DB
    → init_fan_database.py
    → 删除并重建 fans 和 fan_curve_points
    → 写入 data/fans.db
```

该脚本包含：

```sql
DROP TABLE IF EXISTS fan_curve_points;
DROP TABLE IF EXISTS fans;
```

所以执行它会重建数据库，不应作为普通的后端启动步骤，也不应在生产环境随意执行。

当前数据库初始化脚本仍依赖 `frontend.fan_db` 中的数据模型。若后续建立正式的数据导入工具，建议把初始化数据和导入逻辑移出测试前端模块。

---

## 19. 构建和运行

### 19.1 编译后端

```powershell
python scripts/build_backend.py
```

产物：

```text
backend/build/fan_selector_server.exe
```

### 19.2 启动服务

```powershell
python scripts/run_server.py
```

### 19.3 指定数据库

PowerShell 示例：

```powershell
$env:FAN_DB_PATH = "D:\fan-selector\data\fans.db"
python scripts/run_server.py
```

### 19.4 闭环测试

```powershell
python scripts/run_test.py
```

测试脚本会：

1. 启动 C++ 服务；
2. 通过 Python gRPC 客户端发送请求；
3. 执行正常选型、自定义系数、全部淘汰、非法参数和一致性测试；
4. 关闭 C++ 服务。

---

## 20. 当前实现需要特别注意的事项

### 20.1 数据库是首次请求加载并永久缓存

更新数据库后必须重启服务。若正式运行需要热更新，应增加明确的缓存刷新策略。

### 20.2 `rejectedByEff` 名称不完全准确

内部 `rejectedEff` 不仅统计效率淘汰，还统计：

- 无曲线交点；
- 转速越界；
- 效率不合格；
- 装机功率不足。

它实际表示“初筛后详细校核淘汰数”。

### 20.3 Proto 字段语义需要固定

当前 `speedRatio` 实际为：

```text
困难时期转速 / 容易时期转速
```

字段注释和正式前端理解应保持一致。

### 20.4 输入参数校验还可以加强

当前服务只检查风量和风压为正数，没有在后端限制：

- 困难时期是否必须大于容易时期；
- `K、K_N、eta_t、eta_min` 的合理上限；
- 效率参数是否小于等于 1。

正式上线前应由后端执行完整校验，不能只依赖客户端。

### 20.5 数据访问与曲线拟合尚未拆层

`fan_db.cpp` 既负责 SQL，又负责单位转换和曲线拟合。若以后切换 PostgreSQL/MySQL 或增加数据热更新，建议拆分为：

```text
fan_repository      数据库查询
fan_mapper          数据库记录到 FanModel
fan_curve_service   曲线拟合
selector            纯选型算法
```

---

## 21. 后端核心流程总结

```text
1. 客户端通过 SelectFan 发送双工况参数
2. server.cpp 校验请求并取得默认系数
3. engine.cpp 计算双时期选型风量和管网阻力
4. selector.cpp 调用 fanDb() 获取启用风机
5. fan_db.cpp 首次从 SQLite 只读加载并缓存风机
6. selector.cpp 对风机进行能力范围初筛
7. 对通过风机拟合额定风压曲线和效率曲线
8. 求两个时期风机曲线与管网曲线的基准交点
9. 根据相似定律计算两个时期所需转速
10. 校核转速范围、最低效率和装机功率
11. 对合格风机计算综合评分并排序
12. converters.cpp 生成 Proto 响应
13. gRPC 将结果返回正式客户端
```

从职责边界来看，后端对外只暴露业务选型接口；数据库查询属于后端内部实现。正式客户端不需要知道数据库位置、表结构或 SQL，只需要遵循 Proto 定义发送请求并读取响应。
