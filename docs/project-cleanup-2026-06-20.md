# 项目整理记录（2026-06-20）

## 整理目标

让项目结构更清晰、简洁、可维护：保留源码、测试、配置样例、部署文档和必要业务数据；清理运行缓存、日志、截图、字节码和一次性开发脚本。

## 已执行清理

- 删除 Python 字节码与缓存目录：`__pycache__/`、`*.pyc`。
- 删除运行日志与 E2E 截图：`logs/*.log`、`logs/*.png`、`logs/e2e_shots/`。
- 删除本地工具会话状态：`playwright-cli.json`。
- 归档一次性迁移、路由拆分、QA 验证脚本到：`docs/archive/dev-scratch-2026-06-20/`。
- 修复源码 BOM 问题：`src/cards/consensus.py`、`src/interfaces/web_api.py`。

## 保留策略

- 保留 `src/`、`tests/`、`scripts/` 中仍具备产品或验证价值的文件。
- 保留 `data/` 中业务数据库、活动记录、财务数据、别名表和团队共享池。
- 保留 `docs/` 中架构、部署、迁移、优化闭环等长期文档。
- 保留 `.workbuddy/` 与 `.codebuddy/` 记忆目录，不删除项目记忆。

## 当前注意事项

- `pytest` 未在当前托管 Python 环境安装，因此无法直接运行 pytest 回归。
- 已使用 Python AST 对 `src/`、`scripts/`、`tests/` 全量语法解析验证，结果通过。
- 当前 `git status` 仍包含大量既有开发改动与新增文件，本次整理只处理缓存、日志、临时脚本和 BOM，不回滚既有业务开发成果。

## 后续建议

- 若确认 `docs/archive/dev-scratch-2026-06-20/` 中脚本不再需要，可在下一轮删除该归档目录。
- 建议补装测试依赖后运行完整测试：`python -m pytest`。
- 未来一次性脚本建议默认放入 `scripts/dev/` 或 `docs/archive/`，避免散落在主脚本目录。
