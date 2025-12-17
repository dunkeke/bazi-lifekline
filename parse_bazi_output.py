import subprocess
import sys

def run_bazi_py(py_path: str, args: list[str]) -> str:
    # 用当前 Python 解释器运行，保证依赖一致
    cmd = [sys.executable, py_path] + args
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    # bazi.py 有大量 print，这里直接拿 stdout
    out = p.stdout if p.stdout else ""
    # 若有报错也带上，便于 UI 展示
    if p.stderr:
        out += "\n[stderr]\n" + p.stderr
    return out
