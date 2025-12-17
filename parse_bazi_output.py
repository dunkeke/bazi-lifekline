# parse_bazi_output.py
import subprocess
import sys
import re
import pandas as pd


def run_bazi_py(py_path: str, args: list[str]) -> str:
    """
    黑盒运行 bazi.py，不 import、不改动源程序
    """
    cmd = [sys.executable, py_path] + args
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    output = p.stdout or ""
    if p.stderr:
        output += "\n[stderr]\n" + p.stderr
    return output


# 示例流年行格式（需与你 bazi.py 输出微调一次即可）
# 年龄  年份  干支  ...其它说明
RE_LIUNIAN = re.compile(
    r'^\s*(\d+)\s+(\d{4})\s+([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\s*(.*)$',
    re.M
)

# 示例大运行格式
RE_DAYUN = re.compile(
    r'^\s*(\d+)\s+([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])\s*(.*)$',
    re.M
)


def parse_dayun_liunian(text: str):
    dayun = [
        {"start_age": int(a), "gz": gz, "desc": desc.strip()}
        for a, gz, desc in RE_DAYUN.findall(text)
    ]

    liunian = [
        {"age": int(a), "year": int(y), "gz": gz, "desc": desc.strip()}
        for a, y, gz, desc in RE_LIUNIAN.findall(text)
    ]

    return pd.DataFrame(dayun), pd.DataFrame(liunian)
