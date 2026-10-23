# v7 云端部署

本项目保留 C++ 计算引擎，云端入口为根目录 `streamlit_app.py`。
入口会在 Linux 上编译并启动本地 gRPC 服务，再加载原有界面。
首次启动会比普通 Python 应用更慢。编译输出在 Streamlit 日志中。

1. 将项目上传 GitHub（不要上传虚拟环境、编译产物或 secrets）。
2. 登录 https://share.streamlit.io 并授权访问该仓库。
3. Create app，选择仓库和分支，入口填写 `streamlit_app.py`。
4. Advanced settings 中选择 Python 3.11，然后 Deploy。
5. 部署成功后使用分配的 `https://….streamlit.app` 地址。

`packages.txt` 安装 Linux C++ 系统依赖；`requirements.txt` 安装 Python 依赖。
必须保留 `data/fans.db`、`data/images`、`proto` 和 C++ 源码。
现有 `frontend/app.py` 仍可按原有本地方式启动。

云端发布后请验证：后端已连接、默认参数选型、曲线及报告下载。
本地 Windows 检查不能代替 Linux 云端编译与实际部署验证。
