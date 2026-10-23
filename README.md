# 矿井通风机选型系统 v4

> C++ 后端 + Python 前端，通过 gRPC 通信

## 架构

```
┌──────────────────────────┐      gRPC       ┌──────────────────────────┐
│    Python 前端            │  ◄──────────►  │    C++ 后端               │
│                          │   Port 50051    │                          │
│  Streamlit Web UI        │                 │  计算引擎 (engine)        │
│  Matplotlib 绑图         │                 │  风机数据库 (fan_db)      │
│  gRPC 客户端             │                 │  选型算法 (selector)      │
│                          │                 │  gRPC 服务端              │
└──────────────────────────┘                 └──────────────────────────┘
```

## 目录结构

```
v4/
├── proto/fan_selector.proto        # 共享的 gRPC 接口定义
├── backend/                        # C++ 后端
│   ├── CMakeLists.txt
│   ├── include/                    # 头文件 (config/models/engine/fan_db/selector/converters)
│   ├── src/                        # 实现 (engine/fan_db/selector/server/converters)
│   └── build/                      # 编译产物
│       └── fan_selector_server.exe
├── frontend/                       # Python 前端
│   ├── app.py                      # Streamlit Web UI (gRPC 客户端)
│   ├── config.py                   # 常量
│   ├── models.py                   # 数据结构 (仅绘图用)
│   ├── fan_db.py                   # 风机数据库 (仅绘图用)
│   ├── plotting/                   # 可视化模块
│   │   ├── font_config.py
│   │   ├── curves.py
│   │   └── result.py
│   └── generated/                  # Proto 生成的 Python 代码
├── data/fonts/msyh.ttc             # 中文字体
├── scripts/
│   ├── build_backend.py            # 一键编译 C++ 后端
│   ├── generate_proto.py           # 生成 Python Proto 代码
│   ├── run_server.py               # 启动 C++ Server
│   ├── run_web.py                  # 启动 Streamlit 前端
│   └── run_test.py                 # 闭环测试 (5 用例)
├── requirements.txt                # Python 依赖
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# C++ 依赖 (msys2 mingw64)
pacman -S mingw-w64-x86_64-grpc mingw-w64-x86_64-protobuf
```

### 2. 编译 C++ 后端

```bash
python scripts/build_backend.py
```

### 3. 生成 Proto 代码

```bash
python scripts/generate_proto.py
```

### 4. 运行闭环测试

```bash
python scripts/run_test.py
```

### 5. 启动系统

```bash
# 终端 1：启动 C++ 后端
python scripts/run_server.py

# 终端 2：启动前端
python scripts/run_web.py
```

浏览器打开 http://localhost:8501 即可使用。

## 闭环测试用例

| 用例 | 描述 | 验证点 |
|------|------|--------|
| 测试1 | 正常选型 | best = FBCDZ(B)-6-No22, score > 0.95 |
| 测试2 | 自定义系数 K=1.15 | Q_f 按系数缩放 |
| 测试3 | 全部淘汰 | has_result = false |
| 测试4 | 非法参数 | gRPC INVALID_ARGUMENT |
| 测试5 | 一致性校验 | 两次调用结果完全一致 |
