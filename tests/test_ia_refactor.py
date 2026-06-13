from collections import Counter
from pathlib import Path


def test_card_config_uses_investment_signal_information_architecture():
    from src.cards.cards_config import CARD_CONFIG, CARD_DISPLAY

    assert len(CARD_CONFIG) == 26
    assert Counter(value[0] for value in CARD_CONFIG.values()) == {
        "signals": 7,
        "decisions": 6,
        "research": 4,
        "data": 5,
        "settings": 4,
    }

    assert CARD_CONFIG["consensus"][:4] == ("signals", "今日信号", 1, 1)
    assert CARD_CONFIG["chat"][:4] == ("decisions", "投资决策", 2, 1)
    assert CARD_CONFIG["pipeline_execute"][:4] == ("data", "数据管理", 4, 1)
    assert CARD_CONFIG["daemon"][:4] == ("settings", "通知与设置", 5, 1)

    assert CARD_DISPLAY["consensus"][0] == "共识标的"
    assert CARD_DISPLAY["chat"][0] == "智能问答"
    assert CARD_DISPLAY["pipeline_execute"][0] == "处理队列"
    assert CARD_DISPLAY["asset_alias"][0] == "标的代码映射"
    assert CARD_DISPLAY["daemon"][0] == "自动采集"


def test_dashboard_template_uses_new_tabs_and_daemon_copy():
    text = Path("src/templates/base.html").read_text(encoding="utf-8")

    assert '<span id="topbar_title" class="title">今日信号</span>' in text
    for tab_key in ["signals", "decisions", "research", "data", "settings"]:
        assert f"{tab_key}:" in text or f"{tab_key!r}:" in text

    assert "自动采集运行中" in text
    assert "自动采集已停止" in text
    assert "Daemon 运行中" not in text
    assert "Daemon 已停止" not in text
    assert "TABS.some(function(t) { return t.key === lastTab; })" in text


def test_processing_queue_copy_is_productized():
    text = Path("src/cards/pipeline_execute.py").read_text(encoding="utf-8")

    for expected in [
        "处理队列",
        "扫描新内容",
        "运行分析流程",
        "筛选推文",
        "分析观点",
        "补全行情",
        "补全加密行情",
        "校准标的",
        "标的代码映射",
        "应用映射修正",
        "提及名称",
        "标的代码",
        "填写代码",
    ]:
        assert expected in text

    for legacy in ["种子任务", "流水线执行</div>", "股价拉取", "运行校准", "资产代码库", "填代码"]:
        assert legacy not in text


def test_asset_alias_copy_is_productized():
    text = Path("src/cards/functional_cards.py").read_text(encoding="utf-8")

    for expected in ["标的代码映射", "提及名称", "标的代码", "填写代码", "代码明确"]:
        assert expected in text

    for legacy in ["资产代码库", "Ticker", "填代码", "ticker 明确"]:
        assert legacy not in text


def test_chat_card_entry_is_registered_and_visible():
    from src.cards import get_card

    card = get_card("chat")
    assert card is not None
    html = card.render(card.get_data())
    assert "问分析师库" in html
    assert "基于检索结果生成，仅供研究参考" in html
    assert 'data-action="ask-chat"' in html


def test_chat_examples_escape_data_question_attributes():
    from src.cards.chat_card import ChatCard

    card = ChatCard()
    html = card.render({"examples": ['他说 "NVDA" 怎么样？']})
    assert 'data-question="他说 &quot;NVDA&quot; 怎么样？"' in html
    assert 'data-question="他说 "NVDA" 怎么样？"' not in html


def test_pipeline_retry_and_skip_use_api_fetch():
    text = Path("src/templates/base.html").read_text(encoding="utf-8")

    assert "async function retryTaskPE(id) { await fetch(" not in text
    assert "async function skipTaskPE(id) { await fetch(" not in text
    assert "apiFetch('/pipeline/tasks/' + id + '/retry'" in text
    assert "apiFetch('/pipeline/tasks/' + id + '/skip'" in text


def test_chat_ui_preserves_state_and_ignores_stale_answers():
    text = Path("src/templates/base.html").read_text(encoding="utf-8")

    assert "var CHAT_STATE =" in text
    assert "hydrateChatState();" in text
    assert "CHAT_STATE.requestId += 1" in text
    assert "if (requestId !== CHAT_STATE.requestId) return;" in text
    assert "CHAT_STATE.answerHtml" in text


def test_chat_action_clamps_top_k_and_handles_invalid_values():
    text = Path("src/interfaces/web_api.py").read_text(encoding="utf-8")

    assert "def _normalize_chat_top_k" in text
    assert "return max(1, min(value, 20))" in text
    assert "top_k = _normalize_chat_top_k(payload.get(\"top_k\", 5))" in text


def test_ai_html_results_are_sanitized_before_rendering():
    text = Path("src/templates/base.html").read_text(encoding="utf-8")

    assert "function sanitizeTrustedHtml" in text
    assert "sanitizeTrustedHtml(result.html)" in text
    assert "rp_result').innerHTML = result && result.ok ? result.html" not in text
    assert "pf_result').innerHTML = result && result.ok ? result.html" not in text


def test_pytest_is_available_in_project_requirements():
    text = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pytest" in text


def test_chat_engine_uses_generic_openai_compatible_llm_config():
    text = Path("src/ai/chat_engine.py").read_text(encoding="utf-8")

    assert 'os.getenv("CHAT_MODEL")' in text
    assert 'os.getenv("LLM_API_KEY")' in text
    assert 'os.getenv("LLM_BASE_URL")' in text
    assert 'base_url=self.base_url' in text
    assert 'os.getenv("OPENAI_API_KEY")' in text
    assert 'os.getenv("OPENAI_MODEL")' in text


def test_card_config_comments_use_current_information_architecture():
    text = Path("src/cards/cards_config.py").read_text(encoding="utf-8")
    header = text.split("\nCARD_CONFIG", 1)[0]

    assert '"signals"' in header
    assert '"今日信号"' in header
    for legacy in ['"overview"', '"operations"', '"今日概览"']:
        assert legacy not in header


def test_landing_page_matches_new_information_architecture():
    text = Path("src/templates/landing.html").read_text(encoding="utf-8")

    assert "免费开始使用" in text
    assert "https://github.com" not in text
    for label in ["智能信号采集", "AI 多维度分析", "信号治理门禁", "投资决策辅助", "深度研究工具", "实时推送通知"]:
        assert label in text
    assert "系统运维" not in text
    assert "登录" in text  # 登录入口存在


def test_dashboard_app_import_does_not_require_chromadb_at_startup():
    text = Path("src/interfaces/web_api.py").read_text(encoding="utf-8")

    top_level_imports = "\n".join(
        line for line in text.splitlines()
        if line.startswith("from ") or line.startswith("import ")
    )
    assert "from src.ai.chat_engine import ChatEngine" not in top_level_imports
    assert "        from src.ai.chat_engine import ChatEngine" in text
