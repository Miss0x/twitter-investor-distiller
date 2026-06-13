# Governance End-to-End Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Phase 0-10 已完成的 Signal Governance 骨架收口为可运行、可追溯、可阻断、可展示的端到端系统集成闭环。

**Architecture:** 本计划不是局部 bugfix 清单，而是系统集成收口计划。核心原则是：现有分析/共识/行情产物通过稳定适配器进入 `SignalCandidate`，治理链路由 `PipelineTask` 真实调度，所有阶段产物由 `GovernanceRepository` 统一读写，Dashboard / HTML / RAG / Telegram 只能消费经过 Publish Gate 的 `SignalPackage`。禁止硬编码特殊信号、临时文件路径、跳过门禁的旁路输出。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy/SQLite、JSON artifact repository、Jinja2 Cards、现有 `PipelineTask` 单线程执行器、OpenAI-compatible ChatEngine、pytest。

---

## 0. Why This Plan Exists

Phase 0-10 已经建立治理层骨架，但还没有完成系统级闭环：

- `src/pipeline/task_executor.py` 的 governance task 仍是桩实现，只返回 `ack`。
- `src/cards/governance_cards.py` 的四张治理卡片固定返回空态。
- `src/governance/report_generator.py` 报告 HTML 未转义 evidence 文本和 URL。
- `src/governance/repository.py` 读回 `data_gaps` / `acknowledged_gaps` 后没有还原 dataclass 类型。
- `src/governance/data_gaps.py` 没有检查 `AcknowledgedGap.expires_at`。
- `src/governance/push_policy.py` 对 unknown 状态默认放行，与强门禁原则冲突。
- `src/ai/chat_engine.py` 仍只检索 tweet，没有治理上下文优先级。

本计划的目标不是“再修几个点”，而是定义一个不可绕过的全局完成标准：

```text
existing analysis / consensus / price artifact
-> SignalCandidate
-> data_gaps + acknowledged_gaps
-> quality
-> panel
-> debate
-> risk
-> publish
-> SignalPackage
-> Dashboard / HTML / RAG / Telegram
```

只有这条链路在通过路径和失败路径上都可验证，才算收口完成。

---

## 1. Non-Negotiable Integration Rules

1. **Single Entry:** 治理层唯一输入是 `SignalCandidate`。现有分析/共识/行情文件必须通过适配器转换，不能让下游模块直接读散落 JSON。
2. **Single Output:** Dashboard / HTML / RAG / Telegram 的投资判断输出只能消费 `SignalPackage` 或其关联治理 artifacts。
3. **No Bypass:** `publish_status in {"block", "failed"}` 的 package 不能生成 HTML 报告、不能强推 Telegram、不能作为 RAG 投资结论来源。
4. **Artifact First:** 每个阶段必须有稳定 artifact：candidate、data_gaps、acknowledged_gaps、quality、panel、debate、risk、publish、package、report。
5. **Typed Reload:** 保存后重新读取的 artifact 必须能还原为可继续参与 gate 的 typed model，不能变成半结构 dict。
6. **Fail Closed:** unknown / missing / corrupt / stale 状态默认阻断或降级展示，不能默认放行。
7. **No Hardcoding:** 禁止为测试 fixture、固定 ticker、固定 signal_id 写特殊逻辑。测试必须通过通用接口驱动。
8. **Backwards Compatible:** 不破坏现有 `filter/analyze/fetch_price/fetch_crypto/portrait/clean` 任务，不改变旧数据文件格式，只新增适配层。

---

## 2. Target Data Flow

### 2.1 Existing System Sources

现有可接入来源：

- `data/pipeline/*_analyzed.json`：分析后的推文、提及股票、立场、置信度、LLM 输出。
- `data/pipeline/*_filtered.json`：过滤后的投资相关推文。
- 价格数据文件或 price task result：作为 `EvidenceRef(source_type="price")`。
- 共识/轮动脚本输出：作为 `EvidenceRef(source_type="consensus")` 或 `raw_payload`。
- 原始 tweet ID / username：作为 `source_tweet_ids` 和 `source_usernames`。

Phase 11 不要求重写旧分析流程，只新增治理适配器：

