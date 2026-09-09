# -*- coding: utf-8 -*-
"""
桌面悬浮股票盯盘助手 — 透明窗口版
===================================
功能：
- 实时 A 股行情（新浪 + 腾讯双源）
- 背景完全透明 / 可滑块调节
- 自定义字体（家族 / 大小 / 颜色）
- 涨红跌绿（中国 A 股习惯）颜色可自定义
- 全局快捷键（自定义组合键，默认 Alt+E）
- 系统托盘
- 配置实时保存

支持中文路径、打包成单文件 exe，配置文件存放在 exe 同级目录。

入口：python stock_desktop.py  或  stock_desktop.exe
"""
from __future__ import annotations

import io
import json
import copy
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from typing import Any, Optional

from PyQt5.QtCore import (
    Qt, QPoint, QTimer, QSize, pyqtSignal, QObject, QEvent
)
from PyQt5.QtGui import (
    QColor, QFont, QIcon, QPixmap, QPainter, QPen, QBrush,
    QLinearGradient, QKeySequence, QFontDatabase, QPainterPath
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QDialog, QListWidget, QLineEdit, QComboBox, QCheckBox,
    QSpinBox, QSlider, QDoubleSpinBox, QMessageBox, QMenu, QFrame,
    QInputDialog, QShortcut, QSizePolicy, QGroupBox, QFormLayout,
    QFontComboBox, QColorDialog, QTabWidget, QStyle
)

# Windows 高 DPI
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 数据源
from stock_fetcher import get_stock_fetcher  # noqa: E402

# pynput（可选）
try:
    from pynput import keyboard as _pynput_kb
    HAS_PYNPUT = True
except Exception:
    HAS_PYNPUT = False

# 系统托盘（可选）
try:
    from PyQt5.QtWidgets import QSystemTrayIcon as _QSystemTrayIcon
    _HAS_TRAY = True
except Exception:
    _HAS_TRAY = False


