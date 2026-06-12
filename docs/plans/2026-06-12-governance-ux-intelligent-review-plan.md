# Phase 12 Governance UX & Intelligent Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 暂缓 Telegram Bot，把开发重心放到 Web 治理交互和智能角色评审，让用户能在 Dashboard 里看懂、处理、复核信号问题，并让系统从规则化评审升级为有证据约束的“研究员式分析”。

**Architecture:** Phase 11 已经把治理链路接通；Phase 12 不重写链路，而是在链路上加“人能操作的工作台”和“可控的 LLM 研究员”。核心原则：所有人工操作都写成可追溯 artifact；所有 LLM 输出都必须引用已有证据，不能自由编造；规则评审永远保留为兜底。

**Tech Stack:** Python 3.13、FastAPI、Jinja2 Cards、统一 `apiFetch()`、事件委托 `data-action`、JSON governance artifacts、OpenAI-compatible LLM、pytest。

---

## 0. 这阶段到底要实现什么？

用人话说，Phase 12 要让系统从“后台有治理结果”变成“你能在网页上处理治理结果”。

现在 Phase 11 已经能做到：一个候选信号进来，系统会检查证据、风险、角色意见、发布门禁，然后生成正式的 `SignalPackage`。但对你来说，Web 界面还比较像“结果展示页”：能看到一些结果，但还不能很好地操作。

Phase 12 做完后，你应该能在 Web 上完成这些动作：

1. 看到一个信号为什么没通过。
2. 看到它缺了哪些东西，比如原始推文、价格背景、财报证据、多个来源验证。
3. 对暂时补不齐但你愿意承担的缺口，手动点“承认这个缺口”。
4. 写下为什么承认，比如“这只是观察信号，不作为正式买入依据”。
5. 设置承认有效期，比如 24 小时、3 天、7 天。
6. 到期后系统自动重新阻断，不会永久放行。
7. 看到每个研究员角色的观点，不只是一个分数。
8. 看到多头和空头的辩论理由。
9. 最终知道：这个信号是通过、警告通过，还是被阻断。

一句话：Phase 12 要把治理系统变成一个真正可用的“投研工作台”。

---

## 1. 术语翻译表

下面这些术语后面开发会继续出现，所以先用人话解释。

| 术语 | 人话解释 | 你能感受到的效果 |
|---|---|---|
| `SignalCandidate` 候选信号 | 系统觉得“可能值得研究”的一条投资线索 | 比如某博主连续提到 NVDA，系统先把它当成候选，不马上当结论 |
| `DataGap` 数据缺口 | 做判断还缺的东西 | 比如没有价格背景、没有原始推文、没有第二个来源 |
| `AcknowledgedGap` 已承认缺口 | 你知道它缺东西，但决定暂时接受这个风险 | 比如你说“我知道缺财报验证，但先作为观察信号保留 3 天” |
| `Quality Gate` 质量门禁 | 检查信号是不是太粗糙 | 证据太少、来源太弱，就不能直接通过 |
| `Risk Scan` 风险扫描 | 检查有没有危险信号 | 比如“必涨”“内幕”“马上起飞”等高风险词会触发警告 |
| `Panel Review` 角色评审 | 让不同风格的研究员看同一个信号 | 价值派、成长派、风控派可能给出不同意见 |
| `Debate` 多空辩论 | 把支持理由和反对理由摆在一起 | 你能看到“为什么看多”和“为什么要小心” |
| `Publish Gate` 发布门禁 | 最后一关，决定能不能成为正式信号 | 没过门禁的不能进正式报告、不能强推、不能作为问答结论 |
| `SignalPackage` 正式信号包 | 通过审核后形成的一份完整档案 | Dashboard、HTML、RAG 都读这份统一结果 |
| `Artifact` 产物文件 | 每一步留下的 JSON/HTML 记录 | 以后能追溯“当时为什么通过/为什么阻断” |
| `Fail-closed` 默认阻断 | 不确定时宁可拦住，不默认放行 | 系统不会因为看不懂状态就乱推给你 |
| `LLM Reviewer` 智能研究员 | 让大模型扮演某种研究风格，但必须按规则输出 | 它能写出分析理由，但不能脱离证据瞎编 |

---

## 2. 不做什么

这阶段明确不做 Telegram Bot。

原因很简单：Telegram 是“把结果推给你”的通道。如果治理交互和研究质量还没打磨好，先做 Bot 只是更快地把半成品推到你面前。

Phase 12 不做：