```text
existing artifacts -> GovernanceInputAdapter -> SignalCandidate -> GovernanceRunner
```

### 2.2 Governance Artifacts

目录保持 Phase 0-10 设计：

```text
data/governance/
  candidates/YYYY-MM-DD/{signal_id}.json
  data_gaps/YYYY-MM-DD/{signal_id}.json
  acknowledged_gaps/YYYY-MM-DD/{signal_id}.json
  quality/YYYY-MM-DD/{signal_id}.json
  panel/YYYY-MM-DD/{signal_id}.json
  debate/YYYY-MM-DD/{signal_id}.json
  risk/YYYY-MM-DD/{signal_id}.json
  publish/YYYY-MM-DD/{signal_id}.json
  packages/YYYY-MM-DD/{signal_id}.json
  reports/YYYY-MM-DD/{signal_id}.html
  runs/{run_id}.json
```

新增 repository 方法必须复用统一 path builder，避免每个模块自己拼日期目录。

### 2.3 State Synchronization

`PipelineTask.status` 与 governance artifact 状态必须一致：

| PipelineTask.status | Governance Meaning | Artifact Requirement |
|---|---|---|
| `pending` | 尚未执行 | 不要求 artifact |
| `running` | 当前阶段执行中 | 可写 run log |
| `completed` | 阶段成功结束 | 必须有对应 artifact 或明确 no-op result |
| `failed` | 阶段异常 | 必须有 error_msg，不能生成后续 publishable package |
| `skipped` | 用户跳过 | 必须记录跳过原因，不能当作 pass |

任何 governance task 失败后，下游任务不能默认继续生成可发布 package。允许 Dashboard 展示 failed 状态和错误信息。

---

## 3. Task 1: Add End-to-End Contract Tests First

**Files:**
- Create: `tests/test_governance_end_to_end.py`
- Modify only if needed: `tests/fixtures/governance/*.json`

**Purpose:** 先定义全局验收标准，防止实现阶段变成局部修修补补。

**Required tests:**

1. `test_valid_signal_flows_to_publishable_package`
   - 输入：valid fixture，有 tweet / analysis / price evidence。
   - 期望：生成 `SignalPackage.publish_status in {"pass", "warn"}`。
   - 期望：package 保存后可 reload，reload 后 `data_gaps` / `acknowledged_gaps` 仍是 dataclass 实例。

2. `test_missing_evidence_blocks_all_downstream_outputs`
   - 输入：无 evidence candidate。
   - 期望：Quality Gate block。
   - 期望：Publish Gate block。
   - 期望：HTML report 返回 None。
   - 期望：strong push 返回 False。

3. `test_acknowledged_required_gap_allows_publish_until_expiry`
   - 输入：required gap + 未过期 ack。
   - 期望：`has_blocking_gaps(...) is False`。

4. `test_expired_acknowledged_gap_blocks_again`
   - 输入：required gap + 过期 ack。
   - 期望：`has_blocking_gaps(...) is True`。

5. `test_high_risk_package_never_strong_pushes`
   - 输入：risk_level=`high_risk`。
   - 期望：package 可以归档展示，但 strong push False。

6. `test_html_report_escapes_untrusted_evidence`
   - 输入：evidence excerpt 包含 `<script>alert(1)</script>`，url 包含恶意 quote。
   - 期望：HTML 中没有原始 `<script>`，href 属性被安全转义。

7. `test_pipeline_governance_task_runs_real_chain`
   - 输入：`PipelineTask(task_type="governance_run", payload={...})` 或等价调度入口。
   - 期望：不再返回“桩实现”，而是保存 package artifact。

8. `test_dashboard_cards_read_latest_package_artifacts`
   - 输入：repo 中已有 package/risk/panel/publish artifact。
   - 期望：四张治理卡片返回 `empty=False` 和真实字段。

**Run:**

```bash
pytest tests/test_governance_end_to_end.py -v
```

**Expected before implementation:** FAIL，原因应指向缺失 runner、repository reload 类型、dashboard 空态、HTML escaping、push default 等真实缺口。

---

## 4. Task 2: Create Governance Runner As The Orchestration Layer