# =========================================================================
# 路径 / 常量
# =========================================================================
def _app_dir() -> str:
    """获取应用根目录。

    - 开发模式（直接跑 .py）：返回脚本所在目录的父目录（即项目根）
    - 打包模式（PyInstaller 单文件）：返回 exe 所在目录

    这样配置文件 monitor_config.json 始终在 exe 旁边，方便用户备份/编辑。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：sys.executable 指向 exe
        # sys._MEIPASS 是临时解压目录（不要写配置到这里）
        return os.path.dirname(os.path.abspath(sys.executable))
    # 开发模式：__file__ 在 src/stock_desktop.py，父目录的父目录是项目根
    here = os.path.abspath(os.path.dirname(__file__))
    # 支持中文路径：全程用 str，不用 bytes
    return os.path.dirname(here) if os.path.basename(here) == "src" else here


# 配置文件路径：在 exe / 项目根目录下
CONFIG_FILE = os.path.join(_app_dir(), "monitor_config.json")
FONT_FAMILY_DEFAULT = "Microsoft YaHei"

# 图标字符（用 emoji 跨平台一致）
ICON_COG = "\u2699"        # ⚙
ICON_CLOSE = "\u2715"      # ✕
ICON_UP = "\u25B2"         # ▲
ICON_DOWN = "\u25BC"       # ▼
ICON_DOT = "\u2022"        # •
ICON_REFRESH = "\u21BB"    # ↻
ICON_HIDE = "\u2014"       # — （em dash，表示最小化）
ICON_PLUS = "+"
ICON_EYE = "\u25C9"        # ◉ （在线指示）
ICON_OFFLINE = "\u25CC"    # ◌

# 默认值
DEFAULT_THEME = "dark"
DEFAULT_OPACITY = 0.0
DEFAULT_FONT_SIZE = 9
DEFAULT_REFRESH_INTERVAL = 500
DEFAULT_HOTKEY = "<alt>+e"  # 默认 Alt+E
DEFAULT_STOCKS = [
    {"code": "600519", "alias": "贵州茅台"},  # 默认贵州茅台
]

# 主题色（每条都可被用户覆盖）
DEFAULT_COLORS = {
    "dark": {
        "text":      "#d0d0d8",
        "price":     "#f0f0f5",
        "header":    "#7a7a82",
        "time":      "#5a5a62",
        "sep":       "#3a3a3a",
        "up":        "#ff5252",   # 红涨
        "down":      "#26d07c",   # 绿跌
        "neutral":   "#d0d0d8",
        "btn":       "#909098",
        "btn_hover": "#ffffff",
        "btn_close_hover": "#ff4040",
        "bg":        "#0a0a0a",
        "border":    "#262626",
    },
    "light": {
        "text":      "#202028",
        "price":     "#101018",
        "header":    "#606068",
        "time":      "#808088",
        "sep":       "#c0c0c0",
        "up":        "#d62828",
        "down":      "#1f9d55",
        "neutral":   "#202028",
        "btn":       "#505058",
        "btn_hover": "#101018",
        "btn_close_hover": "#ff2020",
        "bg":        "#f0f0f0",
        "border":    "#a0a0a0",
    },
}

DEFAULT_CONFIG: dict = {
    "stocks": copy.deepcopy(DEFAULT_STOCKS),
    "refresh_interval": DEFAULT_REFRESH_INTERVAL,
    "window": {
        "x": 100, "y": 100,
        "opacity": DEFAULT_OPACITY,
        "topmost": True,
        "font_size": DEFAULT_FONT_SIZE,
        "font_family": FONT_FAMILY_DEFAULT,
        "theme": DEFAULT_THEME,
        "hotkey": DEFAULT_HOTKEY,
    },
    "colors": {},  # 颜色覆盖项：{theme: {key: "#rrggbb", ...}}
}


# =========================================================================
# 配置管理
# =========================================================================
class StockConfig:
    """配置文件读写 — 原子写、字段补齐、迁移。支持中文路径。"""

    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        # 确保父目录存在（exe 可能放在只读盘，但这里只是新建文件）
        try:
            os.makedirs(os.path.dirname(self.config_file) or ".", exist_ok=True)
        except Exception:
            pass
        self.config = self._load_config()
        self._migrate()
        self.save_config()

    def _load_config(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                # 支持中文路径：io.open + encoding='utf-8' 强制
                with io.open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Config] 加载失败，使用默认: {e}")
        return copy.deepcopy(DEFAULT_CONFIG)

    def _migrate(self):
        """旧值兼容 + 缺字段补齐。"""
        cfg = self.config
        # refresh_interval: 旧版 <= 300 表示秒
        ri = cfg.get("refresh_interval")
        if isinstance(ri, (int, float)) and 0 < ri <= 300:
            cfg["refresh_interval"] = int(ri * 1000)
        # window 字段
        wc = cfg.setdefault("window", {})
        wc.setdefault("x", 100)
        wc.setdefault("y", 100)
        wc.setdefault("opacity", DEFAULT_OPACITY)
        wc.setdefault("topmost", True)
        wc.setdefault("font_size", DEFAULT_FONT_SIZE)
        wc.setdefault("font_family", FONT_FAMILY_DEFAULT)
        wc.setdefault("theme", DEFAULT_THEME)
        wc.setdefault("hotkey", DEFAULT_HOTKEY)
        # colors
        cfg.setdefault("colors", {})

    def save_config(self):
        try:
            tmp = self.config_file + ".tmp"
            # 用 io.open + encoding='utf-8' 支持中文路径和中文内容
            with io.open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            # 跨平台替换（Windows 支持 os.replace 原子替换）
            os.replace(tmp, self.config_file)
        except Exception as e:
            print(f"[Config] 保存失败: {e}")

    # -- 读取 API --
    def get_stocks(self):
        return self.config.get("stocks", [])

    def get_refresh_interval(self) -> int:
        return int(self.config.get("refresh_interval", DEFAULT_REFRESH_INTERVAL))

    def get_window_config(self) -> dict:
        return self.config.get("window", {})

    def get_color_overrides(self, theme: str) -> dict:
        return self.config.get("colors", {}).get(theme, {})

    def effective_color(self, theme: str, key: str) -> str:
        """取用户覆盖色，没有就回落到主题默认。"""
        override = self.get_color_overrides(theme).get(key)
        if override:
            return override
        return DEFAULT_COLORS.get(theme, DEFAULT_COLORS[DEFAULT_THEME])[key]

    # -- 写 API --
    def add_stock(self, code, alias=None) -> bool:
        code = code.strip()
        stocks = self.get_stocks()
        for s in stocks:
            if s["code"] == code:
                if alias:
                    s["alias"] = alias
                    self.save_config()
                return False
        stocks.append({"code": code, "alias": alias or code})
        self.save_config()
        return True

    def remove_stock(self, code):
        self.config["stocks"] = [s for s in self.get_stocks() if s["code"] != code]
        self.save_config()

    def set_alias(self, code, alias):
        for s in self.get_stocks():
            if s["code"] == code:
                s["alias"] = alias
                self.save_config()
                return True
        return False

    def move_stock(self, code, delta):
        stocks = self.get_stocks()
        for i, s in enumerate(stocks):
            if s["code"] == code:
                j = i + delta
                if 0 <= j < len(stocks):
                    stocks[i], stocks[j] = stocks[j], stocks[i]
                    self.save_config()
                    return True
        return False

    def update_window(self, **kwargs):
        wc = self.get_window_config()
        for k, v in kwargs.items():
            if v is not None:
                wc[k] = v
        self.save_config()

    def set_refresh_interval(self, ms: int):
        self.config["refresh_interval"] = int(ms)
        self.save_config()

    def set_color(self, theme: str, key: str, value: str):
        colors = self.config.setdefault("colors", {})
        theme_colors = colors.setdefault(theme, {})
        theme_colors[key] = value
        self.save_config()

    def reset_colors(self, theme: str):
        if "colors" in self.config and theme in self.config["colors"]:
            del self.config["colors"][theme]
            self.save_config()


# =========================================================================
# 主题
# =========================================================================
class Theme:
    """运行时主题对象：从 DEFAULT_COLORS + 用户覆盖合并而来。"""

    def __init__(self, name: str, overrides: Optional[dict] = None):
        self.name = name
        base = DEFAULT_COLORS.get(name, DEFAULT_COLORS[DEFAULT_THEME])
        merged = dict(base)
        if overrides:
            merged.update(overrides)
        # 全部转 QColor 缓存
        self._colors = {k: QColor(v) for k, v in merged.items()}
        # bg_rgb 用于 paintEvent
        bg = self._colors["bg"]
        self.bg_rgb = (bg.red(), bg.green(), bg.blue())

    def __getitem__(self, k):
        return self._colors[k].name()  # '#rrggbb'

    def get_qcolor(self, k) -> QColor:
        return self._colors[k]

    def as_dict(self) -> dict:
        return {k: v.name() for k, v in self._colors.items()}


# =========================================================================
# 快捷键捕获按钮
# =========================================================================
class HotkeyCaptureButton(QPushButton):
    """点一下进入"按任意组合键"模式，按 Esc 取消。"""

    hotkey_changed = pyqtSignal(str)  # pynput 格式

    _SPECIAL_KEYS = {
        Qt.Key_Space: 'space', Qt.Key_Tab: 'tab',
        Qt.Key_Backspace: 'backspace', Qt.Key_Delete: 'delete',
        Qt.Key_Return: 'enter', Qt.Key_Enter: 'enter', Qt.Key_Escape: 'esc',
        Qt.Key_Home: 'home', Qt.Key_End: 'end',
        Qt.Key_PageUp: 'page_up', Qt.Key_PageDown: 'page_down',
        Qt.Key_Up: 'up', Qt.Key_Down: 'down', Qt.Key_Left: 'left', Qt.Key_Right: 'right',
        Qt.Key_Insert: 'insert', Qt.Key_Pause: 'pause', Qt.Key_Print: 'print_screen',
        Qt.Key_CapsLock: 'caps_lock', Qt.Key_NumLock: 'num_lock', Qt.Key_ScrollLock: 'scroll_lock',
        Qt.Key_Minus: '-', Qt.Key_Equal: '=',
        Qt.Key_BracketLeft: '[', Qt.Key_BracketRight: ']',
        Qt.Key_Semicolon: ';', Qt.Key_Apostrophe: "'",
        Qt.Key_Comma: ',', Qt.Key_Period: '.', Qt.Key_Slash: '/',
        Qt.Key_Backslash: '\\', Qt.Key_QuoteLeft: '`',
        Qt.Key_Plus: '+', Qt.Key_Asterisk: '*',
    }
    _MOD_DISPLAY = {'<ctrl>': 'Ctrl', '<alt>': 'Alt',
                    '<shift>': 'Shift', '<cmd>': 'Win'}
    _MOD_ORDER = ['<ctrl>', '<alt>', '<shift>', '<cmd>']

    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self._current = current or ""
        self._capturing = False
        self.setCheckable(True)
        self.setMinimumWidth(180)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setText(self._format_display(self._current))
        self.setToolTip("点击后按下新的快捷键组合（必须含 Ctrl/Alt/Shift/Win 之一）\n按 Esc 取消")
        self.clicked.connect(self._on_clicked)

    def _format_display(self, pynput_str: str) -> str:
        """把 pynput 格式 '<ctrl>+<alt>+h' 显示为 'Ctrl+Alt+H'"""
        if not pynput_str:
            return f"{ICON_COG} 点击设置快捷键"
        parts = pynput_str.lower().split('+')
        mods, key = [], None
        for p in parts:
            p = p.strip()
            if p in self._MOD_DISPLAY:
                mods.append(p)
            else:
                key = p
        seen, ordered = set(), []
        for m in self._MOD_ORDER:
            if m in mods and m not in seen:
                ordered.append(m)
                seen.add(m)
        out = [self._MOD_DISPLAY[m] for m in ordered]
        if key:
            # 单字符 (a-z, 0-9) → 大写；功能键 f1-f24 → 大写；
            # 单词型 (space, tab, esc, page_up 等) → 首字母大写
            if len(key) == 1 or re.match(r'^f\d+$', key):
                out.append(key.upper())
            else:
                out.append(key.replace('_', ' ').title().replace(' ', ''))
        return "+".join(out) if out else f"{ICON_COG} 点击设置快捷键"

    def _on_clicked(self, checked: bool):
        if checked:
            self._start_capture()
        else:
            self._cancel_capture()

    def _start_capture(self):
        self._capturing = True
        self.setText(f"  {ICON_DOT} 按下新快捷键 (Esc 取消)  {ICON_DOT}")
        self.setStyleSheet(
            "QPushButton { background: #fff3cd; color: #333;"
            " border: 1px solid #ffc107; padding: 4px; border-radius: 4px; }"
        )
        self.grabKeyboard()  # 抢焦点，确保 keyPressEvent 一定被触发

    def _cancel_capture(self):
        self._capturing = False
        self.releaseKeyboard()
        self.setChecked(False)
        self.setStyleSheet("")
        self.setText(self._format_display(self._current))

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)
        if event.key() == Qt.Key_Escape:
            self._cancel_capture()
            event.accept()
            return
        if event.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
            event.accept()
            return
        mods = []
        if event.modifiers() & Qt.ControlModifier: mods.append('<ctrl>')
        if event.modifiers() & Qt.AltModifier: mods.append('<alt>')
        if event.modifiers() & Qt.ShiftModifier: mods.append('<shift>')
        if event.modifiers() & Qt.MetaModifier: mods.append('<cmd>')
        key_name = self._qt_to_pynput(event.key(), event.text())
        if not key_name:
            event.accept()
            return
        if not mods:
            self.setText("需要至少一个修饰键 (Ctrl/Alt/Shift/Win)")
            event.accept()
            return
        mods.append(key_name)
        new = '+'.join(mods)
        self._current = new
        self._capturing = False
        self.releaseKeyboard()
        self.setChecked(False)
        self.setStyleSheet("")
        self.setText(self._format_display(new))
        self.hotkey_changed.emit(new)
        event.accept()

    def _qt_to_pynput(self, key, text):
        if key in self._SPECIAL_KEYS:
            return self._SPECIAL_KEYS[key]
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            return f"f{key - Qt.Key_F1 + 1}"
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(ord('a') + key - Qt.Key_A)
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(ord('0') + key - Qt.Key_0)
        if text and text.isprintable():
            return text.lower()
        return None


# =========================================================================
# 颜色选择按钮
# =========================================================================
class ColorPickerButton(QPushButton):
    """点击弹 QColorDialog。"""

    color_changed = pyqtSignal(str)  # "#rrggbb"

    def __init__(self, color: str = "#ffffff", label: str = "", parent=None):
        super().__init__(parent)
        self._color = color
        self._label = label
        self.setMinimumWidth(70)
        self.setMaximumWidth(110)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self):
        # 左侧色块 + 右侧文字
        pix = QPixmap(18, 18)
        pix.fill(QColor(self._color))
        painter = QPainter(pix)
        painter.setPen(QPen(QColor(0, 0, 0, 80), 1))
        painter.drawRect(0, 0, 17, 17)
        painter.end()
        self.setIcon(QIcon(pix))
        text = self._color.upper() if not self._label else f"{self._label} {self._color.upper()}"
        self.setText(text)
        self.setIconSize(QSize(18, 18))

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.parent(),
                                   f"选择 {self._label or '颜色'}")
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.color_changed.emit(self._color)

    def setColor(self, color: str):
        self._color = color
        self._refresh()


# =========================================================================
# 配置弹窗
# =========================================================================
class ConfigDialog(QDialog):
    """分组 + 标签页 + 实时保存。"""

    def __init__(self, parent, config: StockConfig):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(f"{ICON_COG}  盯盘助手 — 设置")
        self.setMinimumSize(640, 580)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )
        self._building = True
        self._init_ui()
        self._building = False
        self._apply_qss()

    # ---- 样式 ----
    def _apply_qss(self):
        """让 QSS 比 Qt 默认好看一档"""
        self.setStyleSheet("""
            QDialog { background: #1e1e24; color: #d8d8e0; }
            QLabel { color: #c8c8d0; background: transparent; }
            QGroupBox {
                border: 1px solid #33333a; border-radius: 6px;
                margin-top: 14px; padding: 12px 10px 8px 10px;
                color: #e0e0e8; font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px;
                padding: 0 6px; color: #8a8a92; }
            QTabWidget::pane {
                border: 1px solid #33333a; border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: #2a2a32; color: #a0a0a8;
                padding: 8px 18px; border: 1px solid #33333a;
                border-bottom: none; border-top-left-radius: 6px;
                border-top-right-radius: 6px; margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e24; color: #ffffff;
                border-bottom: 1px solid #1e1e24;
            }
            QListWidget {
                background: #15151a; border: 1px solid #33333a;
                border-radius: 4px; color: #d8d8e0;
                padding: 4px;
            }
            QListWidget::item { padding: 4px 6px; }
            QListWidget::item:selected {
                background: #3a3a4a; color: #ffffff;
            }
            QPushButton {
                background: #2a2a32; color: #d8d8e0;
                border: 1px solid #3a3a42; border-radius: 4px;
                padding: 6px 14px; min-width: 60px;
            }
            QPushButton:hover { background: #3a3a44; color: #ffffff; }
            QPushButton:pressed { background: #40404a; }
            QPushButton:disabled { color: #555; background: #25252a; }
            QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QFontComboBox {
                background: #15151a; color: #e0e0e8;
                border: 1px solid #33333a; border-radius: 4px;
                padding: 4px 6px; min-height: 22px;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #2a2a32; color: #d8d8e0;
                border: 1px solid #3a3a42; selection-background-color: #3a3a4a;
            }
            QCheckBox { color: #d8d8d0; padding: 4px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #3a3a42; border-radius: 3px;
                background: #15151a;
            }
            QCheckBox::indicator:checked {
                background: #4a8cff; border: 1px solid #4a8cff;
            }
            QSlider::groove:horizontal {
                height: 6px; background: #2a2a32;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a8cff, stop:1 #6aa8ff);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px; height: 16px; margin: -5px 0;
                background: #ffffff; border: 1px solid #4a8cff;
                border-radius: 8px;
            }
        """)

    # ---- 布局 ----
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_stock_tab(),   f"  {ICON_DOT} 股票列表  ")
        tabs.addTab(self._build_display_tab(), f"  {ICON_EYE} 显示  ")
        tabs.addTab(self._build_color_tab(),   f"  {ICON_COG} 颜色  ")
        tabs.addTab(self._build_hotkey_tab(),  f"  {ICON_DOT} 快捷键  ")
        layout.addWidget(tabs)

        # 底部按钮
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    # ---- 标签页 1：股票列表 ----
    def _build_stock_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(8)

        gb = QGroupBox("自选股")
        gb_lay = QVBoxLayout(gb)
        self.listbox = QListWidget()
        self._refresh_list()
        gb_lay.addWidget(self.listbox)

        btn_row = QHBoxLayout()
        for text, handler in [
            (f"{ICON_PLUS} 添加", self._add),
            ("修改别名", self._edit_alias),
            ("删除", self._remove),
            ("▲ 上移", self._up),
            ("▼ 下移", self._down),
        ]:
            b = QPushButton(text)
            b.clicked.connect(handler)
            btn_row.addWidget(b)
        btn_row.addStretch()
        gb_lay.addLayout(btn_row)
        lay.addWidget(gb)
        lay.addStretch()
        return w

    # ---- 标签页 2：显示 ----
    def _build_display_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(8)
        wc = self.config.get_window_config()

        # 字体
        gb_font = QGroupBox("字体")
        form_f = QFormLayout(gb_font)
        form_f.setLabelAlignment(Qt.AlignRight)
        form_f.setHorizontalSpacing(12)
        form_f.setVerticalSpacing(8)

        font_row = QHBoxLayout()
        self.font_family_combo = QFontComboBox()
        self.font_family_combo.setCurrentFont(QFont(wc.get("font_family", FONT_FAMILY_DEFAULT)))
        self.font_family_combo.currentFontChanged.connect(self._on_font_family_changed)
        font_row.addWidget(self.font_family_combo, 2)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 48)
        self.font_size_spin.setValue(int(wc.get("font_size", DEFAULT_FONT_SIZE)))
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        font_row.addWidget(self.font_size_spin, 1)
        form_f.addRow("字体 / 字号:", font_row)
        lay.addWidget(gb_font)

        # 主题
        gb_theme = QGroupBox("主题")
        form_t = QFormLayout(gb_theme)
        form_t.setLabelAlignment(Qt.AlignRight)
        form_t.setHorizontalSpacing(12)
        form_t.setVerticalSpacing(8)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(DEFAULT_COLORS.keys()))
        self.theme_combo.setCurrentText(wc.get("theme", DEFAULT_THEME))
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        form_t.addRow("主题:", self.theme_combo)
        lay.addWidget(gb_theme)

        # 窗口
        gb_win = QGroupBox("窗口")
        form_w = QFormLayout(gb_win)
        form_w.setLabelAlignment(Qt.AlignRight)
        form_w.setHorizontalSpacing(12)
        form_w.setVerticalSpacing(8)

        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(500, 600000)
        self.refresh_spin.setSingleStep(500)
        self.refresh_spin.setSuffix(" ms")
        self.refresh_spin.setValue(self.config.get_refresh_interval())
        self.refresh_spin.valueChanged.connect(self._on_refresh_changed)
        form_w.addRow("刷新间隔:", self.refresh_spin)

        self.topmost_check = QCheckBox("窗口始终置顶")
        self.topmost_check.setChecked(wc.get("topmost", True))
        self.topmost_check.stateChanged.connect(self._on_topmost_changed)
        form_w.addRow("置顶:", self.topmost_check)
        lay.addWidget(gb_win)

        # 透明度
        gb_op = QGroupBox("背景透明度")
        v = QVBoxLayout(gb_op)
        row = QHBoxLayout()
        row.setSpacing(6)
        lft = QLabel("完全透明")
        lft.setStyleSheet("color: #7a7a82;")
        row.addWidget(lft)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setSingleStep(1)
        self.opacity_slider.setPageStep(5)
        self.opacity_slider.setTickPosition(QSlider.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.setValue(int(wc.get("opacity", DEFAULT_OPACITY) * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        row.addWidget(self.opacity_slider, 1)
        rgt = QLabel("完全不透明")
        rgt.setStyleSheet("color: #7a7a82;")
        row.addWidget(rgt)
        v.addLayout(row)
        self.opacity_value_label = QLabel()
        self.opacity_value_label.setAlignment(Qt.AlignCenter)
        self.opacity_value_label.setStyleSheet("color: #7a7a82;")
        v.addWidget(self.opacity_value_label)
        self._update_opacity_label(self.opacity_slider.value())
        lay.addWidget(gb_op)

        lay.addStretch()
        return w

    # ---- 标签页 3：颜色 ----
    def _build_color_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(8)

        note = QLabel(
            f"{ICON_DOT}  修改后立即生效，并在关闭弹窗时写入 monitor_config.json"
        )
        note.setStyleSheet("color: #7a7a82; padding: 0 4px;")
        lay.addWidget(note)

        theme = self.config.get_window_config().get("theme", DEFAULT_THEME)
        gb = QGroupBox(f"颜色设置  ·  当前主题: {theme}")
        gb_lay = QGridLayout(gb)
        gb_lay.setHorizontalSpacing(12)
        gb_lay.setVerticalSpacing(8)

        labels = [
            ("text",   "主文字"),
            ("price",  "价格"),
            ("header", "表头"),
            ("time",   "时间戳"),
            ("sep",    "分隔线"),
            ("up",     "上涨色"),
            ("down",   "下跌色"),
            ("bg",     "背景色"),
            ("border", "边框色"),
        ]
        self._color_buttons = {}
        for i, (key, label) in enumerate(labels):
            r, c = i // 3, (i % 3) * 2
            l = QLabel(f"{label}:")
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            gb_lay.addWidget(l, r, c)
            current = self.config.effective_color(theme, key)
            btn = ColorPickerButton(current, "", self)
            btn.color_changed.connect(lambda col, k=key: self._on_color_changed(k, col))
            self._color_buttons[key] = btn
            gb_lay.addWidget(btn, r, c + 1)

        lay.addWidget(gb)

        # 重置按钮
        reset_row = QHBoxLayout()
        reset_btn = QPushButton("重置当前主题为默认色")
        reset_btn.clicked.connect(self._on_reset_colors)
        reset_row.addStretch()
        reset_row.addWidget(reset_btn)
        lay.addLayout(reset_row)

        lay.addStretch()
        return w

    # ---- 标签页 4：快捷键 ----
    def _build_hotkey_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setSpacing(8)

        gb = QGroupBox("全局快捷键（显示/隐藏窗口）")
        form = QFormLayout(gb)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        wc = self.config.get_window_config()
        self.hotkey_btn = HotkeyCaptureButton(wc.get("hotkey", DEFAULT_HOTKEY))
        self.hotkey_btn.hotkey_changed.connect(self._on_hotkey_changed)
        form.addRow("主快捷键:", self.hotkey_btn)

        info = QLabel(
            f"{ICON_DOT}  必须包含至少一个修饰键（Ctrl/Alt/Shift/Win 之一）\n"
            f"{ICON_DOT}  按 Esc 取消\n"
            f"{ICON_DOT}  应用级别备份键：Shift+Alt+E（窗口有焦点时）\n"
            f"{ICON_DOT}  应用级别备份键：Esc（隐藏到托盘）"
        )
        info.setStyleSheet("color: #7a7a82; padding: 6px 0;")
        form.addRow("", info)
        lay.addWidget(gb)
        lay.addStretch()
        return w

    # ---- 列表操作 ----
    def _refresh_list(self):
        self.listbox.clear()
        for s in self.config.get_stocks():
            self.listbox.addItem(f"{s['code']}    —    {s.get('alias', s['code'])}")

    def _add(self):
        code, ok = QInputDialog.getText(self, f"{ICON_PLUS} 添加股票", "6 位代码:")
        if not ok or not code.strip():
            return
        alias, ok2 = QInputDialog.getText(self, f"{ICON_PLUS} 添加股票", "别名 (可留空):")
        self.config.add_stock(code.strip(), alias.strip() if ok2 and alias.strip() else None)
        self._refresh_list()

    def _edit_alias(self):
        row = self.listbox.currentRow()
        if row < 0: return
        stocks = self.config.get_stocks()
        if row >= len(stocks): return
        s = stocks[row]
        alias, ok = QInputDialog.getText(
            self, "修改别名", f"{s['code']} 的别名:", text=s.get("alias", "")
        )
        if ok and alias:
            self.config.set_alias(s["code"], alias)
            self._refresh_list()

    def _remove(self):
        row = self.listbox.currentRow()
        if row < 0: return
        stocks = self.config.get_stocks()
        if row >= len(stocks): return
        s = stocks[row]
        if QMessageBox.question(self, "确认", f"删除 {s['code']}?") == QMessageBox.Yes:
            self.config.remove_stock(s["code"])
            self._refresh_list()

    def _up(self):
        row = self.listbox.currentRow()
        if row <= 0: return
        self.config.move_stock(self.config.get_stocks()[row]["code"], -1)
        self._refresh_list()
        self.listbox.setCurrentRow(row - 1)

    def _down(self):
        row = self.listbox.currentRow()
        stocks = self.config.get_stocks()
        if row < 0 or row >= len(stocks) - 1: return
        self.config.move_stock(stocks[row]["code"], +1)
        self._refresh_list()
        self.listbox.setCurrentRow(row + 1)

    # ---- 实时回调 ----
    def _on_refresh_changed(self, v):
        if self._building: return
        self.config.set_refresh_interval(v)
        if self.parent() and hasattr(self.parent(), "_restart_timer"):
            self.parent()._restart_timer()

    def _on_font_size_changed(self, v):
        if self._building: return
        self.config.update_window(font_size=v)
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_font_family_changed(self, font):
        if self._building: return
        self.config.update_window(font_family=font.family())
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_theme_changed(self, name):
        if self._building: return
        if name not in DEFAULT_COLORS: return
        self.config.update_window(theme=name)
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_topmost_changed(self, _):
        if self._building: return
        self.config.update_window(topmost=self.topmost_check.isChecked())
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_opacity_changed(self, v):
        if self._building: return
        self._update_opacity_label(v)
        self.config.update_window(opacity=v / 100.0)
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _update_opacity_label(self, v):
        self.opacity_value_label.setText(f"  {v}%  ")

    def _on_color_changed(self, key, color):
        if self._building: return
        theme = self.config.get_window_config().get("theme", DEFAULT_THEME)
        self.config.set_color(theme, key, color)
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_reset_colors(self):
        if self._building: return
        theme = self.config.get_window_config().get("theme", DEFAULT_THEME)
        self.config.reset_colors(theme)
        # 刷新颜色按钮
        for k, btn in self._color_buttons.items():
            btn.setColor(self.config.effective_color(theme, k))
        if self.parent() and hasattr(self.parent(), "apply_config"):
            self.parent().apply_config()

    def _on_hotkey_changed(self, hotkey_str):
        if self._building: return
        self.config.update_window(hotkey=hotkey_str)
        if self.parent() and hasattr(self.parent(), "_register_hotkey"):
            self.parent()._register_hotkey(hotkey_str)


# =========================================================================
# 主窗口
# =========================================================================
class StockDesktopApp(QWidget):

    sig_update = pyqtSignal(str, float, float, str, str)  # code, price, pct, color, arrow
    sig_update_time = pyqtSignal(str, bool)  # ts, ok
    sig_update_invalid = pyqtSignal(str)
    sig_toggle = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.config = StockConfig()
        wc = self.config.get_window_config()

        self.theme_name = wc.get("theme", DEFAULT_THEME)
        self._rebuild_theme()
        self.opacity_val = float(wc.get("opacity", DEFAULT_OPACITY))
        self.font_size = int(wc.get("font_size", DEFAULT_FONT_SIZE))
        self.font_family = wc.get("font_family", FONT_FAMILY_DEFAULT)

        self._drag_start: Optional[QPoint] = None
        self.stock_labels = {}
        self.fetcher = get_stock_fetcher()
        self.refresh_timer = None
        self.is_hidden = False
        self._ghk = None

        # 关键透明设置
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # 信号
        self.sig_update.connect(self._on_update_label)
        self.sig_update_time.connect(self._on_update_time)
        self.sig_update_invalid.connect(self._on_update_invalid)
        self.sig_toggle.connect(self._toggle_visibility)

        self._init_window()
        self._init_ui()
        self._init_tray()
        self._init_hotkey()
        self._init_internal_shortcut()
        self._start_refresh()

    def _rebuild_theme(self):
        self.theme = Theme(self.theme_name, self.config.get_color_overrides(self.theme_name))

    def _init_window(self):
        # 顶级无边框窗口：Qt.Window | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus
        # - Qt.Window 明确顶级窗口身份（虽然 QWidget 默认就是 Window，但显式更稳）
        # - FramelessWindowHint 无标题栏
        # - WindowStaysOnTopHint 始终置顶
        # - WindowDoesNotAcceptFocus 不抢焦点、不在任务栏、但鼠标事件正常（不像 Tool 会丢 move）
        flags = (Qt.Window
                 | Qt.FramelessWindowHint
                 | Qt.WindowStaysOnTopHint
                 | Qt.WindowDoesNotAcceptFocus)
        if self.config.get_window_config().get("topmost", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        wc = self.config.get_window_config()
        self.move(int(wc.get("x", 100)), int(wc.get("y", 100)))

    def paintEvent(self, event):
        """手动绘制半透明背景。
        注意：文字 QLabel 自身用 setStyleSheet 设定颜色与 background:transparent，
        不受 paintEvent 影响 → 文字始终不透明。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r, g, b = self.theme.bg_rgb
        alpha = int(max(0.0, min(1.0, self.opacity_val)) * 255)
        bg_color = QColor(r, g, b, alpha)
        painter.fillRect(event.rect(), bg_color)
        painter.end()

    def _make_font(self, size_delta: int = 0, bold: bool = False) -> QFont:
        f = QFont(self.font_family, max(self.font_size + size_delta, 6))
        f.setBold(bold)
        return f

    def _btn_style(self, key, close=False) -> str:
        hover = "btn_close_hover" if close else "btn_hover"
        return (
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {self.theme[key]}; }}"
            f"QPushButton:hover {{ color: {self.theme[hover]}; }}"
        )

    def _init_ui(self):
        """原版布局：标题栏一行（左：表头 / 右：⚙ ✕），下面股票行。"""
        old = self.layout()
        if old:
            while old.count():
                it = old.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
            old.deleteLater()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        # ===== 标题行：左表头 + 右按钮（加大可拖动区域）=====
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setContentsMargins(0, 4, 0, 4)  # 上下各 4px padding

        # 左：表头（淡灰色）
        self.header_label = QLabel("名称        最新价     涨跌幅")
        self.header_label.setFont(self._make_font(-2))
        self.header_label.setStyleSheet(
            f"color: {self.theme['header']}; background: transparent;"
            f" padding: 4px 0; margin: 0;"
        )
        title_row.addWidget(self.header_label, 1)
        title_row.addStretch(1)

        # 右：⚙ ✕（按钮高度加大到 24px，更容易点中）
        self.config_btn = QPushButton(ICON_COG)
        self.config_btn.setFont(self._make_font(0))
        self.config_btn.setFixedSize(22, 24)
        self.config_btn.setCursor(Qt.PointingHandCursor)
        self.config_btn.setToolTip("设置")
        self.config_btn.setStyleSheet(self._btn_style("btn"))
        self.config_btn.clicked.connect(self._show_config)
        title_row.addWidget(self.config_btn)

        self.close_btn = QPushButton(ICON_CLOSE)
        self.close_btn.setFont(self._make_font(0, True))
        self.close_btn.setFixedSize(22, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("隐藏到托盘 (Esc)")
        self.close_btn.setStyleSheet(self._btn_style("btn", close=True))
        self.close_btn.clicked.connect(self._hide_to_tray)
        title_row.addWidget(self.close_btn)

        layout.addLayout(title_row)

        # ===== 行情表（股票行）=====
        self.stock_container = QFrame()
        self.stock_container.setStyleSheet("background: transparent;")
        self.stock_layout = QGridLayout(self.stock_container)
        self.stock_layout.setContentsMargins(0, 0, 0, 0)
        self.stock_layout.setHorizontalSpacing(8)
        self.stock_layout.setVerticalSpacing(0)
        layout.addWidget(self.stock_container)
        self._init_stock_labels()

        # ===== 底部时间戳 =====
        self.time_label = QLabel("")
        self.time_label.setFont(self._make_font(-3))
        self.time_label.setStyleSheet(
            f"color: {self.theme['time']}; background: transparent;"
        )
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.time_label)

    def _init_stock_labels(self):
        """只画股票数据行；表头在 _init_ui 的标题行里。"""
        font = self._make_font(0)

        # 分隔线（表头与数据的视觉分隔）
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {self.theme['sep']}; border: none;")
        self.stock_layout.addWidget(sep, 0, 0, 1, 3)

        # 列宽自适应
        self.stock_layout.setColumnStretch(0, 3)
        self.stock_layout.setColumnStretch(1, 2)
        self.stock_layout.setColumnStretch(2, 2)

        # 数据行
        for row, s in enumerate(self.config.get_stocks()):
            code = s["code"]
            alias = s.get("alias", code)
            grid_row = row + 1

            nl = QLabel(alias)
            nl.setFont(font)
            nl.setStyleSheet(
                f"color: {self.theme['text']}; background: transparent;"
                f" padding: 0; margin: 0;"
            )
            nl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.stock_layout.addWidget(nl, grid_row, 0)

            pl = QLabel("--")
            pl.setFont(font)
            pl.setStyleSheet(
                f"color: {self.theme['price']}; background: transparent;"
                f" padding: 0; margin: 0;"
            )
            pl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.stock_layout.addWidget(pl, grid_row, 1)

            cl = QLabel("--")
            cl.setFont(font)
            cl.setStyleSheet(
                f"color: {self.theme['text']}; background: transparent;"
                f" padding: 0; margin: 0;"
            )
            cl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.stock_layout.addWidget(cl, grid_row, 2)

            self.stock_labels[code] = {"name": nl, "price": pl, "change": cl}

    # ---- 应用配置（不重建 UI，仅样式刷新） ----
    def apply_config(self):
        wc = self.config.get_window_config()
        new_theme = wc.get("theme", DEFAULT_THEME)
        # 即便主题名没变，覆盖色可能变了
        self.theme_name = new_theme
        self._rebuild_theme()
        self.opacity_val = float(wc.get("opacity", DEFAULT_OPACITY))
        self.font_size = int(wc.get("font_size", DEFAULT_FONT_SIZE))
        self.font_family = wc.get("font_family", FONT_FAMILY_DEFAULT)

        # 置顶变更
        flags = (Qt.Window
                 | Qt.FramelessWindowHint
                 | Qt.WindowStaysOnTopHint
                 | Qt.WindowDoesNotAcceptFocus)
        if wc.get("topmost", True):
            flags |= Qt.WindowStaysOnTopHint
        if int(self.windowFlags()) != int(flags):
            self.setWindowFlags(flags)
            self.show()

        self.update()
        self._restyle_all()
        self._rebuild_stock_rows()
        self._refresh_stocks()

    def _restyle_all(self):
        try:
            self.config_btn.setStyleSheet(self._btn_style("btn"))
            self.close_btn.setStyleSheet(self._btn_style("btn", close=True))
        except Exception:
            pass
        try:
            self.header_label.setFont(self._make_font(-2))
            self.header_label.setStyleSheet(
                f"color: {self.theme['header']}; background: transparent;"
            )
        except Exception:
            pass
        try:
            self.time_label.setFont(self._make_font(-3))
            self.time_label.setStyleSheet(
                f"color: {self.theme['time']}; background: transparent;"
            )
        except Exception:
            pass

    def _rebuild_stock_rows(self):
        while self.stock_layout.count():
            it = self.stock_layout.takeAt(0)
            w = it.widget()
            if w: w.setParent(None); w.deleteLater()
        self.stock_labels.clear()
        self._init_stock_labels()

    # ---- 刷新 ----
    def _start_refresh(self):
        self._restart_timer()

    def _restart_timer(self):
        if self.refresh_timer:
            try:
                self.refresh_timer.stop(); self.refresh_timer.deleteLater()
            except Exception:
                pass
        interval = self.config.get_refresh_interval()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_stocks)
        self.refresh_timer.start(interval)
        self._refresh_stocks()

    def _refresh_stocks(self):
        stocks = self.config.get_stocks()
        if not stocks:
            return
        codes = [s["code"] for s in stocks]

        def fetch():
            ok = False
            try:
                info_list = self.fetcher.get_stocks_info(codes)
                ok = any(i.get("valid") for i in info_list)
                for info in info_list:
                    code = info["code"]
                    if code in self.stock_labels and info.get("valid"):
                        price = info["price"]
                        change_pct = info["change_pct"]
                        if change_pct > 0:
                            color = self.theme["up"]
                            arrow = f"{ICON_UP} "
                        elif change_pct < 0:
                            color = self.theme["down"]
                            arrow = f"{ICON_DOWN} "
                        else:
                            color = self.theme["neutral"]
                            arrow = ""
                        self.sig_update.emit(code, price, change_pct, color, arrow)
                    elif code in self.stock_labels and not info.get("valid"):
                        self.sig_update_invalid.emit(code)
            except Exception as e:
                print(f"[Refresh] 失败: {e}")
            now = datetime.now().strftime("%H:%M:%S")
            self.sig_update_time.emit(now, ok)

        threading.Thread(target=fetch, daemon=True).start()

    # Signals: 5 个参数 — code, price, change_pct, color, arrow
    def _on_update_label(self, code, price, change_pct, color, arrow):
        if code in self.stock_labels:
            labels = self.stock_labels[code]
            labels["price"].setText(f"{price:.2f}")
            labels["price"].setStyleSheet(
                f"color: {color}; background: transparent; padding: 0; margin: 0;"
            )
            sign = "+" if change_pct > 0 else ""
            labels["change"].setText(f"{arrow}{sign}{change_pct:.2f}%")
            labels["change"].setStyleSheet(
                f"color: {color}; background: transparent; padding: 0; margin: 0;"
            )

    def _on_update_invalid(self, code):
        if code in self.stock_labels:
            self.stock_labels[code]["price"].setText("--")

    def _on_update_time(self, ts, ok):
        # ok 保留参数（信号约定），但简单起见不切换状态点
        prefix = "" if ok else f"{ICON_DOT} "
        self.time_label.setText(f"更新: {prefix}{ts}")

    # ---- 拖动 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_start is not None:
            self.move(event.globalPos() - self._drag_start)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = None
            self.config.update_window(x=self.pos().x(), y=self.pos().y())
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("设置", self._show_config)
        menu.addAction("立即刷新", self._refresh_stocks)
        menu.addSeparator()
        menu.addAction("隐藏到托盘", self._hide_to_tray)
        menu.addSeparator()
        menu.addAction("退出", self._quit)
        menu.exec_(event.globalPos())

    def _show_config(self):
        dlg = ConfigDialog(self, self.config)
        dlg.exec_()
        self.apply_config()

    # ---- 托盘 ----
    def _init_tray(self):
        if not _HAS_TRAY:
            return
        try:
            pix = self._build_tray_icon()
            self.tray_icon = _QSystemTrayIcon(QIcon(pix), self)
            self.tray_icon.setToolTip("盯盘助手")
            menu = QMenu()
            menu.addAction("显示/隐藏", self._toggle_visibility)
            menu.addAction("设置", self._show_config)
            menu.addAction("刷新", self._refresh_stocks)
            menu.addSeparator()
            menu.addAction("退出", self._quit)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
        except Exception as e:
            print(f"[Tray] 初始化失败: {e}")

    def _build_tray_icon(self) -> QPixmap:
        """Build a bullish (rising) candlestick tray icon.
        - Dark rounded background
        - Bullish trend line going up
        - Red endpoint dot (up-color, A-share convention)
        """
        size = 64
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        # Round dark background
        p.setBrush(QColor(20, 20, 24))
        p.setPen(QPen(QColor(80, 80, 90), 2))
        p.drawEllipse(4, 4, size - 8, size - 8)
        # Bullish trend line
        pen = QPen(QColor("#ff5252"), 4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        from PyQt5.QtCore import QPoint
        path_points = [
            QPoint(14, 48),  # bottom-left (low)
            QPoint(26, 36),  # rise
            QPoint(36, 40),  # small dip
            QPoint(50, 16),  # final high
        ]
        path = QPainterPath()
        path.moveTo(path_points[0])
        for pt in path_points[1:]:
            path.lineTo(pt)
        p.drawPath(path)
        # Endpoint highlight (red = up)
        p.setBrush(QColor("#ff5252"))
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.drawEllipse(path_points[-1].x() - 5, path_points[-1].y() - 5, 10, 10)
        p.end()
        return pix

    def _on_tray_activated(self, reason):
        if reason == _QSystemTrayIcon.DoubleClick:
            self._toggle_visibility()

    def _hide_to_tray(self):
        self.hide()
        self.is_hidden = True

    def _show_from_tray(self):
        self.show()
        self.is_hidden = False

    def _toggle_visibility(self):
        if self.is_hidden:
            self._show_from_tray()
        else:
            self._hide_to_tray()

    # ---- 快捷键 ----
    def _init_hotkey(self):
        hk = self.config.get_window_config().get("hotkey", DEFAULT_HOTKEY)
        self._register_hotkey(hk)

    def _register_hotkey(self, hotkey_str):
        """注册（或热重载）pynput 全局快捷键。
        跨 pynput 版本兼容：
        - 优先 GlobalHotKeys（所有版本都支持）
        - 失败时回退到 add_hotkey（仅新版 pynput）
        - 都不行就靠 Qt 窗口级快捷键
        """
        # 停掉旧的
        if self._ghk is not None:
            try:
                self._ghk.stop()
            except Exception:
                pass
            self._ghk = None

        if not HAS_PYNPUT:
            print("[Hotkey] pynput 不可用，仅依赖 Qt 窗口级快捷键")
            return

        if not hotkey_str or not isinstance(hotkey_str, str):
            print("[Hotkey] 快捷键为空，仅依赖 Qt 窗口级快捷键")
            return

        # 优先方案: GlobalHotKeys (跨版本稳定)
        try:
            from pynput import keyboard as _kb
            if hasattr(_kb, 'GlobalHotKeys'):
                self._ghk = _kb.GlobalHotKeys({
                    hotkey_str: lambda: self.sig_toggle.emit()
                })
                self._ghk.daemon = True
                self._ghk.start()
                print(f"[Hotkey] GlobalHotKeys 注册成功: {hotkey_str}")
                return
        except Exception as e:
            print(f"[Hotkey] GlobalHotKeys 注册失败: {e}")

        # 备选: add_hotkey (仅新版 pynput 1.7+)
        try:
            from pynput import keyboard as _kb
            if hasattr(_kb, 'add_hotkey'):
                _kb.add_hotkey(hotkey_str, lambda: self.sig_toggle.emit())
                print(f"[Hotkey] add_hotkey 注册成功: {hotkey_str}")
                return
        except Exception as e:
            print(f"[Hotkey] add_hotkey 注册失败: {e}")

        print("[Hotkey] 所有 pynput 方案失败，仅依赖 Qt 窗口级快捷键")

    def _init_internal_shortcut(self):
        """Qt 窗口级快捷键：窗口获得焦点时一定可用（不受 pynput 状态影响）。"""
        # 1) Shift+Alt+E — 备用切换键（窗口有焦点时）
        sc1 = QShortcut(QKeySequence("Shift+Alt+E"), self)
        sc1.setContext(Qt.ApplicationShortcut)
        sc1.activated.connect(self._toggle_visibility)

        # 2) Esc = 隐藏到托盘
        sc2 = QShortcut(QKeySequence("Escape"), self)
        sc2.setContext(Qt.ApplicationShortcut)
        sc2.activated.connect(self._hide_to_tray)

    # ---- 退出 ----
    def _quit(self):
        try:
            if self.refresh_timer:
                self.refresh_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, '_ghk', None) is not None:
                self._ghk.stop()
                self._ghk = None
        except Exception:
            pass
        try:
            if hasattr(self, 'tray_icon'):
                self.tray_icon.hide()
        except Exception:
            pass
        QApplication.quit()


# =========================================================================
# 入口
# =========================================================================
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("盯盘助手")
    app.setOrganizationName("stock-desktop")
    win = StockDesktopApp()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
