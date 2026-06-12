"""
卡片元数据中心配置。
===================

所有卡片的 tab、排序、样式标记 等元数据集中在此定义。
@register 装饰器会自动读取此配置注入到卡片实例。

新增一张卡片只需：
  1. 在对应模块创建 Card 子类（name 必须唯一）
  2. 在此文件的 CARD_CONFIG 中添加一行
  3. 在 __init__.py 末尾添加 `from . import xxx` 导入

设计原则（规则一至规则七不再赘述）:
  - template 和 _render_html() 互斥（规则二）
  - 所有元数据从配置驱动，前端不硬编码（灵活性原则）
"""

# 配置格式:
#   "card_name": (tab_key, tab_label, tab_order, order, is_headline, span_full, template, refresh_seconds)
#
#   tab_key:      标签页标识符，如 "signals", "decisions", "data"
#   tab_label:    标签页显示名，如 "今日信号"
#   tab_order:    标签页排列顺序，数字越小越靠左
#   order:        标签页内卡片排列顺序，数字越小越靠上
#   is_headline:  bool, 是否使用头条高亮样式
#   span_full:    bool, 是否占满整行
#   template:     Jinja2 模板文件名（不含路径和扩展名）或 None（使用 _render_html()）
#   refresh:      自动刷新间隔（秒），0 = 不自动刷新

CARD_CONFIG: dict[str, tuple[str, str, int, int, bool, bool, str | None, int]] = {
    # ── 今日信号（每天打开第一眼看到的投资重点） ──
    "consensus":       ("signals",   "今日信号",   1, 1, True,  False, "consensus",       600),
    "anomaly":         ("signals",   "今日信号",   1, 2, False, False, "anomaly",          600),
    "rotation":        ("signals",   "今日信号",   1, 3, False, False, "rotation",        600),
    "crypto":          ("signals",   "今日信号",   1, 4, False, False, None,              300),
    "system_status":   ("signals",   "今日信号",   1, 5, False, False, "system_status",    60),

    # ── 投资决策（该买什么？该卖什么？） ──
    "chat":            ("decisions", "投资决策",   2, 1, False, True,  None,                0),
    "role_picker":     ("decisions", "投资决策",   2, 2, False, True,  None,                0),
    "portfolio":       ("decisions", "投资决策",   2, 3, False, True,  None,                0),
    "accuracy":        ("decisions", "投资决策",   2, 4, False, False, "accuracy",         300),

    # ── 深度研究（为什么？谁说的？历史怎么看？） ──
    "timeline":        ("research",  "深度研究",   3, 1, False, False, "timeline",         600),
    "network":         ("research",  "深度研究",   3, 2, False, False, "network",         3600),
    "portrait":        ("research",  "深度研究",   3, 3, False, False, None,             300),
    "portrait_generate":("research", "深度研究",   3, 4, False, False, None,               0),

    # ── 数据管理（数据是否新鲜？如何补数据？） ──
    "pipeline_execute":("data",      "数据管理",   4, 1, False, True,  None,              15),
    "api_status":      ("data",      "数据管理",   4, 2, False, False, "api_status",      30),
    "fetch_control":   ("data",      "数据管理",   4, 3, False, False, "fetch_control",    0),
    "asset_alias":     ("data",      "数据管理",   4, 4, False, False, None,             300),

    # ── 通知与设置（自动化、推送、高级工具） ──
    "daemon":          ("settings",  "通知与设置", 5, 1, False, False, "daemon",           5),
    "telegram":        ("settings",  "通知与设置", 5, 2, False, False, "telegram",         0),
    "script_runner":   ("settings",  "通知与设置", 5, 3, False, False, "script_runner",    0),
    "config_center":   ("settings",  "通知与设置", 5, 0, False, True,  "config_center",    0),
}


def apply_card_config(card) -> None:
    """将 CARD_CONFIG 中的元数据注入卡片实例。

    CARD_CONFIG 是唯一权威来源——无条件覆盖卡片实例的属性。
    这确保了即使卡片类本身设置了不同的值，配置中的值也会生效。

    Args:
        card: Card 实例
    """
    name = card.name
    if not name or name not in CARD_CONFIG:
        return

    cfg = CARD_CONFIG[name]
    (tab, tab_label, tab_order, order,
     is_headline, span_full, template, refresh) = cfg

    # 无条件覆盖（CARD_CONFIG 是唯一权威来源）
    card.tab = tab
    card.tab_label = tab_label
    card.tab_order = tab_order
    card.order = order
    card.is_headline = is_headline
    card.span_full = span_full

    # 显示名 + 一句话说明（命名优化层，不改代码标识符）
    card.display_title = CARD_DISPLAY.get(name, ("", ""))[0]
    card.subtitle = CARD_DISPLAY.get(name, ("", ""))[1]

    # template 和 refresh：仅在 CARD_CONFIG 指定时覆盖
    if template:
        card.template = f"{template}.html"
    if refresh:
        card.refresh = refresh


