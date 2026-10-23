# -*- coding: utf-8 -*-
"""
v4 C++ 后端 gRPC 闭环测试

自动启动 C++ Server → Python 客户端跑 5 个测试 → 关闭 Server

用法：python scripts/run_test.py（从 v4 根目录）
"""
import subprocess
import sys
import os
import time

import grpc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from frontend.generated import fan_selector_pb2 as pb
from frontend.generated import fan_selector_pb2_grpc as pb_grpc

PORT = 50051
TOLERANCE = 0.01

CPP_SERVER = os.path.join(
    os.path.dirname(__file__), '..', 'backend', 'build', 'fan_selector_server.exe'
)


def start_cpp_server():
    exe = os.path.normpath(CPP_SERVER)
    if not os.path.exists(exe):
        raise FileNotFoundError(f'C++ server 未编译: {exe}\n请先运行: python scripts/build_backend.py')

    env = os.environ.copy()
    env['PATH'] = r'C:\msys64\mingw64\bin;' + env.get('PATH', '')
    env.setdefault(
        'FAN_DB_PATH',
        os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data', 'fans.db')),
    )

    proc = subprocess.Popen(
        [exe, str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            ch = grpc.insecure_channel(f'localhost:{PORT}')
            grpc.channel_ready_future(ch).result(timeout=1)
            ch.close()
            return proc
        except Exception:
            if proc.poll() is not None:
                stdout = proc.stdout.read().decode('utf-8', errors='replace')
                stderr = proc.stderr.read().decode('utf-8', errors='replace')
                raise RuntimeError(f'Server 启动失败\nstdout: {stdout}\nstderr: {stderr}')
    proc.kill()
    raise RuntimeError('Server 启动超时')


def call_select(stub, air_flow_easy, pressure_easy, air_flow_hard, pressure_hard, **kw):
    return stub.SelectFan(pb.FanSelectionRequest(
        airFlowEasy=air_flow_easy, pressureEasy=pressure_easy,
        airFlowHard=air_flow_hard, pressureHard=pressure_hard, **kw,
    ))


def assert_close(actual, expected, name, tol=TOLERANCE):
    if abs(actual - expected) > tol:
        raise AssertionError(f'{name}: 期望 {expected}, 实际 {actual}')


ALL_TESTS = []


def test(name):
    def deco(func):
        ALL_TESTS.append((name, func))
        return func
    return deco


@test('测试1-正常选型')
def test_normal(stub):
    resp = call_select(stub, 114.5, 2276, 129.5, 3050.2)
    assert_close(resp.easy.flowRate, 114.5, 'easy.flowRate')
    assert len(resp.candidates) > 0, 'should have candidates'
    best = resp.candidates[0]
    assert best.modelId == 'FBCDZ-6No23/2x315', f'best={best.modelId}'
    assert best.score > 0.90, f'score={best.score}'
    assert best.motorCount * best.motorPower == 630, \
        f'motor={best.motorCount * best.motorPower}'
    assert len(best.plotData.curvePoints) > 0, 'should have curve points'
    assert best.plotData.rpmMin > 0, f'rpmMin={best.plotData.rpmMin}'
    assert best.plotData.rpmMax > best.plotData.rpmMin, f'rpmMax={best.plotData.rpmMax}'
    assert best.baseFlowEasy > 0, f'baseFlowEasy={best.baseFlowEasy}'
    assert best.basePressEasy > 0, f'basePressEasy={best.basePressEasy}'
    assert best.baseFlowHard > 0, f'baseFlowHard={best.baseFlowHard}'
    assert best.basePressHard > 0, f'basePressHard={best.basePressHard}'


@test('测试2-自定义系数')
def test_custom(stub):
    resp = call_select(stub, 114.5, 2276, 129.5, 3050.2,
                       reserveCoeff=1.15, minEfficiency=0.75)
    assert_close(resp.easy.flowRate, 114.5 * 1.15, 'reserveCoeff=1.15', tol=0.1)


@test('测试3-全部淘汰')
def test_rejected(stub):
    resp = call_select(stub, 1000, 50000, 1000, 50000)
    assert len(resp.candidates) == 0, f'candidates={len(resp.candidates)}'


@test('测试4-非法参数')
def test_invalid(stub):
    try:
        stub.SelectFan(pb.FanSelectionRequest(
            airFlowEasy=-100, pressureEasy=2276,
            airFlowHard=129.5, pressureHard=3050))
        raise AssertionError('应返回错误')
    except grpc.RpcError as e:
        assert e.code() == grpc.StatusCode.INVALID_ARGUMENT, f'code={e.code()}'


@test('测试5-一致性校验')
def test_consistency(stub):
    resp1 = call_select(stub, 114.5, 2276, 129.5, 3050.2)
    resp2 = call_select(stub, 114.5, 2276, 129.5, 3050.2)
    best1, best2 = resp1.candidates[0], resp2.candidates[0]
    assert best1.modelId == best2.modelId
    assert_close(best1.score, best2.score, 'score consistency')


def main():
    print('=' * 60)
    print('矿井风机选型 v4 — C++ 后端闭环测试')
    print('=' * 60)

    print(f'\n[1/3] 启动 C++ Server ...')
    proc = start_cpp_server()
    print(f'  PID={proc.pid}, 端口={PORT}')

    passed = failed = 0
    errors = []

    try:
        print('\n[2/3] 执行测试 ...')
        channel = grpc.insecure_channel(f'localhost:{PORT}')
        stub = pb_grpc.FanSelectorServiceStub(channel)

        for name, func in ALL_TESTS:
            try:
                func(stub)
                print(f'  [PASS] {name}')
                passed += 1
            except Exception as e:
                print(f'  [FAIL] {name}: {e}')
                failed += 1
                errors.append((name, str(e)))

        channel.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f'\n[3/3] 结果: {passed}/{passed+failed} 通过')
    if errors:
        for n, m in errors:
            print(f'  {n}: {m}')
    result_msg = "闭环测试全部通过!" if failed == 0 else f"{failed} 个失败"
    print(f'\n{result_msg}')
    print(f'  C++ Server 已关闭')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
