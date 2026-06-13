# Signal Governance Final Development Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 UZI-Skill 的强门禁思想与当前 `Signal Governance Layer` 架构草案合并，形成开发前的最终执行方案。

**Architecture:** 保留现有 Dashboard、PipelineTask、RAG 和卡片系统作为主线，在「现有分析结果 -> Dashboard/RAG/Telegram/HTML」之间新增一套专业化信号治理层。治理层采用 UZI-Skill 式硬门禁：独立 `data_gaps`、显式 `acknowledged_gaps`、证据来源检查、persona/role config、多空辩论、critical Publish Gate 阻断；HTML 报告只能从通过 Publish Gate 的 `SignalPackage` 生成。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy/SQLite、JSON artifact repository、Jinja2 卡片系统、Chroma、OpenAI-compatible LLM (`LLM_BASE_URL + LLM_API_KEY + CHAT_MODEL`)、pytest、现有 `PipelineTask` 单线程执行器。

---

## 0. Architecture Reference Summary

本计划是 `docs/plans/2026-06-12-signal-governance-architecture-plan.md` 的开发执行版，不替代原草案的产品背景和架构论证。后续开发以本文件为任务书，以原架构草案为上位设计依据。

### 0.1 Document Roles

| Document | Role | How To Use |
|---|---|---|
| `2026-06-12-signal-governance-architecture-plan.md` | 设计背景与产品架构说明 | 用于理解为什么要做治理层、四大模块的产品意义、风险取舍和长期方向 |
| `2026-06-12-signal-governance-final-development-plan.md` | 开发执行任务书 | 用于确定开发顺序、文件边界、测试策略、提交节奏和硬性 gate 规则 |

### 0.2 Inheritance Map

| Architecture Draft Section | Final Plan Coverage |
|---|---|
| 1. 背景与判断 | Header goal/architecture + Section 0 + Section 2 |
| 2. 总体目标架构 | Section 3 Target Governance Pipeline |
| 3. 目标数据模型 | Section 5 Domain Models |
| 4. 信号质量门禁 | Phase 1 DataGap Registry + Phase 2 Quality Gate |
| 5. 多角色观点蒸馏 | Section 6 Role Config And Debate Design + Phase 4 + Phase 5 |
| 6. 风险提示模块 | Phase 3 Risk Scan + Phase 10 push policy |
| 7. 报告发布前自查 | Phase 6 Publish Gate And SignalPackage |
| 8. 统一 SignalPackage | Section 5 final package model + Phase 6 |
| 9. API 与前端设计 | Phase 8 Dashboard Cards + existing card rules in Section 8 |
| 10. RAG 与智能问答对接 | Phase 10 RAG And Telegram Integration |
| 11. 实施阶段规划 | Section 7 Implementation Phases |
| 12. 测试策略 | Section 9 Global Verification Commands + per-phase tests |
| 13. 迁移与兼容策略 | Section 2 existing system constraints + Section 10 checklist |
| 14. 风险与取舍 | Section 8 Development Rules + phased execution order |
| 15. 推荐优先级 | Section 7 phase order |
| 16. 评审问题清单 | Section 1 Final Decisions |
| 17. 执行 handoff | Section 11 Execution Handoff |

### 0.3 Decisions That Override The Draft

The draft remains valid unless this final plan says otherwise. These decisions override earlier open questions:

1. `data_gaps` must be independent artifacts, not only fields inside `QualityAssessment`.
2. `acknowledged_gaps` are required for unresolved but accepted missing data.
3. Publish Gate `critical` findings are hard blockers.
4. `SignalPackage` cannot be generated without evidence checks.
5. Panel review must use `role_group -> persona -> reviewer` config.
6. Bull/Bear/Rebuttal debate is required before final publish review.
7. HTML reports can only be rendered from non-blocked `SignalPackage` artifacts.
8. Dashboard remains the daily operating surface; HTML is a gated snapshot output.

### 0.4 Content Kept In The Draft Only

The following content is intentionally not duplicated in full here to avoid two divergent sources of truth:

- Long-form explanation of why not to build a lightweight version.
- Full UZI-Skill reference discussion.
- Product-level rationale for each governance module.
- Extended risk/choice discussion.
- Original review question wording.

When implementation needs exact execution steps, use this final plan. When a product/design question arises, read the architecture draft first, then apply the override decisions in Section 0.3 and Section 1.

## 1. Final Decisions

本文件是 `docs/plans/2026-06-12-signal-governance-architecture-plan.md` 的开发前最终版。原方案中第 16 节的 7 个问题已经形成结论，后续开发按本节执行。

