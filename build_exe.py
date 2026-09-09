# -*- coding: utf-8 -*-
"""
打包脚本 — 用 PyInstaller 生成单文件 exe
========================================
用法：
    pip install pyinstaller
    python build_exe.py

输出：
    dist/stock_desktop.exe   （单文件，约 30-40MB）
"""
import os
import shutil
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
ENTRY = os.path.join(SRC, "stock_desktop.py")
ICON = os.path.join(HERE, "assets", "tray_icon.ico")
NAME = "ashare-watch-helper"


def main():
    # 检查 pyinstaller
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("[!] PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 检查入口文件
    if not os.path.exists(ENTRY):
        print(f"[!] 找不到入口: {ENTRY}")
        sys.exit(1)

    # 构造 PyInstaller 命令
    # --onefile: 单文件
    # --noconsole: 不弹黑色窗口
    # --clean: 清理缓存
    # --name: 输出文件名
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--clean",
        f"--name={NAME}",
        "--paths", SRC,  # 关键：让 PyInstaller 找到 stock_fetcher.py
        # 隐藏导入（防止某些情况下 PyInstaller 漏掉）
        "--hidden-import", "pynput.keyboard",
        "--hidden-import", "pynput.mouse",
        # 排除大依赖（减小体积）
        # 不加 --exclude，因为 PyQt5 必须保留
        ENTRY,
    ]

    if os.path.exists(ICON):
        cmd.extend(["--icon", ICON])

    print("[*] 正在打包...")
    print("    CMD:", " ".join(cmd))
    print()

    # 清理旧产物
    for p in ["build", "dist"]:
        p = os.path.join(HERE, p)
        if os.path.exists(p):
            shutil.rmtree(p, ignore_errors=True)
    spec = os.path.join(HERE, f"{NAME}.spec")
    if os.path.exists(spec):
        os.remove(spec)

    # 执行打包
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        print(f"\n[!] 打包失败 (exit code {result.returncode})")
        sys.exit(result.returncode)

    # 报告
    exe_path = os.path.join(HERE, "dist", f"{NAME}.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print()
        print(f"[OK] 打包完成: {exe_path}")
        print(f"     大小: {size_mb:.1f} MB")
        print()
        print("首次运行会在 exe 同级目录生成 monitor_config.json")
        print("双击即可启动。")
    else:
        print("[!] 找不到生成的 exe，请查看上面的 PyInstaller 日志")
        sys.exit(1)


if __name__ == "__main__":
    main()
