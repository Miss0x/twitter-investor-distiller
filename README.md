# Twitter 用户蒸馏 AI 助手

采集精选 X/Twitter 投资者的发言和上下文，通过大模型分析 → 清洗校准 → 多时间窗口投资画像生成。

## 当前状态

- 数据采集：浏览器真人化抓取，1872 条推文入库
- 分析流水线：过滤 → 深度分析 → 清洗校准 → 多窗口画像
- 股价数据：96 只美股已拉取，Polygon.io API
- 加密货币：22 币种行情，Polygon.io + CoinMarketCap
- 控制台：Streamlit Web UI + FastAPI 任务队列

## 采集目标

- **@TJ_Research**：686+46 条已分析（2025-01 + 2025-05）
- **@dearbaibabybus**：404 条已分析（原 @frankyluan）

## 快速开始

```bash
pip install -r requirements.txt

# 初始化数据库
python -m scripts.bootstrap

# 启动后端 API
python -m uvicorn src.interfaces.web_api:app --host 0.0.0.0 --port 8000

# 启动前端控制台
python -m streamlit run src/interfaces/web_ui.py --server.port 8501
```

## 流水线架构

```
爬虫(DB) → 过滤(filter) → 深度分析(analyze) → 清洗校准(clean) → 画像(portrait)
                                      ↓
                                股价拉取(fetch_price)
                                加密货币(fetch_crypto)
```

## 项目结构

```
src/
├── crawler/         # 浏览器抓取、媒体下载、进度跟踪
├── interfaces/      # FastAPI (web_api)、Streamlit (web_ui)
├── pipeline/        # 任务执行器 (task_executor)
├── storage/         # SQLite ORM、媒体管理
├── ai/              # LLM 客户端、Prompts
├── vectorization/   # 向量化与 RAG（待接入）
└── utils/           # 日志、环境变量
config/              # pipeline.yaml、timing.yaml、users.yaml
scripts/             # 工具脚本（bootstrap、clean_analysis、fetch_prices 等）
data/                # SQLite DB、prices.json、stock_alias.csv、pipeline/ 分析结果
```

## 关键数据文件

| 文件 | 说明 |
|------|------|
| `data/pipeline/*_filtered.json` | 过滤结果（投资相关判断） |
| `data/pipeline/*_analyzed.json` | 深度分析结果（11 字段） |
| `data/pipeline/*_analyzed_cleaned.json` | 清洗校准版（stock_details、crypto_details） |
| `data/stock_alias.csv` | 股票别名映射（人工修正累积） |
| `data/prices.json` | Polygon 股价日线 |
| `data/crypto_prices.json` | 加密货币行情 |
