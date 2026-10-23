# -*- coding: utf-8 -*-
"""
生成 Proto Python 代码（给前端用）

用法：python scripts/generate_proto.py（从 v4 根目录）
"""
import subprocess
import sys
import os
import re

if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proto_dir = os.path.join(base, 'proto')
    out_dir = os.path.join(base, 'frontend', 'generated')

    os.makedirs(out_dir, exist_ok=True)

    cmd = [
        sys.executable, '-m', 'grpc_tools.protoc',
        f'-I{proto_dir}',
        f'--python_out={out_dir}',
        f'--grpc_python_out={out_dir}',
        os.path.join(proto_dir, 'fan_selector.proto'),
    ]
    print(f'执行: {" ".join(cmd)}')
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f'生成失败 (exit={result.returncode})')
        sys.exit(1)

    # 修复 grpc 文件中的 import 路径
    grpc_file = os.path.join(out_dir, 'fan_selector_pb2_grpc.py')
    if os.path.exists(grpc_file):
        with open(grpc_file, 'r') as f:
            content = f.read()
        content = re.sub(
            r'^import fan_selector_pb2 as',
            'from frontend.generated import fan_selector_pb2 as',
            content,
            flags=re.MULTILINE,
        )
        with open(grpc_file, 'w') as f:
            f.write(content)
        print('已修复 grpc import 路径')

    print(f'生成成功 → {out_dir}/')
