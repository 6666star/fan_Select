# fan_selector.proto 接口规范文档

> 文件路径：`v4/proto/fan_selector.proto`
>
> 协议版本：Protocol Buffers 3（proto3）
>
> 包名：`fanSelector`
>
> 命名规范：字段使用小驼峰（camelCase），编号顺序排列

## 1. 概述

`fan_selector.proto` 是矿井通风机选型系统前后端通信的**唯一接口契约**。它定义了：

- **1 个服务**：`FanSelectorService` — 提供风机选型的 RPC 方法
- **4 个消息**：`FanSelectionRequest`、`PeriodResult`、`CandidateFan`、`FanSelectionResponse`

前端（Python Streamlit）作为 gRPC **客户端**，将用户输入的矿井工况参数打包为 `FanSelectionRequest`，发送给后端（C++ gRPC Server）。后端完成计算后返回 `FanSelectionResponse`，包含选型结果。

```
前端 ──FanSelectionRequest──→ 后端
前端 ←─FanSelectionResponse── 后端
```

---

## 2. 服务定义

```protobuf
service FanSelectorService {
  rpc SelectFan(FanSelectionRequest) returns (FanSelectionResponse);
}
```

| 方法名 | 请求类型 | 响应类型 | 说明 |
|--------|---------|---------|------|
| `SelectFan` | `FanSelectionRequest` | `FanSelectionResponse` | 一元 RPC，输入矿井工况参数，返回完整选型结果 |

- 通信模式：**一元调用**（Unary RPC），一请求一响应
- 默认端口：`50051`
- 传输协议：HTTP/2（gRPC 默认）

---

## 3. 消息定义

### 3.1 FanSelectionRequest — 选型请求

前端发送给后端的输入参数。

```protobuf
message FanSelectionRequest {
  double airFlowEasy       = 1;   // Easy period air demand (m³/min)
  double pressureEasy      = 2;   // Easy period ventilation resistance (Pa)
  double airFlowHard       = 3;   // Hard period air demand (m³/min)
  double pressureHard      = 4;   // Hard period ventilation resistance (Pa)
  double reserveCoeff      = 5;   // Air volume reserve coefficient K
  double powerMarginCoeff  = 6;   // Power margin coefficient Kn
  double transEfficiency   = 7;   // Transmission efficiency ηt
  double minEfficiency     = 8;   // Minimum efficiency requirement ηmin
}
```

| 字段 | 编号 | 类型 | 单位 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| `airFlowEasy` | 1 | double | m³/min | — | 容易时期需风量，必填，必须 > 0 |
| `pressureEasy` | 2 | double | Pa | — | 容易时期通风网路总阻力，必填，必须 > 0 |
| `airFlowHard` | 3 | double | m³/min | — | 困难时期需风量，必填，必须 > 0 |
| `pressureHard` | 4 | double | Pa | — | 困难时期通风网路总阻力，必填，必须 > 0 |
| `reserveCoeff` | 5 | double | — | 1.00 | 风量备用系数 K，范围 [1.0, 1.3] |
| `powerMarginCoeff` | 6 | double | — | 1.15 | 功率裕量系数 Kn，范围 [1.0, 1.3] |
| `transEfficiency` | 7 | double | — | 0.95 | 传动效率 ηt，范围 [0.8, 1.0] |
| `minEfficiency` | 8 | double | — | 0.70 | 最低效率要求 ηmin，范围 [0.5, 0.9] |

**校验规则：**
- `airFlowEasy`、`pressureEasy`、`airFlowHard`、`pressureHard` 必须全部 > 0，否则返回 `INVALID_ARGUMENT`
- 系数字段如果为 0，后端使用默认值

**输入示例：**
```json
{
  "airFlowEasy": 6870,
  "pressureEasy": 2276,
  "airFlowHard": 7770,
  "pressureHard": 3050.2,
  "reserveCoeff": 1.0,
  "powerMarginCoeff": 1.15,
  "transEfficiency": 0.95,
  "minEfficiency": 0.70
}
```

---

### 3.2 PeriodResult — 单工况计算结果

容易时期或困难时期的管道特性计算结果。

```protobuf
message PeriodResult {
  double flowRate          = 1;   // Calculated air volume (m³/s)
  double pressure          = 2;   // Calculated air pressure (Pa)
  double resistance        = 3;   // Pipeline resistance coefficient R (N·s²/m⁸)
}
```

| 字段 | 编号 | 类型 | 单位 | 说明 |
|------|------|------|------|------|
| `flowRate` | 1 | double | m³/s | 计算风量 = airFlow × reserveCoeff / 60 |
| `pressure` | 2 | double | Pa | 计算风压（直接取输入值） |
| `resistance` | 3 | double | N·s²/m⁸ | 管道阻力系数 R = pressure / flowRate² |

**计算公式：**
```
flowRate   = airFlow × reserveCoeff / 60    （m³/min → m³/s，含备用系数）
pressure   = pressureInput                   （直接使用输入风压）
resistance = pressure / flowRate²            （管道特性曲线 H = R·Q² 的系数）
```

