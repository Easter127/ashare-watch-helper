# 贡献指南 / Contributing

感谢你考虑为 **ashare-watch-helper** 做出贡献！🎉

Thanks for considering contributing!

---

## 🐛 报告 Bug / Report a bug

提交 issue 前请：
- 搜索是否已有相同 issue
- 用 [bug report 模板](.github/ISSUE_TEMPLATE/bug_report.md) 填写
- 附上 `monitor_config.json`（去除敏感信息）和系统信息

Before opening an issue, please:
- Search existing issues
- Use the bug report template
- Attach `monitor_config.json` (redact sensitive info) and system info

## ✨ 提出新功能 / Feature request

请用 [feature request 模板](.github/ISSUE_TEMPLATE/feature_request.md) 描述。

Use the feature request template.

## 🔧 提交 PR / Submit a PR

### 开发流程 / Development

```bash
# 1. Fork & clone
git clone https://github.com/yourname/ashare-watch-helper.git
cd ashare-watch-helper

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements-dev.txt

# 4. 创建分支
git checkout -b feat/your-feature

# 5. 修改代码
# ...

# 6. 测试
python -c "import sys; sys.path.insert(0, 'src'); from stock_desktop import *; print('OK')"

# 7. 提交 & 推送
git commit -m "feat: 增加 XX 功能"
git push origin feat/your-feature
```

### Commit 规范 / Commit convention

[Conventional Commits](https://www.conventionalcommits.org/):

| 前缀 | 含义 |
|---|---|
| `feat:` | 新功能 |
| `fix:` | 修 bug |
| `docs:` | 文档 |
| `style:` | 格式（不影响代码运行） |
| `refactor:` | 重构 |
| `test:` | 测试 |
| `chore:` | 杂项（依赖、构建等） |

### 代码风格 / Code style

- 遵循 PEP 8
- 函数 / 类加 docstring
- 关键逻辑加中文注释
- 标识符用英文

## 📦 发布流程 / Release process

（维护者）
1. 更新 `CHANGELOG.md`
2. `git tag v1.x.x`
3. `git push --tags`
4. GitHub Actions 自动构建并发布 Release

---

再次感谢！❤️
Thanks!