**Files:**
- Create: `src/governance/runner.py`
- Modify: `src/governance/__init__.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** 用一个明确 orchestration layer 串起 Phase 0-10 模块，避免 Pipeline、Dashboard、Report 各自临时调用半条链。

**Public API:**

```python
@dataclass
class GovernanceRunResult:
    signal_id: str
    status: str
    package_path: str | None
    report_path: str | None
    publish_status: str
    error: str | None = None


def run_governance_for_candidate(
    candidate: SignalCandidate,
    repo: GovernanceRepository | None = None,
    push_intent: Literal["dashboard", "strong_push"] = "dashboard",
    acknowledged_gaps: list[AcknowledgedGap] | None = None,
    generate_report: bool = False,
) -> GovernanceRunResult:
    ...
```

**Required behavior:**

1. Save candidate.
2. Collect and save data gaps.
3. Load or accept acknowledged gaps.
4. Run quality gate.
5. Run panel review.
6. Run debate.
7. Run risk scan.
8. Run publish gate.
9. Build and save package.
10. Generate HTML only when package is non-blocked and `generate_report=True`.
11. Return a structured result.
12. On exception, return failed result and do not create publishable package.

**Design constraints:**

- Runner may be deterministic; it must not require LLM calls.
- Runner must not know FastAPI or card rendering.
- Runner must not read arbitrary pipeline files directly; that belongs to adapter layer.
- Runner must use repository methods, not ad hoc paths.

**Run:**

```bash
pytest tests/test_governance_end_to_end.py::test_valid_signal_flows_to_publishable_package -v
```

---

## 5. Task 3: Fix Repository Typed Serialization And Artifact Access

**Files:**
- Modify: `src/governance/repository.py`
- Test: `tests/test_governance_data_gaps.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** 保存/读取必须类型一致，否则系统一旦跨进程、跨日期、跨 Dashboard reload 就断裂。

**Required additions:**

```python
def _load_data_gaps(raw: list[dict]) -> list[DataGap]: ...
def _load_acknowledged_gaps(raw: list[dict]) -> list[AcknowledgedGap]: ...
def save_artifact(kind: str, signal_id: str, data: object, signal_date: str | None = None) -> Path: ...
def load_artifact(kind: str, signal_id: str, signal_date: str | None = None) -> dict | list: ...
def latest_package_path(self) -> Path | None: ...
def load_latest_package(self) -> SignalPackage | None: ...
def list_latest_packages(self, limit: int = 20) -> list[SignalPackage]: ...
```

**Rules:**

- `kind` must be validated against allowed directories; do not accept arbitrary path traversal.
- Dates are explicit strings or today; no hidden mutable global state.
- Corrupt JSON should raise a clear `ValueError` including path.
- `load_package()` must return `SignalPackage.data_gaps: list[DataGap]` and `acknowledged_gaps: list[AcknowledgedGap]`.

**Run:**

```bash
pytest tests/test_governance_data_gaps.py tests/test_governance_end_to_end.py::test_valid_signal_flows_to_publishable_package -v
```

---

## 6. Task 4: Tighten DataGap Acknowledgement Semantics

**Files:**
- Modify: `src/governance/data_gaps.py`
- Test: `tests/test_governance_data_gaps.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** `acknowledged_gaps` 是“有期限的显式承认”，不是永久绕过门禁。

**Required behavior:**

- `expires_at is None` means no expiry.
- If `expires_at` is earlier than current UTC time, the ack is invalid.
- Invalid date format should be treated as expired/invalid, not pass.
- `has_blocking_gaps()` should accept optional `now` for deterministic tests:

```python
def has_blocking_gaps(
    gaps: list[DataGap],
    acknowledged: list[AcknowledgedGap],
    now: datetime | None = None,
) -> bool:
    ...
```

**Run:**

```bash
pytest tests/test_governance_data_gaps.py tests/test_governance_end_to_end.py::test_expired_acknowledged_gap_blocks_again -v
```

---

## 7. Task 5: Add Existing Artifact To SignalCandidate Adapter

**Files:**
- Create: `src/governance/adapters.py`
- Test: `tests/test_governance_adapters.py`

**Purpose:** 新治理层必须有稳定入口接入现有系统，不能要求未来开发者手写 candidate dict。

**Public API:**

```python
def candidate_from_analysis_item(item: dict, source_file: str | None = None) -> SignalCandidate:
    ...