- 不做 Telegram Bot 新功能。
- 不做大规模真实采集任务。
- 不重写 Phase 11 的治理链路。
- 不让 LLM 自动下投资建议。
- 不做复杂权限系统。
- 不做多用户协同。

Phase 12 只聚焦两个东西：

1. Web 上能不能处理治理问题。
2. 角色评审能不能变得更像真实研究员，同时保持可控。

---

## 3. 总体数据流

用人话看，流程应该是这样：

```text
系统发现一个候选信号
-> 检查它缺什么
-> Web 页面展示缺口
-> 用户可以承认某些缺口
-> 系统重新跑门禁
-> 研究员角色给出观点
-> 多头/空头形成辩论
-> 最终决定能不能成为正式信号
-> Dashboard 展示最终状态
```

工程上对应：

```text
SignalCandidate
-> DataGap
-> AcknowledgedGap Action
-> GovernanceRunner rerun
-> LLM Panel Review
-> LLM Debate
-> Publish Gate
-> SignalPackage
-> Governance Dashboard Cards
```

关键原则：Web 页面不能自己“改结论”。Web 只能提交操作，比如“承认缺口”。真正的结论必须由 `GovernanceRunner` 重新计算。

这样可以避免一个常见问题：前端看起来改了状态，但后端真实门禁没变，最后 Dashboard、报告、问答又互相打架。

---

## 4. Task 1: Web 展示完整数据缺口

**目标人话版：** 让你在 Dashboard 上一眼看出“这个信号到底缺什么”。

**Files:**
- Modify: `src/cards/governance_cards.py`
- Modify: `src/templates/cards/quality_gate.html`
- Test: `tests/test_governance_ux.py`

**需要展示：**

每个 `DataGap` 至少显示：

- 缺口名称：比如“缺少价格背景”。
- 严重程度：低、中、高、关键。
- 是否阻断发布：是/否。
- 当前状态：未处理、已承认、已过期。
- 建议动作：补数据、承认风险、放弃信号。

**设计要求：**

- 空数据时显示“暂无治理结果，请先运行治理流水线”。
- 加载失败时显示错误和重试按钮。
- 不允许 Python 生成 `onclick`。
- 按钮使用 `data-action="acknowledge-gap"`。
- DOM ID 必须带卡片名前缀，比如 `quality_gate-gap-list`。

**测试：**

新增测试验证：

1. 有 package 时卡片返回 `empty=False`。
2. 未承认 gap 显示为 `pending`。
3. 已承认 gap 显示为 `acknowledged`。
4. 过期承认显示为 `expired`。

---

## 5. Task 2: 手动承认数据缺口

**目标人话版：** 当某个数据暂时补不齐时，你可以明确告诉系统：“我知道这里缺东西，但我愿意暂时接受这个风险。”

这不是绕过门禁，而是留下可追溯记录。

**Files:**
- Modify: `src/interfaces/web_api.py`
- Modify: `src/templates/base.html`
- Modify: `src/governance/data_gaps.py`
- Modify: `src/governance/repository.py`
- Test: `tests/test_governance_gap_actions.py`

**新增 API:**

```text
POST /api/governance/gaps/acknowledge
```

请求内容：

```json
{
  "signal_id": "NVDA-20260612-001",
  "gap_code": "missing_price_context",
  "reason": "仅作为观察信号，暂不作为正式买入依据",
  "expires_in_hours": 72
}
```

人话解释：

- `signal_id`：是哪条信号。
- `gap_code`：承认哪一个缺口。
- `reason`：你为什么愿意承认。
- `expires_in_hours`：承认多久后失效。

**后端行为：**

1. 检查 signal/package 是否存在。
2. 检查 gap 是否真的存在。
3. reason 不能为空。
4. expires_in_hours 必须在安全范围内，比如 1 到 168 小时。
5. 写入 `acknowledged_gaps` artifact。
6. 重新运行 `GovernanceRunner`。
7. 返回新的 package 状态。

**为什么要重新运行 runner：**

因为承认缺口不是直接改状态。系统必须重新检查质量、风险、发布门禁，才能决定是否放行。

---

## 6. Task 3: 撤销承认缺口

**目标人话版：** 如果你后来觉得“不应该承认这个缺口”，可以撤销，系统会重新阻断或重新审核。

**Files:**
- Modify: `src/interfaces/web_api.py`
- Modify: `src/templates/base.html`
- Modify: `src/governance/repository.py`
- Test: `tests/test_governance_gap_actions.py`

**新增 API:**

```text
POST /api/governance/gaps/revoke
```

请求内容：