---

### 3.3 CandidateFan — 候选风机

一台通过筛选的风机及其运行参数。字段编号顺序排列。

```protobuf
message CandidateFan {
  string modelId           = 1;   // Fan model ID, e.g. FBCDZ(B)-6-No22
  double ratedRpm          = 2;   // Rated speed (r/min)
  double motorPower           = 3;   // Single motor power (kW)
  int32  motorCount        = 4;   // Number of motors
  double flowEasy          = 5;   // Easy period operating point air volume (m³/s)
  double pressEasy         = 6;   // Easy period operating point air pressure (Pa)
  double flowHard          = 7;   // Hard period operating point air volume (m³/s)
  double pressHard         = 8;   // Hard period operating point air pressure (Pa)
  double efficiencyEasy    = 9;   // Easy period operating point efficiency (0~1)
  double efficiencyHard    = 10;  // Hard period operating point efficiency (0~1)
  double shaftPowerEasy    = 11;  // Easy period shaft power (kW)
  double shaftPowerHard    = 12;  // Hard period shaft power (kW)
  double requiredPower     = 13;  // Required motor power (kW)
  double speedRatio        = 14;  // Speed ratio (easy / hard)
  double rpmEasy           = 15;  // Easy period operating speed (r/min)
  double rpmHard           = 16;  // Hard period operating speed (r/min)
  double powerMargin       = 17;  // Power margin (%)
  double score             = 18;  // Comprehensive score (0~1, higher is better)
}
```

| 字段 | 编号 | 类型 | 单位 | 说明 |
|------|------|------|------|------|
| `modelId` | 1 | string | — | 风机型号，如 `FBCDZ(B)-6-No22` |
| `ratedRpm` | 2 | double | r/min | 额定转速 |
| `motorPower` | 3 | double | kW | 单台电机功率 |
| `motorCount` | 4 | int32 | — | 电机数量（对旋式通常为 2） |
| `flowEasy` | 5 | double | m³/s | 容易时期工作点风量 |
| `pressEasy` | 6 | double | Pa | 容易时期工作点风压 |
| `flowHard` | 7 | double | m³/s | 困难时期工作点风量 |
| `pressHard` | 8 | double | Pa | 困难时期工作点风压 |
| `efficiencyEasy` | 9 | double | — | 容易时期工作点效率（0~1） |
| `efficiencyHard` | 10 | double | — | 困难时期工作点效率（0~1） |
| `shaftPowerEasy` | 11 | double | kW | 容易时期轴功率 |
| `shaftPowerHard` | 12 | double | kW | 困难时期轴功率 |
| `requiredPower` | 13 | double | kW | 所需电机功率 = max(shaftPowerEasy, shaftPowerHard) × powerMarginCoeff |
| `speedRatio` | 14 | double | — | 转速比 = rpmEasy / rpmHard（≤ 1） |
| `rpmEasy` | 15 | double | r/min | 容易时期运行转速 |
| `rpmHard` | 16 | double | r/min | 困难时期运行转速（通常 = 额定转速） |
| `powerMargin` | 17 | double | % | 功率余量 = (总装机 - requiredPower) / 总装机 × 100 |
| `score` | 18 | double | — | 综合评分（0~1，越大越优） |

**设计说明：**
- 已删除冗余字段：`series`、`fanType`（可由 `modelId` 查询）、`totalMotorKw`（= `motorPower` × `motorCount`）、`best`（取 `candidates[0]` 即可）
- 风机规格数据（曲线点、转速范围等）未来从独立接口获取，不在选型响应中传输

---

### 3.4 FanSelectionResponse — 选型响应

后端返回的完整选型结果。

```protobuf
message FanSelectionResponse {
  int32  code              = 1;   // Status code: 200 = success
  string msg               = 2;   // Response message
  PeriodResult easy        = 3;   // Easy period calculation result
  PeriodResult hard        = 4;   // Hard period calculation result
  int32  totalFans         = 5;   // Total fans in database
  int32  screenedOut       = 6;   // Screened out by range mismatch
  int32  rejectedByEff     = 7;   // Rejected by efficiency
  repeated CandidateFan candidates = 8;  // Candidate list, sorted by score desc
  repeated string steps    = 9;   // Computation log for debugging
}
```

| 字段 | 编号 | 类型 | 说明 |
|------|------|------|------|
| `code` | 1 | int32 | 状态码：200 = 成功，500 = 内部错误 |
| `msg` | 2 | string | 响应消息，如 `"success"` 或错误描述 |
| `easy` | 3 | PeriodResult | 容易时期计算结果 |
| `hard` | 4 | PeriodResult | 困难时期计算结果 |
| `totalFans` | 5 | int32 | 数据库中风机总数 |
| `screenedOut` | 6 | int32 | 初筛淘汰数量（风量/风压范围不匹配） |
| `rejectedByEff` | 7 | int32 | 效率不达标淘汰数量 |
| `candidates` | 8 | repeated CandidateFan | 候选风机列表，按 score 降序排列，取 `candidates[0]` 即为最佳推荐 |
| `steps` | 9 | repeated string | 计算过程日志，用于调试和展示 |