def candidate_from_payload(payload: dict, repo: GovernanceRepository | None = None) -> SignalCandidate:
    ...
```

**Mapping rules:**

- `signal_id`: 优先 payload/item 中显式字段；否则由 ticker + tweet id + analysis timestamp 生成稳定 hash。
- `ticker`: 来自 `ticker`、`symbol`、`mentioned_stocks[0]`，找不到则使用 `UNKNOWN` 并产生 raw_payload 标记。
- `source_tweet_ids`: 来自 `id`、`tweet_id`、`source_tweet_ids`。
- `source_usernames`: 来自 `username`、`author`、`source_usernames`。
- `stance`: 来自现有 analysis stance / action / sentiment。
- `signal_score`: 来自 score/confidence_score，无法解析则 None。
- `evidence`: 至少从 tweet/analysis 构造；price evidence 只在 payload 明确提供时添加，不能编造价格。
- `raw_payload`: 保留原始字段，便于追溯。

**Strict rule:** 不得臆造任何行情、收益率、价格数字。

**Run:**

```bash
pytest tests/test_governance_adapters.py -v
```

---

## 8. Task 6: Replace Pipeline Governance Stubs With Real Dispatch

**Files:**
- Modify: `src/pipeline/task_executor.py`
- Test: `tests/test_governance_pipeline_tasks.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** 让现有任务系统成为治理链路的真实入口，而不是旁路 demo。

**Task types:**

Use one primary task for full chain:

```text
governance_run
```

Keep old granular task names only if needed for compatibility:

```text
governance_candidate
governance_quality
governance_risk
governance_panel
governance_debate
governance_publish
governance_report
```

**Recommended behavior:**

- `governance_run` payload accepts:

```json
{
  "candidate": {...},
  "analysis_item": {...},
  "signal_id": "optional-existing-candidate-id",
  "generate_report": true,
  "push_intent": "dashboard"
}
```

- Dispatch order:
  1. If `candidate` present, parse it.
  2. Else if `analysis_item` present, use adapter.
  3. Else if `signal_id` present, load candidate from repo.
  4. Else fail closed with clear error.

- Result JSON must include:

```json
{
  "ok": true,
  "signal_id": "...",
  "publish_status": "pass|warn|block|failed",
  "package_path": "...",
  "report_path": "...|null",
  "message": "..."
}
```

**Failure behavior:**

- Invalid payload -> task failed, no publishable package.
- Missing artifact -> task failed, no publishable package.
- Governance block -> task completed with `publish_status="block"`, because block is a valid gate outcome, not runtime failure.

**Run:**

```bash
pytest tests/test_governance_pipeline_tasks.py tests/test_governance_end_to_end.py::test_pipeline_governance_task_runs_real_chain -v
```

---

## 9. Task 7: Wire Dashboard Cards To Real Governance Artifacts

**Files:**
- Modify: `src/cards/governance_cards.py`
- Modify if needed: `src/templates/cards/quality_gate.html`
- Modify if needed: `src/templates/cards/risk_alerts.html`
- Modify if needed: `src/templates/cards/panel_review.html`
- Modify if needed: `src/templates/cards/publish_review.html`
- Test: `tests/test_governance_cards.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** Dashboard 是日常操作台，不能只显示静态空态。

**Card data source rule:**

- Default: load latest package from `GovernanceRepository.load_latest_package()`.
- Optional query param: `signal_id` + `date` loads exact package.
- If no package exists, return empty state.
- If package exists but corrupt, return visible error data; card API envelope should expose error.

**Expected card data:**

`QualityGateCard.get_data()`:

```python
{
  "empty": False,
  "signal_id": "...",
  "ticker": "...",
  "status": package.quality["status"],
  "checks": package.quality["checks"],
  "data_gaps": [...],
  "acknowledged_gaps": [...],
}
```

`RiskAlertsCard.get_data()`:

```python
{
  "empty": False,
  "risk_level": package.risk["risk_level"],
  "total_score": package.risk.get("total_score", 0),
  "triggers": package.risk.get("triggers", []),
}
```

`PanelReviewCard.get_data()`:

```python
{
  "empty": False,
  "aggregate_stance": package.panel.get("aggregate_stance", "unknown"),
  "aggregate_score": package.panel.get("aggregate_score", 0),
  "reviews": package.panel.get("reviews", []),
  "debate": package.debate,
}
```

`PublishReviewCard.get_data()`:

```python
{
  "empty": False,
  "status": package.publish_status,
  "issues": package.publish_review.get("issues", []),
  "html_report_path": package.html_report_path,
}
```

**No frontend bypass:** Buttons for acknowledge/retry may be added later, but must go through explicit card action/API, not inline `onclick`.

**Run:**

```bash
pytest tests/test_governance_cards.py tests/test_governance_end_to_end.py::test_dashboard_cards_read_latest_package_artifacts -v
```

---

## 10. Task 8: Harden HTML Report Generation

**Files:**
- Modify: `src/governance/report_generator.py`
- Test: `tests/test_governance_report_generator.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** HTML 报告是可打开产物，必须按不可信输入处理 evidence、summary、ticker、URL。

