# -*- coding: utf-8 -*-
"""
启动 C++ gRPC 后端

用法：python scripts/run_server.py [port]（从 v4 根目录）
"""
import subprocess
import sys
import os
                                
if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe = os.path.join(base, 'backend', 'build-ucrt', 'fan_selector_server.exe')

    if not os.path.exists(exe):
        print(f'未找到: {exe}')
        print('请先编译: python scripts/build_backend.py')
        sys.exit(1)

    port = sys.argv[1] if len(sys.argv) > 1 else '50051'

    env = os.environ.copy()
    env['PATH'] = r'C:\msys64\ucrt64\bin;' + env.get('PATH', '')
    env.setdefault('FAN_DB_PATH', os.path.join(base, 'data', 'fans.db'))

    print(f'启动 C++ gRPC Server (端口 {port}) ...')
    print(f'风机数据库: {env["FAN_DB_PATH"]}')
    result = subprocess.run([exe, port], env=env)
    sys.exit(result.returncode)