**判断是否有合格候选：** 前端通过 `len(candidates) > 0` 判断，无需额外的 `hasResult` 字段。

---

## 4. 数据流示例

以标准测试工况为例：

**请求：**
```json
{
  "airFlowEasy": 6870,
  "pressureEasy": 2276,
  "airFlowHard": 7770,
  "pressureHard": 3050.2,
  "reserveCoeff": 1.0,
  "powerMarginCoeff": 1.15,
  "transEfficiency": 0.95,
  "minEfficiency": 0.70
}
```

**响应关键字段：**
```json
{
  "code": 200,
  "msg": "success",
  "easy":  { "flowRate": 114.5,  "pressure": 2276.0,  "resistance": 0.173588 },
  "hard":  { "flowRate": 129.5,  "pressure": 3050.2,  "resistance": 0.181885 },
  "totalFans": 5,
  "screenedOut": 2,
  "candidates": [
    {
      "modelId": "FBCDZ(B)-6-No22",
      "score": 0.9812,
      "efficiencyEasy": 0.8165,
      "efficiencyHard": 0.8280,
      "speedRatio": 0.9432,
      "motorPower": 315,
      "motorCount": 2
    }
  ]
}
```

---

## 5. 错误处理

| 场景 | `code` | `msg` | gRPC 状态码 |
|------|--------|-------|-------------|
| 正常返回 | 200 | `"success"` | `OK` |
| 全部淘汰 | 200 | `"success"` | `OK`（`candidates` 为空） |
| 输入参数非法 | — | — | `INVALID_ARGUMENT` |
| 服务端内部错误 | 500 | 错误描述 | `INTERNAL` |
| 服务不可达 | — | — | `UNAVAILABLE` |

---

## 6. 前后端调用代码

### Python 客户端（前端）

```python
import grpc
from frontend.generated import fan_selector_pb2 as pb
from frontend.generated import fan_selector_pb2_grpc as pb_grpc

channel = grpc.insecure_channel("localhost:50051")
stub = pb_grpc.FanSelectorServiceStub(channel)

resp = stub.SelectFan(pb.FanSelectionRequest(
    airFlowEasy=6870, pressureEasy=2276,
    airFlowHard=7770, pressureHard=3050.2,
    reserveCoeff=1.0, powerMarginCoeff=1.15,
    transEfficiency=0.95, minEfficiency=0.70,
))

print(f"状态: {resp.code} {resp.msg}")
best = resp.candidates[0]  # 按 score 降序，第一个即最佳
print(f"最佳风机: {best.modelId}")
print(f"评分: {best.score:.4f}")
```

### C++ 服务端（后端）

```cpp
class FanSelectorServiceImpl final
    : public fanSelector::FanSelectorService::Service {

    grpc::Status SelectFan(
        grpc::ServerContext* ctx,
        const fanSelector::FanSelectionRequest* req,
        fanSelector::FanSelectionResponse* resp) override {

        // 1. 校验输入
        if (req->airfloweasy() <= 0 || req->pressureeasy() <= 0 ...)
            return {grpc::INVALID_ARGUMENT, "参数非法"};

        // 2. 计算管道特性
        auto dual = run_dual(...);

        // 3. 运行选型算法
        auto result = run_selector(dual, ...);

        // 4. 填充响应
        *resp = build_selection_response(dual, result);
        resp->set_code(200);
        resp->set_msg("success");
        return grpc::Status::OK;
    }
};
```

**注意：** protobuf C++ 生成的访问器将 camelCase 字段名转为全小写，例如 proto 中的 `airFlowEasy` 对应 C++ 的 `airfloweasy()` / `set_airfloweasy()`。Python 端保持原始 camelCase。

---

## 7. 扩展指南

如需增加新功能（如噪声参数、多工况支持），修改步骤：

1. **编辑 `proto/fan_selector.proto`** — 添加新字段（使用下一个可用编号）
2. **重新生成代码**：
   - C++ 端：CMake 重新编译会自动生成
   - Python 端：运行 `python scripts/generate_proto.py`
3. **更新后端逻辑** — 在 `server.cpp` / `converters.cpp` 中填充新字段
4. **更新前端展示** — 在 `app.py` 中读取新字段并展示

**命名规范：**
- 字段名使用小驼峰（camelCase），语义清晰，避免缩写歧义
- 消息名使用大驼峰（PascalCase）
- 编号按顺序递增，不跳号
- 冗余字段（可由其他字段计算得到的）不写入 proto
- 注释使用英文

proto3 的向后兼容性保证：新增字段不影响旧版客户端，旧字段删除后编号不可复用。