**Required behavior:**

- Escape text fields with `html.escape(..., quote=True)`.
- Validate URL scheme: allow only `http://` and `https://`; otherwise omit link.
- `target="_blank" rel="noopener noreferrer"` for external links.
- Blocked/failed package returns None.
- Package without candidate returns None.
- Package without evidence may render only if publish_status is warn/pass and publish gate allowed it; otherwise None.

**Run:**

```bash
pytest tests/test_governance_report_generator.py tests/test_governance_end_to_end.py::test_html_report_escapes_untrusted_evidence -v
```

---

## 11. Task 9: Fail-Closed Push Policy And Telegram Contract

**Files:**
- Modify: `src/governance/push_policy.py`
- Test: `tests/test_governance_chat_engine.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** 强推送是高风险输出，默认必须 fail closed。

**Required behavior:**

```python
ALLOWED_STRONG_PUSH = {
    ("pass", "safe"),
    ("pass", "notice"),
    ("warn", "safe"),
    ("warn", "notice"),
}
```

- `block`, `failed`, empty, unknown publish status -> False。
- `high_risk`, `unknown`, empty risk level -> False。
- `caution` 默认 False，除非未来显式新增 `allow_caution=True` 参数；Phase 11 不加这个旁路。
- Return reason must be user-visible and deterministic.

**Run:**

```bash
pytest tests/test_governance_chat_engine.py tests/test_governance_end_to_end.py::test_high_risk_package_never_strong_pushes -v
```

---

## 12. Task 10: Add Governance Context Provider For RAG

**Files:**
- Create: `src/governance/context_provider.py`
- Modify: `src/ai/chat_engine.py`
- Test: `tests/test_governance_chat_engine.py`

**Purpose:** 投资判断类回答应优先引用通过门禁的治理结论，再补充原始推文，而不是继续只从 tweet RAG 生成。

**Public API:**

```python
def is_investment_judgment_question(question: str) -> bool:
    ...


def build_governance_context(
    question: str,
    repo: GovernanceRepository | None = None,
    limit: int = 5,
) -> str:
    ...
