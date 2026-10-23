# V7 风机数据数据库化改造方案

## 1. 改造背景

当前 V5/V7 的风机型号、额定参数、性能曲线点都硬编码在 `backend/src/fan_db.cpp` 中。

这会带来几个问题：

1. 新增、删除、修改风机型号必须改 C++ 代码并重新编译。
2. 前后端可能维护重复数据，容易不一致。
3. 风机性能曲线属于业务数据，不应该和算法代码耦合。
4. 后续如果要支持更多厂家、系列、版本、导入导出，会很难扩展。

V7 的第一步迭代目标是：**将具体风机数据从代码中移出，存储到数据库中，C++ 后端运行时从数据库读取风机数据。**

## 2. 改造目标

### 必须实现

- 风机型号数据不再硬编码在 `fan_db.cpp`。
- 风机基础参数存入数据库。
- 风机曲线点存入数据库。
- C++ 后端启动或首次选型时从数据库读取数据。
- 现有选型算法尽量不变，仍然使用 `FanModel`、`FanCurvePoint` 等内部结构。
- 前端绘图继续使用后端返回的 `CandidateFan.plotData.curvePoints`。
- 原有测试用例结果尽量保持一致。

### 暂不实现

- 不做复杂后台管理系统。
- 不做用户在线编辑风机数据库。
- 不做多用户权限。
- 不引入大型数据库服务。
- 不重写选型算法。

## 3. 推荐数据库方案

第一阶段建议使用 **SQLite**。

原因：

- 单文件数据库，部署简单。
- C++ 和 Python 都能直接访问。
- 不需要额外启动数据库服务。
- 适合当前风机数据量。
- 后续如需要，可迁移到 MySQL/PostgreSQL。

建议数据库文件路径：

```text
data/fans.db
```

## 4. 数据库表设计

### 4.1 风机型号表：`fans`

用于存储风机基础信息。

```sql
CREATE TABLE fans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL UNIQUE,
    series TEXT NOT NULL,
    fan_type TEXT NOT NULL DEFAULT 'counter_rotating',
    rated_rpm REAL NOT NULL,
    rpm_min REAL NOT NULL,
    rpm_max REAL NOT NULL,
    motor_kw REAL NOT NULL,
    motor_count INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

字段说明：

| 字段 | 含义 |
|---|---|
| `id` | 数据库内部主键 |
| `model_id` | 风机型号，如 `FBCDZ(B)-6-No22` |
| `series` | 风机系列 |
| `fan_type` | 风机类型 |
| `rated_rpm` | 额定转速 |
| `rpm_min` | 最小变频转速 |
| `rpm_max` | 最大变频转速 |
| `motor_kw` | 单台电机功率 |
| `motor_count` | 电机数量 |
| `enabled` | 是否参与选型 |

### 4.2 风机曲线点表：`fan_curve_points`

用于存储风机额定转速下的性能曲线点。

```sql
CREATE TABLE fan_curve_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fan_id INTEGER NOT NULL,
    q_m3_min REAL NOT NULL,
    h_pa REAL NOT NULL,
    eta_percent REAL NOT NULL,
    point_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (fan_id) REFERENCES fans(id) ON DELETE CASCADE
);
```

字段说明：

| 字段 | 含义 |
|---|---|
| `fan_id` | 关联 `fans.id` |
| `q_m3_min` | 原始风量，单位 `m3/min` |
| `h_pa` | 风压，单位 `Pa` |
| `eta_percent` | 效率，单位 `%` |
| `point_order` | 曲线点顺序 |

注意：数据库保存原始曲线数据时建议继续使用 `m3/min` 和 `%`，因为这更接近产品样本数据。C++ 读取后再转换为内部计算单位：

```text
Q: m3/min -> m3/s，除以 60
eta: % -> 0~1，除以 100
```

## 5. 代码结构调整

### 5.1 当前结构

当前 `backend/src/fan_db.cpp` 同时承担了三个职责：

1. 存储硬编码风机数据。
2. 把原始数据转换成 `FanModel`。
3. 提供曲线拟合工具。

### 5.2 V7 目标结构

建议拆分为：

```text
backend/
  include/
    fan_db.hpp          # 风机数据访问接口
    fan_repository.hpp  # 数据库读取接口，可选
  src/
    fan_db.cpp          # 保留曲线拟合、数据转换公共逻辑
    fan_repository.cpp  # SQLite 读取实现