| Decision | Final Answer | Implementation Meaning |
|---|---|---|
| 高风险信号是否阻断 Telegram 强推送 | 默认阻断 | `high_risk` 或 Publish Gate `block` 不进入强推送，只能进入风险卡片或归档 |
| 缺行情/缺数据如何处理 | 用独立 `data_gaps` + `acknowledged_gaps` 管理 | 缺口不能埋在 `QualityAssessment` 文本里；补不齐必须显式承认 |
| 多角色评审如何建模 | `role_group -> persona -> reviewer` | 不做平铺角色名；每个角色有配置、评分标准、证据约束和输出 schema |
| 运行产物放哪里 | `data/governance/`，加入 `.gitignore` | 借鉴 UZI `.cache/{ticker}` 分阶段产物，但适配本项目数据目录 |
| Dashboard 与 HTML 谁为主 | Dashboard 为日常工作台，HTML 为通过 gate 后的快照 | Dashboard 可交互处理缺口；HTML 只从通过 gate 的 `SignalPackage` 生成 |
| ChatEngine 是否强制证据 | 投资判断类回答必须带证据、风险、数据缺口 | 普通检索问题可简化，投资建议/风险判断必须走治理上下文 |
| 模型配置方式 | 当前 `.env`，未来设置页加密存储 | 后续配置页只显示已配置状态，不回显完整 API Key |

## 2. What We Already Have

现有系统已经有工程门禁意识，不能推倒重来：

- `src/cards/base.py` / `src/cards/__init__.py`：卡片注册、渲染路径约束、`template` 与 `_render_html()` 互斥。
- `src/cards/card_schema.py`：dataclass schema 校验，字段缺失不应静默失败。
- `src/interfaces/web_api.py`：卡片 API 信封 `{html, data, error}`、ChatEngine 懒加载、`top_k` 边界处理。
- `src/templates/base.html`：统一 `apiFetch()`、toast 错误可见、AI HTML 片段清理、聊天状态与竞态保护。
- `src/pipeline/task_executor.py`：单线程执行锁、任务状态机、skip/retry、错误可见。
- `src/cards/cards_config.py`：Dashboard 信息架构已经按「今日信号 / 投资决策 / 深度研究 / 数据管理 / 通知与设置」产品化。

缺口在于：这些都是工程门禁，还没有形成 UZI-Skill 那种跨阶段投研发布门禁。

## 3. Target Governance Pipeline

最终治理链路固定为：

```text
existing analysis/consensus/price data
-> SignalCandidate
-> DataGap registry
-> Quality Gate
-> Panel Review with role config
-> Bull/Bear/Rebuttal debate
-> Risk Scan
-> Publish Gate
-> SignalPackage
-> Dashboard / RAG / Telegram / HTML report
```

硬规则：

1. `SignalCandidate` 没有 evidence，不允许生成 `SignalPackage`。
2. `data_gaps` 独立落盘，不只存在于 quality 结果内部。
3. required gap 未补齐且未 acknowledged，不允许进入 Publish Gate。
4. Publish Gate 存在 `critical` issue，必须返回 `block`。
5. HTML report 只能读取 `packages/{date}/{signal_id}.json`，不能直接从 tweet、analysis 或 LLM 临时回答生成。
6. Telegram 强推只能消费 `SignalPackage.publish_status in {"pass", "warn"}` 且 `risk.level != "high_risk"` 的信号。
7. ChatEngine 涉及投资判断时，优先检索 `SignalPackage` / `RiskAssessment` / `PanelReview`，再补原始 tweet。

## 4. Data Artifacts

新增目录，全部属于运行产物，不提交 Git：

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

`data/governance/` 必须加入 `.gitignore`。

## 5. Domain Models

Create `src/governance/models.py`.

Core types:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Severity = Literal["info", "warning", "critical"]
GateStatus = Literal["pass", "warn", "block", "failed"]
RiskLevel = Literal["safe", "notice", "caution", "high_risk", "unknown"]
PanelStance = Literal["bullish", "bearish", "neutral", "avoid", "insufficient_data"]
GapStatus = Literal["open", "resolved", "acknowledged"]


@dataclass(frozen=True)
class EvidenceRef:
    source_type: Literal["tweet", "price", "analysis", "consensus", "risk", "panel", "manual"]
    source_id: str
    url: str | None = None
    title: str | None = None
    excerpt: str | None = None
    timestamp: str | None = None
    reliability: float | None = None