# ═══════════════════════════════════════════════════════
# 显示名 + 一句话功能说明（命名优化层）
# ═══════════════════════════════════════════════════════
# 格式: "card_name": ("用户看到的中文标题", "一句话说明这个模块/按钮做什么")
# 目的：让用户一进来就明白每个卡片代表什么功能，不再是技术黑话。
# 注意：这里只改"显示名"，不动卡片的 name 标识符 / 路由 / 文件名，零回归风险。

CARD_DISPLAY: dict[str, tuple[str, str]] = {
    # ── 今日信号 ──
    "consensus":       ("共识标的",       "多位分析师在相近时间同时看好的标的，共识分越高越值得关注"),
    "anomaly":         ("观点异动",       "检测分析师近期观点与以往的明显偏离，捕捉态度转折信号"),
    "rotation":        ("热门板块",       "近期被讨论热度快速上升的行业板块，捕捉资金轮动方向"),
    "crypto":          ("加密资产信号",   "被追踪分析师提及的加密资产价格与讨论热度"),
    "system_status":   ("数据状态",       "今日数据采集、处理进度与系统健康状态"),

    # ── 投资决策 ──
    "chat":            ("智能问答",       "直接询问分析师历史观点库，快速追溯标的、观点与来源"),
    "role_picker":     ("分析师模拟选股", "让 AI 代入某位分析师的风格，针对指定板块给出选股方案"),
    "portfolio":       ("我的持仓诊断",   "粘贴你的持仓，AI 结合分析师观点给出加减仓建议"),
    "accuracy":        ("历史胜率",       "回溯每位分析师历史信号的真实收益与胜率"),

    # ── 深度研究 ──
    "timeline":        ("观点时间线",     "分析师看多看空观点随时间的变化曲线"),
    "network":         ("信息源关系",     "分析师之间的关注与互动关系，发现潜在信息源头"),
    "portrait":        ("分析师画像",     "已生成的分析师投资风格画像，点击展开查看全文"),
    "portrait_generate":("生成分析师画像", "选择分析师与时间范围，让 AI 归纳其投资风格"),

    # ── 数据管理 ──
    "pipeline_execute":("处理队列",       "查看并运行待处理的筛选、分析、补行情、画像等任务"),
    "api_status":      ("账号采集状态",   "采集 API 的额度、限流与各监控账号已采集条数"),
    "fetch_control":   ("手动采集",       "针对指定账号手动补采某一时间段的推文"),
    "asset_alias":     ("标的代码映射",   "维护「提及名称 → 标的代码」映射，提升识别准确率"),

    # ── 通知与设置 ──
    "daemon":          ("自动采集",       "启停后台自动采集进程，开启后定时抓取新推文"),
    "telegram":        ("推送通知",       "配置 Telegram 机器人，把重要信号推送到你的手机"),
    "script_runner":   ("高级工具",       "手动触发后台脚本，供调试、维护与批量生成信号使用"),
    "config_center":   ("用户配置",       "集中管理 LLM、Twitter API、Telegram Bot 和观察对象"),
}

# ═══════════════════════════════════════════════════════
# 信号治理卡片扩展
# ═══════════════════════════════════════════════════════

GOVERNANCE_CARD_CONFIG: dict[str, tuple[str, str, int, int, bool, bool, str | None, int]] = {
    "quality_gate":    ("signals",   "今日信号",   1, 0, False, False, "quality_gate",    300),
    "risk_alerts":     ("signals",   "今日信号",   1, 1, False, False, "risk_alerts",     300),
    "panel_review":    ("decisions", "投资决策",   2, 0, False, True,  "panel_review",      0),
    "publish_review":  ("data",      "数据管理",   4, 0, False, False, "publish_review",    0),
}

GOVERNANCE_CARD_DISPLAY: dict[str, tuple[str, str]] = {
    "quality_gate":    ("信号质量门禁", "今日信号的证据完整性、数据新鲜度与来源可靠性检查"),
    "risk_alerts":     ("风险提示",     "异常推广、群荐股、杀猪盘、话术诱导等风险信号扫描"),
    "panel_review":    ("多角色评审",   "价值/成长/宏观/趋势/游资/风控/信源/AI瓶颈 8 大流派对信号的结构化评审"),
    "publish_review":  ("发布审核",     "信号发布前的最终阻断检查：证据缺口、风险等级、评审分歧"),
}


# 扩充到主配置
CARD_CONFIG.update(GOVERNANCE_CARD_CONFIG)
CARD_DISPLAY.update(GOVERNANCE_CARD_DISPLAY)
