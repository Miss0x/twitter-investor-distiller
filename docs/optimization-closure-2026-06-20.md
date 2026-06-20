# 阶段优化收尾报告（2026-06-20）

## 结论

本阶段 6 个方向优化可以收尾。项目从“大文件耦合、测试覆盖不足、部分数据链路有隐性 bug”的状态，提升到“模块化、可测试、可审计、关键路径有回归保护”的状态。

## 已完成事项

### 1. 路由模块化

- `src/interfaces/web_api.py` 从约 1683 行压缩到约 275 行。
- 迁移 11 个 `APIRouter` 模块，保持原有路由集合一致。
- 提取 `src/interfaces/chat_utils.py`，消除拆分后的循环依赖。

### 2. 集成与 E2E 测试补强

- 新增 `tests/integration/test_e2e_scenarios.py`，覆盖 governance、valuation、team、reports 等路径。
- 修复认证测试硬编码账号导致重复运行失败的问题。
- 当前全量测试基线：`239 passed, 3 warnings`。

### 3. 性能路径优化

- 新增数据库热路径索引：
  - `ix_tweets_vec_pending (is_vectorized, created_at_twitter)`
  - `ix_media_downloaded (downloaded)`
  - `ix_pipeline_tasks_type_status (task_type, status)`
- 新增 `tests/test_db_indexes.py` 锁定索引存在性。
- 审查 `src/storage/cache.py`，确认 Redis/Memory 双实现、TTL、优雅降级设计已满足当前阶段目标。

### 4. API 契约修复

- 修复 `src/api/schemas.py` 中 `ValuationDcfResponse.confidence` 类型与实际返回值不一致的问题。
- 修复后 DCF 相关集成测试通过，避免 FastAPI `ResponseValidationError`。

### 5. 数据完整性加固

- 修复 `src/storage/alias_repository.py` 的 CSV 写入转义问题。
- 修复 `src/interfaces/handlers_data.py` 的 add/edit/delete/skip/unskip 链路，避免备注含逗号/引号时破坏 `stock_alias.csv`。
- 修复 `src/interfaces/routers/pipeline.py` 中 `_save_alias`、`_load_skip_set`、`_is_known_stock_ticker` 对 CSV 的 `split(",")` 误解析。
- 新增 `tests/test_stock_alias_csv_integrity.py`，覆盖卡片入口和 pipeline helper。

### 6. 全面审查与质量门禁

- 修复拆分后循环依赖、私有函数依赖、错误 `user_id`、前端提示目标错误、重复任务配置等问题。
- 验证命令均通过：
  - `python -X utf8 -m pytest tests/ --ignore=tests/load_test.py -q`
  - `python -X utf8 -m ruff check src/ tests/test_stock_alias_csv_integrity.py`
  - `python -X utf8 -m vulture src/ --min-confidence 80 --ignore-names market,signal_ticker`
  - `git --no-pager diff --check`

## 代码质量评估

- 模块边界：显著改善，路由职责更清晰。
- 回归保护：显著改善，新增测试覆盖真实 bug 类型。
- 数据安全：明显改善，CSV 读写统一使用标准库解析/序列化。
- 性能基础：当前阶段达标，后续可进入生产级压测。
- 维护成本：降低，新增功能可按 router/test 独立演进。

## 后续建议

以下事项不阻塞本阶段收尾，建议作为下一阶段专项：

1. PostgreSQL 迁移后的真实查询计划与索引压测。
2. Celery/异步任务在高并发下的吞吐验证。
3. 多进程部署时 Redis 缓存一致性验证。
4. 宽泛 `except Exception` 的结构化日志与可观测性增强。
5. CI 中固定执行 `pytest tests/ --ignore=tests/load_test.py`，避免根目录临时输出被误收集。