@dataclass(frozen=True)
class DataGap:
    code: str
    message: str
    severity: Severity
    required_for_publish: bool
    suggested_fix: str | None = None
    evidence_needed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcknowledgedGap:
    code: str
    reason: str
    acknowledged_by: str
    acknowledged_at: str
    expires_at: str | None = None


@dataclass
class SignalCandidate:
    signal_id: str
    ticker: str
    asset_name: str | None
    generated_at: datetime
    source_tweet_ids: list[str]
    source_usernames: list[str]
    stance: str | None
    signal_score: float | None
    confidence: str | None
    evidence: list[EvidenceRef]
    raw_payload: dict = field(default_factory=dict)
```

Final package:

```python
@dataclass
class SignalPackage:
    signal_id: str
    ticker: str
    generated_at: datetime
    publish_status: GateStatus
    summary: str
    candidate: SignalCandidate
    quality: dict
    data_gaps: list[DataGap]
    acknowledged_gaps: list[AcknowledgedGap]
    panel: dict
    debate: dict
    risk: dict
    publish_review: dict
    evidence: list[EvidenceRef]
    html_report_path: str | None = None
```

## 6. Role Config And Debate Design

Create config directory:

```text
config/governance/
  roles.yaml
  risk_rules.yaml
  quality_rules.yaml
  publish_rules.yaml
```

`roles.yaml` structure:

```yaml
version: "2026-06-12"
role_groups:
  value_quality:
    label: "价值质量派"
    objective: "检查商业质量、估值纪律、安全边际和长期可持续性"
    personas:
      - id: "buffett_style"
        label: "巴菲特式质量视角"
        stance_bias: "quality_first"
        required_evidence: ["business_quality", "valuation", "cash_flow"]
        scoring_rubric:
          valuation: 0.25
          moat: 0.30
          management: 0.15
          downside: 0.30
  growth_tech:
    label: "成长科技派"
    objective: "检查 TAM、技术平台、产品周期和增长持续性"
    personas: []
  macro_liquidity:
    label: "宏观流动性派"
    objective: "检查利率、美元、周期、风险偏好和系统性压力"
    personas: []
  trend_momentum:
    label: "趋势动量派"
    objective: "检查趋势、突破、拥挤度、回撤和交易纪律"
    personas: []
  hot_money_sentiment:
    label: "游资情绪派"
    objective: "检查题材、情绪、资金接力和短线一致预期"
    personas: []
  risk_control:
    label: "风控反方派"
    objective: "主动寻找证据缺口、估值泡沫、叙事过热和反向风险"
    personas: []
  source_forensics:
    label: "信源审查派"
    objective: "检查观点来源、传播路径、历史可靠性和异常推广痕迹"
    personas: []
  ai_chokepoint:
    label: "AI瓶颈猎手"
    objective: "检查 AI 产业链卡位、供给瓶颈、不可替代性和周期风险"
    personas: []