```

**Question classifier rule:**

Use deterministic keyword classification for Phase 11:

- investment judgment keywords: `买`, `卖`, `看多`, `看空`, `风险`, `机会`, `信号`, `推荐`, `仓位`, `目标价`, `止损`, `能不能投`, `是否值得`
- Do not call LLM for classification.

**Context rules:**

- Include only packages with `publish_status in {"pass", "warn"}`.
- Include risk level, data gaps, panel stance, debate final stance, evidence refs.
- Exclude blocked/failed packages from conclusion context.
- If no package exists, return explicit message: `当前没有通过发布门禁的治理信号`.

**ChatEngine integration:**

- For investment judgment questions, prepend governance context before tweet context.
- For non-investment questions, keep existing tweet retrieval behavior.
- Do not remove existing retriever.
- Tests should use fake retriever and fake repo; no real LLM call.

**Run:**

```bash
pytest tests/test_governance_chat_engine.py -v
```

---

## 13. Task 11: Add Run Log And Error Visibility

**Files:**
- Modify: `src/governance/runner.py`
- Modify: `src/governance/repository.py`
- Test: `tests/test_governance_end_to_end.py`

**Purpose:** UZI-Skill 强在阶段产物和可复盘。Phase 11 必须记录每次治理运行的状态，不只保存最终 package。

**Run log shape:**

```json
{
  "run_id": "20260612T...-SIGNALID",
  "signal_id": "...",
  "started_at": "...",
  "finished_at": "...",
  "status": "completed|blocked|failed",
  "steps": [
    {"name": "candidate", "status": "completed", "artifact": "..."},
    {"name": "data_gaps", "status": "completed", "artifact": "..."},
    {"name": "quality", "status": "completed", "artifact": "..."},
    {"name": "publish", "status": "blocked", "artifact": "..."}
  ],
  "error": null
}
```

**Rules:**

- Runtime failure: status `failed`.
- Gate block: status `blocked`, not failed.
- Completed pass/warn: status `completed`.
- Dashboard cards may later use latest run log for visible errors.

**Run:**

```bash
pytest tests/test_governance_end_to_end.py -v
```

---

## 14. Task 12: Full Regression Verification

**Files:**
- No code changes unless failures reveal integration bugs.

**Commands:**

```bash
pytest tests/test_governance_*.py tests/test_ia_refactor.py -v
python -m compileall src
```

**Expected:**

- Existing 76 tests continue passing or are intentionally updated where old stub expectations are replaced by real chain expectations.
- New end-to-end tests pass.
- `compileall src` passes.

**Do not push yet** unless the user explicitly confirms.

---

## 15. Acceptance Criteria

Phase 11 is complete only when all criteria are true:

1. `governance_run` PipelineTask executes real governance chain, not stub ack.
2. Valid signal produces saved `SignalPackage` and optional HTML report.
3. Missing evidence blocks Quality Gate, Publish Gate, HTML report, and strong push.
4. Required data gap blocks unless acknowledged and not expired.
5. Expired ack blocks again.
6. High risk never reaches strong Telegram push.
7. Dashboard governance cards read real latest package artifacts.
8. Report generator escapes untrusted evidence and validates URLs.
9. Repository save/load preserves typed models.
10. RAG investment judgment path includes governance context and excludes blocked packages.
11. Run logs make blocked/failed/completed outcomes auditable.
12. Full governance + IA regression tests pass.
13. No hardcoded ticker/signal/fixture special cases.
14. No bypass path allows blocked package into Dashboard conclusion, HTML, RAG conclusion, or Telegram strong push.

---

## 16. Risks And Boundaries

### In Scope

- Integration contract and end-to-end chain.
- Deterministic runner and adapter.
- Repository typing and artifact access.
- Dashboard card real artifact reading.
- HTML safety hardening.
- Push/RAG fail-closed policy.
- Tests for pass/block/ack/expiry/high-risk/reload/report escaping.

### Out Of Scope For Phase 11

- New LLM role prompts or model-based debate generation.
- Full UI for acknowledging gaps from Dashboard.
- Real Telegram Bot delivery implementation if not already present.
- New external data providers.
- Historical backfill of all existing signals into governance packages.
- Encrypting user LLM keys in Settings page.

These are follow-up product phases, not blockers for the integration closure.

---

## 17. Recommended Commit Sequence

1. `test: add governance end-to-end closure tests`
2. `feat: add governance runner orchestration`
3. `fix: preserve governance artifact types on reload`
4. `fix: enforce acknowledged gap expiry`
5. `feat: adapt existing analysis artifacts to candidates`
6. `feat: execute governance pipeline tasks`
7. `feat: read governance artifacts in dashboard cards`
8. `fix: harden governance HTML reports`
9. `fix: fail closed for governance push policy`
10. `feat: add governance context for investment chat`
11. `feat: persist governance run logs`
12. `test: verify governance closure regression`

---

## 18. Execution Handoff

Plan complete. Execute only after user approval.

Recommended execution mode for this plan:

1. Implement Task 1 first and confirm expected failures.
2. Implement Tasks 2-6 to close core data flow.
3. Pause for review after Pipeline real dispatch works.
4. Implement Tasks 7-11 to close output surfaces.
5. Run full regression in Task 12.
6. Request code review before push.

Do not push to GitHub until the user explicitly confirms.
