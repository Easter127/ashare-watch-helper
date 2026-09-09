# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-XX-XX

### 🎉 Initial Release

#### 新增 / Added
- 实时 A 股行情显示（新浪 + 腾讯双数据源，自动重试）
- 完全透明背景（0% 不透明度，文字保持完全不透明）
- 横向滑块调节背景透明度（0% – 100%）
- 字体家族选择（`QFontComboBox`，支持所有系统字体）
- 字体大小可调（6 – 48 pt）
- 9 种主题颜色可自定义（文字、价格、表头、时间、分隔线、涨色、跌色、背景、边框）
- 实时颜色选择（`QColorDialog` + 色块预览）
- 全局快捷键自定义（默认 `Alt+E`，可在设置中改）
- 快捷键捕获控件（点击按钮 → 按下任意组合键即生效）
- 系统托盘 + 双击恢复
- 配置文件实时落盘（无需手动"保存"按钮）
- 原子写入配置（`.tmp` + `os.replace`，防止写崩溃损坏）
- 在线/离线状态指示
- 涨跌幅前缀箭头（▲ / ▼）
- 拖动窗口到任意位置（自动保存坐标）
- 双主题（dark / light），每个主题的颜色都可被用户覆盖
- 右键菜单（设置 / 立即刷新 / 隐藏 / 退出）
- **完整支持中文路径**（项目目录 / exe 所在目录 / config 文件名）
- **PyInstaller 单文件 exe 打包**（带自定义图标）
- **配置文件自动存放在 exe 同级目录**
- **顶级窗口（Qt.Window）** + 加大可拖动标题栏

#### 技术 / Technical
- PyQt5 5.15+
- Python 3.8+
- 模块化设计：UI / 主题 / 配置 / 热键 分层清晰
- 跨 pynput 版本兼容（`GlobalHotKeys` 主路径 + `add_hotkey` 备选 + Qt 窗口级兜底）
- GitHub Actions CI（3 OS × 3 Python 矩阵）

[1.0.0]: https://github.com/yourname/ashare-watch-helper/releases/tag/v1.0.0