```

或者更简单一点，第一阶段也可以只保留：

```text
backend/
  include/fan_db.hpp
  src/fan_db.cpp
```

但 `fan_db.cpp` 内部不再放硬编码数据，而是从 SQLite 读取。

## 6. C++ 接口设计

当前接口：

```cpp
const std::vector<FanModel>& fan_db();
```

建议第一阶段保持这个接口不变，减少对 `selector.cpp` 的影响。

改造后：

```cpp
const std::vector<FanModel>& fan_db();
```

内部行为变为：

1. 第一次调用时读取 `data/fans.db`。
2. 查询启用的风机。
3. 查询每台风机的曲线点。
4. 转换成 `FanModel`。
5. 缓存在静态变量中。
6. 后续选型复用缓存。

伪代码：

```cpp
const std::vector<FanModel>& fan_db() {
    static const std::vector<FanModel> db = load_fans_from_sqlite(default_db_path());
    return db;
}
```

这样 `selector.cpp` 基本不需要修改。

## 7. 数据库路径配置

建议支持三种方式，优先级从高到低：

1. 命令行参数指定。
2. 环境变量指定。
3. 默认路径 `data/fans.db`。

例如：

```bash
backend/build/fan_selector_server.exe 50051 data/fans.db
```

或者：

```bash
set FAN_DB_PATH=data/fans.db
python scripts/run_server.py
```

第一阶段可以先用默认路径，后续再加配置。

## 8. 数据迁移方案

需要新增一个脚本，把当前 `fan_db.cpp` 中的 5 款风机数据迁移到 SQLite。

建议脚本：

```text
scripts/init_fan_database.py
```

职责：

1. 创建 `data/fans.db`。
2. 创建 `fans` 表。
3. 创建 `fan_curve_points` 表。
4. 写入当前 5 款风机数据。
5. 可重复执行，支持删除旧库重建或 upsert。

执行方式：

```bash
python scripts/init_fan_database.py
```

## 9. 前端调整方案

当前 `frontend/fan_db.py` 主要用于首页展示数据库表格，真实绘图已经使用后端返回的 `plotData`。

V7 可以分两步处理：

### 第一阶段

暂时保留 `frontend/fan_db.py`，但不再把它视为权威数据源。

前端选型、绘图仍以 gRPC 响应为准。

### 第二阶段

新增后端接口，例如：

```proto
rpc ListFans(ListFansRequest) returns (ListFansResponse);
```

前端首页风机数据库表格也从后端读取。

这样可以彻底删除或弱化 `frontend/fan_db.py`。

## 10. Proto 是否需要修改

第一阶段不需要修改 `proto/fan_selector.proto`。

原因：

- `SelectFan` 请求参数不变。
- `CandidateFan.plotData` 已经能返回曲线点。
- 数据库化是后端数据来源变化，不影响前后端通信协议。

后续如果需要前端展示完整风机库，可以再新增：

```proto
message ListFansRequest {}

message FanInfo {
  string modelId = 1;
  string series = 2;
  string fanType = 3;
  double ratedRpm = 4;
  double rpmMin = 5;
  double rpmMax = 6;
  double motorPower = 7;
  int32 motorCount = 8;
  int32 curvePointCount = 9;
}

message ListFansResponse {
  repeated FanInfo fans = 1;
}