```json
{
  "signal_id": "NVDA-20260612-001",
  "gap_code": "missing_price_context",
  "reason": "后续发现该缺口影响较大，撤销承认"
}
```

**后端行为：**

1. 读取当前 acknowledged gaps。
2. 把对应 gap 标记为 revoked，而不是直接删除。
3. 写入审计记录。
4. 重新运行 `GovernanceRunner`。
5. 返回新状态。

**为什么不直接删除：**

因为投资研究需要留痕。以后你回看时，要知道某个缺口曾经被承认过，又为什么被撤销。

---

## 7. Task 4: 缺口操作审计记录

**目标人话版：** 每次你承认或撤销一个缺口，系统都要留下“谁、什么时候、为什么做了这个操作”。

**Files:**
- Create: `src/governance/audit.py`
- Modify: `src/governance/repository.py`
- Test: `tests/test_governance_audit.py`

**Artifact 路径：**

```text
data/governance/audit/YYYY-MM-DD/{signal_id}.jsonl
```

**每条记录：**

```json
{
  "event_type": "gap_acknowledged",
  "signal_id": "NVDA-20260612-001",
  "gap_code": "missing_price_context",
  "actor": "local_user",
  "reason": "仅作为观察信号",
  "created_at": "2026-06-12T03:30:00+08:00"
}
```

**为什么用 jsonl：**

因为同一条信号可能有多次操作。jsonl 适合追加写入，不容易因为一次写入失败破坏整份文件。

---

## 8. Task 5: Web 前端交互

**目标人话版：** 你不用改文件、不用跑命令，只在网页上点按钮、填理由、选有效期，就能处理缺口。

**Files:**
- Modify: `src/templates/cards/quality_gate.html`
- Modify: `src/templates/base.html`
- Test: `tests/test_governance_ux.py`

**前端交互：**

每个未处理的数据缺口旁边显示用户能直接理解的操作文案。页面上不要出现 `gap`、`acknowledge`、`artifact`、`package`、`runner`、`schema` 这类工程词。

推荐页面文案：

- 按钮：“我知道这里缺数据，暂时接受这个风险”；
- 输入框标题：“为什么暂时接受？”；
- 输入框占位提示：“例如：只作为观察线索，不作为正式买入依据”；
- 有效期标题：“这个决定多久后失效？”；
- 有效期选项：“24 小时后重新检查”“3 天后重新检查”“7 天后重新检查”；
- 撤销按钮：“不再接受这个风险”；
- 状态文案：“待处理”“已暂时接受”“已过期，需要重新确认”。

工程字段和用户文案要分离：

- 后端仍可使用 `gap_code`、`reason`、`expires_in_hours`；
- 前端展示必须使用中文业务文案；
- 不能把接口字段名直接显示给用户；
- 每个风险/缺口 code 都要通过映射表转成自然语言；
- 映射缺失时显示“未知问题，请查看日志”，不要显示原始 code。

**前端规则：**

- 所有请求走 `apiFetch()`。
- 所有按钮使用 `data-action`。
- 不使用内联 `onclick`。
- 成功后刷新治理卡片。
- 失败时 toast 展示错误。
- toast 也必须使用人话，比如“保存失败，请稍后重试”，不要显示 Python 异常或字段名。

**边界情况：**

- 理由为空：显示“请简单说明为什么暂时接受这个风险”。
- 承认已过期：显示“这个决定已经过期，请重新确认”。
- 没有治理结果：显示“还没有可处理的信号，请先运行一次治理检查”。
- 后端失败：不改页面假状态，显示“操作没有保存成功”。

---

## 9. Task 6: 智能角色评审 schema

**目标人话版：** 让每个研究员角色不是只给分，而是说清楚“我为什么支持/反对/观望”。

**Files:**
- Create: `src/governance/llm_review.py`
- Modify: `src/governance/panel_review.py`
- Test: `tests/test_governance_llm_review.py`

**固定输出格式：**

```json
{
  "persona_id": "growth_investor",
  "stance": "bullish",
  "confidence": 72,
  "decision": "warn",
  "key_points": [
    "需求增长证据较强",
    "但估值安全边际不足"
  ],
  "evidence_used": ["tweet_123", "price_456"],
  "data_gaps": ["missing_earnings_context"],
  "risk_flags": ["valuation_risk"],
  "summary": "可以继续跟踪，但不适合直接作为强买入信号。"
}
```

**人话解释：**

