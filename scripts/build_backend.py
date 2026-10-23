# -*- coding: utf-8 -*-
"""
编译 C++ 后端

用法：python scripts/build_backend.py（从 v4 根目录）
前置：安装 msys2 mingw64 的 grpc 和 protobuf
"""
import subprocess
import sys
import os

if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend = os.path.join(base, 'backend')
    build = os.path.join(backend, 'build')

    os.makedirs(build, exist_ok=True)

    env = os.environ.copy()
    env['PATH'] = r'C:\msys64\mingw64\bin;' + env.get('PATH', '')

    print('[1/2] cmake configure ...')
    r = subprocess.run(
        ['cmake', '..', '-G', 'MinGW Makefiles',
         '-DCMAKE_PREFIX_PATH=C:/msys64/mingw64',
         '-DCMAKE_BUILD_TYPE=Release'],
        cwd=build, env=env,
    )
    if r.returncode != 0:
        print('cmake configure 失败')
        sys.exit(1)

    print('\n[2/2] cmake build ...')
    r = subprocess.run(
        ['cmake', '--build', '.', '-j4'],
        cwd=build, env=env,
    )
    if r.returncode != 0:
        print('编译失败')
        sys.exit(1)

    exe = os.path.join(build, 'fan_selector_server.exe')
    print(f'\n编译成功: {exe}')