service FanSelectorService {
  rpc SelectFan(FanSelectionRequest) returns (FanSelectionResponse);
  rpc ListFans(ListFansRequest) returns (ListFansResponse);
}
```

## 11. 构建依赖

如果 C++ 直接读取 SQLite，需要引入 SQLite C/C++ 依赖。

### Windows/MSYS2

可能需要安装：

```bash
pacman -S mingw-w64-x86_64-sqlite3
```

CMake 中增加：

```cmake
find_package(SQLite3 REQUIRED)

target_link_libraries(fan_selection_core PUBLIC SQLite::SQLite3)
```

如果 `find_package(SQLite3)` 不稳定，也可以手动查找：

```cmake
find_library(SQLITE3_LIBRARY sqlite3)
find_path(SQLITE3_INCLUDE_DIR sqlite3.h)
```

## 12. 测试方案

保留现有闭环测试：

```bash
python scripts/run_test.py
```

需要重点验证：

1. 数据库加载成功。
2. 风机数量仍为 5。
3. 标准工况推荐型号仍为 `FBCDZ(B)-6-No22`。
4. `plotData.curvePoints` 不为空。
5. 非法参数仍返回 `INVALID_ARGUMENT`。
6. 数据库文件缺失时，后端给出明确错误。

建议新增测试场景：

- 数据库为空。
- 某个风机曲线点少于 5 个。
- 某个风机缺失必填字段。
- 某个风机 `rpm_min > rpm_max`。
- 某个风机被设置为 `enabled = 0`。

## 13. 错误处理策略

后端启动或首次调用时，如果数据库异常，应返回清晰错误：

| 场景 | 建议处理 |
|---|---|
| 数据库文件不存在 | 返回 `INTERNAL`，提示数据库路径不存在 |
| 表不存在 | 返回 `INTERNAL`，提示请初始化数据库 |
| 风机数量为 0 | 返回 `INTERNAL` 或正常返回空候选，但日志提示 |
| 曲线点少于 5 个 | 跳过该风机，并写入日志 |
| 数据字段非法 | 跳过该风机，并写入日志 |

第一阶段建议严格一些：数据库或表错误直接失败，单台风机数据错误则跳过。

## 14. 分阶段实施计划

### 阶段 1：数据库文件和初始化脚本

- 新建 `data/fans.db`。
- 新增 `scripts/init_fan_database.py`。
- 把当前 5 款风机写入 SQLite。
- 暂不改 C++。

### 阶段 2：C++ 从 SQLite 读取

- 修改 `fan_db.cpp`。
- 移除硬编码风机原始数组。
- 实现 `load_fans_from_sqlite()`。
- 保持 `fan_db()` 对外接口不变。
- 修改 CMake 链接 SQLite。

### 阶段 3：验证选型结果一致性

- 编译后端。
- 运行 `scripts/run_test.py`。
- 比较推荐型号、评分、候选数量。
- 检查曲线绘图是否正常。

### 阶段 4：前端风机库展示改造

- 短期保留 `frontend/fan_db.py`。
- 后续新增 `ListFans` gRPC 接口。
- 前端首页数据库表格改为后端返回。
- 删除前端硬编码风机副本。

## 15. 最终目标结构

理想状态：

```text
V7/
  data/
    fans.db                     # 风机数据库
  backend/
    src/
      fan_db.cpp                # 从数据库读取 + 曲线拟合
      selector.cpp              # 选型算法，不关心数据来源
      engine.cpp                # 管网计算
      server.cpp                # gRPC 服务
  frontend/
    app.py                      # 只通过 gRPC 获取结果
    plotting/
      result.py                 # 使用 CandidateFan.plotData 绘图
  scripts/
    init_fan_database.py        # 初始化/重建数据库
    run_server.py
    run_web.py
    run_test.py
```

## 16. 关键原则

1. 风机数据是业务数据，不再写死在 C++ 源码中。
2. 选型算法尽量不感知数据库细节。
3. `FanModel` 作为算法层内部统一数据结构继续保留。
4. 第一阶段不修改 proto，降低风险。
5. 数据库使用原始工程单位保存，读取后转换为算法单位。
6. 后端是风机数据的唯一权威来源。
