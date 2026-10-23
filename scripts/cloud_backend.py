"""Build and supervise one local backend per Streamlit Python process."""
import atexit
import os
from pathlib import Path
import subprocess
import threading

import grpc

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".cloud-build"
_lock = threading.Lock()
_process = None


def _stop():
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
            _process.wait()


atexit.register(_stop)


def ensure_backend():
    global _process
    with _lock:
        if _process is not None and _process.poll() is None:
            return
        executable = BUILD / "fan_selector_server"
        # Reconfigure/build on each new process so source updates are respected.
        subprocess.run(
            ["cmake", "-S", str(ROOT / "backend"), "-B", str(BUILD),
             "-DCMAKE_BUILD_TYPE=Release"], check=True, timeout=180,
        )
        subprocess.run(
            ["cmake", "--build", str(BUILD), "--parallel", "2"],
            check=True, timeout=600,
        )
        env = os.environ.copy()
        env["FAN_DB_PATH"] = str(ROOT / "data" / "fans.db")
        _process = subprocess.Popen([str(executable), "50051"], cwd=ROOT, env=env)
        channel = grpc.insecure_channel("localhost:50051")
        try:
            grpc.channel_ready_future(channel).result(timeout=30)
            if _process.poll() is not None:
                raise RuntimeError("Backend exited during startup")
        except Exception:
            _stop()
            raise
        finally:
            channel.close()