- `stance`：这个角色偏看多、看空、还是中立。
- `confidence`：它有多确定。
- `decision`：支持通过、警告通过、还是阻断。
- `key_points`：核心理由。
- `evidence_used`：它用了哪些已有证据。
- `data_gaps`：它觉得还缺什么。
- `risk_flags`：它看到的风险。
- `summary`：一句人能看懂的总结。

**强约束：**

LLM 输出里的 `evidence_used` 必须来自已有 `EvidenceRef.source_id`。如果引用了不存在的证据，整条评审降级为 invalid，不参与最终分数。

---

## 10. Task 7: LLM 评审兜底机制

**目标人话版：** 如果大模型挂了、超时了、返回格式乱了，系统不能崩，也不能乱信它。应该自动退回规则评审。

**Files:**
- Modify: `src/governance/llm_review.py`
- Modify: `src/governance/panel_review.py`
- Test: `tests/test_governance_llm_review.py`

**规则：**

1. LLM 超时：使用 deterministic review。
2. LLM JSON 解析失败：使用 deterministic review。
3. LLM 引用不存在的证据：该角色评审标记 invalid。
4. LLM 说出 evidence 之外的新事实：标记 hallucination_risk。
5. 多数 LLM reviewer invalid：整个 panel 降级为规则评审。

**人话解释：**

大模型可以帮忙分析，但不能当裁判。裁判仍然是我们的门禁规则。

---

## 11. Task 8: 智能多空辩论

**目标人话版：** 让系统把“为什么看多”和“为什么看空”分开讲清楚，而不是强行给一个单一结论。

**Files:**
- Create: `src/governance/llm_debate.py`
- Modify: `src/governance/debate.py`
- Test: `tests/test_governance_llm_debate.py`

**输出结构：**

```json
{
  "bull": {
    "thesis": "看多理由",
    "evidence": ["tweet_123"],
    "weak_points": ["缺少财报验证"]
  },
  "bear": {
    "thesis": "看空或谨慎理由",
    "evidence": ["risk_456"],
    "weak_points": ["缺少反方来源"]
  },
  "rebuttal": {
    "winner": "none",
    "why": "支持和反对证据都不充分",
    "remaining_uncertainties": ["需要价格确认"]
  },
  "final_stance": "neutral"
}
```

**限制：**

- Bull 只能使用已有证据讲看多理由。
- Bear 只能使用已有证据讲风险。
- Rebuttal 只能基于 bull/bear 内容反驳。
- 不能引入系统没有的数据。

---

## 12. Task 9: Publish Gate 接入智能评审质量

**目标人话版：** 最终能不能通过，不只看有没有证据，也要看研究员意见是不是可靠。

**Files:**
- Modify: `src/governance/publish_gate.py`
- Test: `tests/test_governance_publish_gate.py`

**新增阻断规则：**

1. 多数 reviewer invalid：阻断。
2. 所有 reviewer 都 insufficient_data：阻断。
3. debate final_stance 是 insufficient_data：阻断。
4. LLM hallucination_risk 达到高等级：阻断。
5. bull/bear 分歧严重但证据不足：警告通过或阻断，不能正常通过。

**人话解释：**

如果研究员们自己都说不清，或者模型明显胡编，系统不能假装这个信号靠谱。

---

## 13. Task 10: Web 展示智能评审和辩论

**目标人话版：** 你能在 Dashboard 上看到每个研究员的观点，以及多空双方到底争在哪里。

**Files:**
- Modify: `src/templates/cards/panel_review.html`
- Modify: `src/templates/cards/publish_review.html`
- Modify: `src/cards/governance_cards.py`
- Test: `tests/test_governance_ux.py`

**展示内容：**

Panel Review 卡片：

- 每个角色名称；
- 立场：看多/看空/中立/数据不足；
- 置信度；
- 核心理由；
- 使用证据；
- 缺失数据；
- 风险提醒。

Debate 区域：

- 多头观点；
- 空头观点；
- 反驳结论；
- 剩余不确定性。

Publish Review 卡片：

- 最终状态；
- 阻断原因；
- 警告原因；
- 下一步建议。

---

## 14. Task 11: 成本和开关控制

**目标人话版：** 智能评审会调用大模型，要能控制成本，不能每次刷新网页都乱调用。

**Files:**
- Modify: `src/governance/runner.py`
- Modify: `src/governance/llm_review.py`
- Modify: `src/utils/env.py` or existing env loading path
- Test: `tests/test_governance_llm_review.py`

**配置项：**

```text
GOVERNANCE_LLM_REVIEW_ENABLED=true/false
GOVERNANCE_LLM_REVIEW_MODEL=...
GOVERNANCE_LLM_TIMEOUT_SECONDS=30
GOVERNANCE_LLM_MAX_REVIEWERS=8
```

