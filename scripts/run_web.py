# -*- coding: utf-8 -*-
"""
启动 Streamlit Web UI

用法：python scripts/run_web.py（从 v4 根目录）
注意：需要先启动 C++ 后端（python scripts/run_server.py）
"""
import subprocess
import sys
import os

if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = os.path.join(base, 'frontend', 'app.py')
    subprocess.run([sys.executable, '-m', 'streamlit', 'run', app], cwd=base)
