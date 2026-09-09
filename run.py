"""
一键启动 — 双击此文件即可。
依赖走全局 Python (PyQt5/pynput/requests 已装在 site-packages)。
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")


def main():
    print("[*] 检查依赖（全局 Python）...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "-r", os.path.join(HERE, "requirements.txt")],
            check=False,
        )
    except Exception as e:
        print(f"[!] pip install 跳过: {e}")

    main_py = os.path.join(SRC, "stock_desktop.py")
    print(f"[*] 启动 {main_py}")
    print()
    os.chdir(HERE)
    # 关键：把 src/ 加到 sys.path，让 stock_desktop.py 能 import stock_fetcher
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    with open(main_py, "r", encoding="utf-8") as f:
        code = f.read()
    exec(compile(code, main_py, "exec"),
         {"__name__": "__main__", "__file__": main_py})


if __name__ == "__main__":
    main()