**规则：**

- 默认可以先关闭智能评审，使用规则评审。
- 只有运行治理任务时调用 LLM。
- Dashboard 刷新不能触发 LLM 调用。
- LLM 输出保存成 artifact，后续页面只读 artifact。

---

## 15. Task 12: 端到端测试

**目标人话版：** 不是测单个函数，而是证明整条链真的能用。

**Files:**
- Create or Modify: `tests/test_governance_ux_end_to_end.py`
- Modify: existing governance tests if behavior changed

**必须覆盖：**

1. 未处理 required gap 会阻断。
2. Web acknowledge 后重新运行治理，状态变化。
3. expired acknowledge 会重新阻断。
4. revoke acknowledge 后重新阻断。
5. LLM reviewer 正常输出时进入 panel artifact。
6. LLM reviewer 引用不存在证据时被降级。
7. LLM 超时时规则评审兜底。
8. Dashboard 展示真实 panel/debate 内容。
9. Publish Gate 根据智能评审质量阻断坏信号。
10. 原有 Phase 11 测试全部继续通过。

**运行命令：**

```bash
C:\Users\lwj93\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pytest tests/test_governance_*.py tests/test_ia_refactor.py -v
C:\Users\lwj93\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m compileall src
```

---

## 16. 验收标准

Phase 12 完成必须满足：

- Web 能展示 data gaps 的状态。
- Web 能 acknowledge gap。
- Web 能 revoke gap acknowledge。
- acknowledge/revoke 都有审计记录。
- acknowledge 过期后会重新阻断。
- Dashboard 不会自己伪造状态，必须读取 governance artifact。
- LLM reviewer 输出必须结构化。
- LLM reviewer 必须引用已有证据。
- LLM 出错时自动退回规则评审。
- Debate 能展示多头、空头、反驳和剩余不确定性。
- Publish Gate 会参考智能评审质量。
- Dashboard 刷新不会触发 LLM 调用。
- 所有新增功能都有失败路径测试。
- 旧的 Phase 11 测试继续通过。

---

## 17. 推荐执行顺序

不要一次性把 Web 和 LLM 全写完。建议分四批：

### Batch A: Web 缺口处理

- Task 1: 展示完整 data gaps。
- Task 2: acknowledge gap。
- Task 3: revoke gap。
- Task 4: audit log。
- Task 5: Web 前端交互。

完成后你就能在网页上处理“缺什么、承认什么、何时过期”。

### Batch B: 智能角色评审

- Task 6: LLM review schema。
- Task 7: LLM 兜底机制。
- Task 11: 成本和开关控制。

完成后角色评审不再只是规则打分，而是有理由、有证据、有风险提示。

### Batch C: 智能多空辩论

- Task 8: LLM debate。
- Task 9: Publish Gate 接入评审质量。
- Task 10: Web 展示评审和辩论。

完成后你能看到“支持方怎么说、反对方怎么说、最后为什么通过或阻断”。

### Batch D: 全链路验证

- Task 12: 端到端测试。
- 跑全量 governance + IA 回归。
- 编译检查。
- 检查工作区改动。

---

## 18. 关键风险

### 风险 1：LLM 编造事实

解决：只能引用已有 evidence。引用不存在证据就降级或判 invalid。

### 风险 2：Web 状态和后端状态不一致

解决：Web 操作后必须重新运行 `GovernanceRunner`，页面只展示重新计算后的结果。

### 风险 3：成本失控

解决：Dashboard 刷新不调用 LLM；LLM 只在治理任务运行时调用；结果保存成 artifact。

### 风险 4：用户承认缺口变成永久绕过

解决：acknowledge 必须有 reason 和 expires_at；过期后自动重新阻断。

### 风险 5：复杂度失控

解决：先做单用户、本地审计、固定有效期选项，不做权限系统和多人协同。

---

## 19. 最终效果

做完 Phase 12 后，系统会更像一个“研究工作台”：

- 它不只是告诉你一个信号通过没通过；
- 它会告诉你为什么；
- 它允许你处理暂时补不齐的数据缺口；
- 它会记录你的处理理由；
- 它会让不同研究角色给出更像人的分析；
- 它会把多头和空头理由分开；
- 它会在模型乱说或证据不足时自动降级；
- 它不会因为接了 LLM 就失去纪律。

这阶段完成后，再做 Telegram Bot 才有意义。因为到那时 Bot 推送出去的不是半成品摘要，而是经过 Web 工作台和智能评审强化后的正式信号。