```

Debate output:

```json
{
  "signal_id": "...",
  "bull": {"thesis": "...", "evidence": ["tweet:..."], "confidence": 0.72},
  "bear": {"thesis": "...", "evidence": ["price:..."], "confidence": 0.66},
  "rebuttal": {"winner": "bear", "why": "...", "remaining_uncertainties": []},
  "final_stance": "neutral",
  "must_disclose_risks": []
}
```

## 7. Implementation Phases

### Phase 0: Governance Baseline And Fixtures

**Files:**
- Create: `tests/fixtures/governance/signal_candidate_valid.json`
- Create: `tests/fixtures/governance/signal_candidate_missing_price.json`
- Create: `tests/fixtures/governance/signal_candidate_no_evidence.json`
- Create: `tests/test_governance_models.py`
- Modify: `.gitignore`

**Step 1: Write failing tests**

Tests must assert:

- `data/governance/` is ignored by Git.
- A valid fixture can be loaded into `SignalCandidate`.
- A no-evidence candidate is invalid for package generation.

**Step 2: Implement minimal model loader**

Create `src/governance/models.py` and `src/governance/repository.py` with JSON load/save helpers.

**Step 3: Run tests**

Run:

```bash
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m pytest tests/test_governance_models.py tests/test_ia_refactor.py
```

Expected: all pass.

**Step 4: Commit**

```bash
git add .gitignore src/governance tests/fixtures/governance tests/test_governance_models.py
git commit -m "Add governance baseline models and fixtures"
```

### Phase 1: DataGap Registry

**Files:**
- Create: `src/governance/data_gaps.py`
- Create: `tests/test_governance_data_gaps.py`
- Modify: `src/governance/repository.py`

**Step 1: Write failing tests**

Tests must cover:

- `DataGap` artifacts are written to `data/governance/data_gaps/YYYY-MM-DD/{signal_id}.json`.
- `AcknowledgedGap` artifacts are written separately.
- Required open gaps block publish readiness.
- Required acknowledged gaps allow publish readiness but remain visible.

**Step 2: Implement gap registry**

Functions:

```python
collect_data_gaps(candidate: SignalCandidate) -> list[DataGap]
acknowledge_gap(signal_id: str, gap_code: str, reason: str, acknowledged_by: str) -> AcknowledgedGap
has_blocking_gaps(gaps: list[DataGap], acknowledged: list[AcknowledgedGap]) -> bool
```

**Step 3: Run tests and commit**

### Phase 2: Quality Gate

**Files:**
- Create: `src/governance/quality_gate.py`
- Create: `tests/test_governance_quality_gate.py`

**Step 1: Write failing tests**

Quality Gate must:

- block when evidence is empty.
- warn when price context is missing for normal Dashboard display.
- block when price context is missing for strong push / explicit buy-sell conclusion.
- emit machine-readable checks.
- include references to independent `data_gaps` artifact path.

**Step 2: Implement rules**

Keep rules deterministic first. Do not call LLM in this phase.

**Step 3: Run tests and commit**

### Phase 3: Risk Scan

**Files:**
- Create: `src/governance/risk_scan.py`
- Create: `config/governance/risk_rules.yaml`
- Create: `tests/test_governance_risk_scan.py`

**Step 1: Write failing tests**

Risk Scan must:

- detect user text triggers such as `群里老师`, `必涨`, `内幕`, `翻倍`.
- detect concentration / promotion-like language from candidate text.
- produce `high_risk` at threshold.
- prevent strong Telegram push for `high_risk`.

**Step 2: Implement deterministic weighted rules**

No LLM required initially. Keep weights configurable.

**Step 3: Run tests and commit**

### Phase 4: Role Config And Panel Review

**Files:**
- Create: `config/governance/roles.yaml`
- Create: `src/governance/roles.py`
- Create: `src/governance/panel_review.py`
- Create: `tests/test_governance_roles.py`
- Create: `tests/test_governance_panel_review.py`

**Step 1: Write failing tests**

Tests must assert:

- role config loads `role_groups` and personas.
- every role group has `objective` and `required_evidence` or group-level equivalent.
- panel review output includes group id, persona id, stance, score, evidence refs, missing evidence.
- reviewer cannot cite evidence that is not present in candidate/package evidence.

**Step 2: Implement config loader**

Use YAML parser already in requirements (`pyyaml`).

**Step 3: Implement rule-first panel skeleton**

Initial implementation may use deterministic scoring with optional LLM summary later. The architecture must expose LLM hook, but tests should not depend on network calls.

**Step 4: Run tests and commit**

### Phase 5: Bull/Bear/Rebuttal Debate

**Files:**
- Create: `src/governance/debate.py`
- Create: `tests/test_governance_debate.py`

**Step 1: Write failing tests**

Debate must:

- generate `bull`, `bear`, and `rebuttal` sections.
- force both sides to cite evidence.
- carry unresolved uncertainties into Publish Gate.
- produce `final_stance` without overriding critical risk.

**Step 2: Implement deterministic debate composer**

Use `PanelReview` stances and conflicts first; LLM can summarize later.

**Step 3: Run tests and commit**

### Phase 6: Publish Gate And SignalPackage

**Files:**
- Create: `src/governance/publish_gate.py`
- Create: `src/governance/package_builder.py`
- Create: `tests/test_governance_publish_gate.py`
- Create: `tests/test_governance_package_builder.py`

**Step 1: Write failing tests**

Publish Gate must block when:

- candidate has no evidence.
- required gaps are open.
- risk is `high_risk` for strong push.
- quality status is `block`.
- debate has unresolved critical uncertainty.
- panel tries to cite nonexistent evidence.

Package Builder must:

- produce `SignalPackage` only after Publish Gate `pass` or `warn`.
- include `data_gaps` and `acknowledged_gaps`.
- include all evidence refs.
- write package artifact to `data/governance/packages/YYYY-MM-DD/{signal_id}.json`.

**Step 2: Implement gate**

`critical` is hard block. This is not advisory.

**Step 3: Run tests and commit**

### Phase 7: PipelineTask Integration

**Files:**
- Modify: `src/pipeline/task_executor.py`
- Modify: `src/storage/models.py`
- Create: `tests/test_governance_pipeline_tasks.py`

**Step 1: Write failing tests**

New task types:

- `governance_candidate`
- `governance_quality`
- `governance_risk`
- `governance_panel`
- `governance_debate`
- `governance_publish`
- `governance_report`

Tests must assert unknown tasks still fail visibly and governance tasks write `PipelineTask.result` with artifact paths.

**Step 2: Implement task dispatch**

Do not parallelize. Reuse existing single-thread execution model.

**Step 3: Run tests and commit**

### Phase 8: Dashboard Cards

**Files:**
- Modify: `src/cards/cards_config.py`
- Create: `src/cards/governance_cards.py`
- Create: `src/templates/cards/quality_gate.html`
- Create: `src/templates/cards/risk_alerts.html`
- Create: `src/templates/cards/panel_review.html`
- Create: `src/templates/cards/publish_review.html`
- Modify: `src/cards/__init__.py`
- Create: `tests/test_governance_cards.py`

**Step 1: Write failing tests**

Cards must follow existing rules:

- API returns `{html, data, error}`.
- no Python-generated `onclick`.
- DOM ids use card name prefix.
- empty/loading/error states exist.
- governance cards read package/gate artifacts, not raw LLM temporary output.

**Step 2: Implement cards**

Add under `signals` and `decisions` tabs carefully:

- `quality_gate`: 今日信号，near system status.
- `risk_alerts`: 今日信号，near anomaly.
- `panel_review`: 投资决策 or 深度研究.
- `publish_review`: 数据管理 or 投资决策.

**Step 3: Run tests and commit**

### Phase 9: HTML Report Generator

**Files:**
- Create: `src/governance/report_generator.py`
- Create: `src/templates/reports/signal_package.html`
- Create: `tests/test_governance_report_generator.py`

**Step 1: Write failing tests**

Report generator must:

- refuse to render if no `SignalPackage` exists.
- refuse to render if package `publish_status == "block"`.
- include evidence, data gaps, acknowledged gaps, risk, debate and publish review.
- write report to `data/governance/reports/YYYY-MM-DD/{signal_id}.html`.

**Step 2: Implement HTML report**

This is an artifact/snapshot, not the main UI.

**Step 3: Run tests and commit**

### Phase 10: RAG And Telegram Integration

**Files:**
- Modify: `src/ai/chat_engine.py`
- Modify: Telegram-related module found during implementation
- Create: `tests/test_governance_chat_engine.py`
- Create: `tests/test_governance_push_policy.py`

**Step 1: Write failing tests**

ChatEngine must:

- route risk-oriented questions to risk/package context.
- include evidence/risk/data gaps for investment judgment.
- not answer buy/sell style questions from raw tweets only when package exists.

Telegram policy must:

- block `high_risk` strong push.
- block Publish Gate `block`.
- allow `warn` only with visible warning label.

**Step 2: Implement integration**

Keep `LLM_BASE_URL + LLM_API_KEY + CHAT_MODEL` config.

**Step 3: Run tests and commit**

## 8. Development Rules

1. TDD for every phase: write failing tests first.
2. No network or live LLM dependency in unit tests.
3. Governance artifacts are runtime data and must not be committed.
4. Do not bypass existing card API envelope.
5. Do not write front-end business gate logic in templates.
6. Do not generate HTML reports directly from raw analysis; only from `SignalPackage`.
7. Critical gate failures must be machine-readable, not just natural-language warnings.
8. Keep commits phase-sized.

## 9. Global Verification Commands

Run after each phase:

```bash
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m pytest tests/test_ia_refactor.py
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m pytest tests/test_governance_*.py
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m compileall src
```

Run before final merge/push:

```bash
git status --short
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m pytest tests/test_ia_refactor.py tests/test_governance_*.py
"C:/Users/lwj93/.workbuddy/binaries/python/envs/default/Scripts/python.exe" -m compileall src
git diff --check
```

## 10. Pre-Development Checklist

Before implementation starts, confirm:

- `docs/plans/2026-06-12-signal-governance-architecture-plan.md` remains the architecture reference.
- This file is the execution plan.
- `data/governance/` is ignored.
- No OpenAI official dependency is introduced; all LLM calls use OpenAI-compatible config.
- The first implementation phase is Phase 0, not UI cards.
- HTML report work starts only after Publish Gate and SignalPackage exist.

## 11. Execution Handoff

Plan complete and saved to `docs/plans/2026-06-12-signal-governance-final-development-plan.md`.

Two execution options:

1. **Subagent-Driven (this session)** - dispatch fresh subagent per phase, review between phases, fast iteration.
2. **Parallel Session (separate)** - open a new session with executing-plans, batch execution with checkpoints.

Recommended: Subagent-driven execution, but only after the user confirms this final plan.
