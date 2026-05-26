# Twitter Investor Distiller — AI 投资研究助手

采集精选 X/Twitter 投资者的发言 → 大模型分析 → 多维信号量化 → 角色代入选股 → 实时预警。

## 当前架构

- **数据采集**: twitterapi.io API（主路径）+ 浏览器真人抓取（备灾）
- **前端**: FastAPI + Jinja2 卡片模块化仪表盘，20 张独立卡片，4 个标签页
- **后端**: SQLite + Chroma 向量库 + OpenAI 兼容 LLM
- **入口**: Web 仪表盘 + Telegram Bot + FastAPI

## 采集目标

| 分析师 | 画像 |
|--------|------|
| **@TJ_Research** | 宏观趋势型，准确率 46% |
| **@dearbaibabybus** | 成长波段型，准确率 45% |

## 快速开始

```bash
pip install -r requirements.txt

# 配置 .env（复制 .env.example 并填入密钥）
cp .env.example .env

# 启动 Web 仪表盘
python -m uvicorn src.interfaces.web_api:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000`。

## 仪表盘标签页

| 标签页 | 卡片 |
|--------|------|
| **抓取仪表盘** | 系统状态、实时API采集、手动拉取、Telegram通知、准确率、API状态 |
| **推文分析** | 流水线执行、资产代码库、脚本工具箱 |
| **分析师画像** | 画像生成（时间窗口+日历）、画像浏览（点击展开） |
| **信号与洞察** | 角色代入选股、持股顾问、共识TOP5、板块轮动、加密货币信号、异常检测、情绪时间线、信源推荐 |

## 流水线架构

```
API采集(DB) → 过滤(filter) → 深度分析(analyze) → 清洗校准(clean)
    │                           │
    └───────────────┬───────────┼───────┬───────┬──────┐
                    ▼           ▼       ▼       ▼      ▼
               信号量化(#1)  联动(#4) 轮动(#8) 时间线(#9) 异常(#10)
                    │           │       │       │      │
                    └───────┬───┴───────┴───────┴──────┘
                            ▼
                   画像(portrait) → 角色代入(#7)
                            │
                   持仓顾问(#13) → Telegram(#5) → 实时推送
```

## 项目结构

```
src/
├── cards/            # 20 张卡片模块（一文件一功能）
├── interfaces/       # FastAPI Web API + Telegram Bot
├── crawler/          # twitterapi.io 数据抓取 + 浏览器备灾
├── pipeline/         # 任务执行器（filter/analyze/clean/portrait）
├── storage/          # SQLite ORM 模型
├── ai/               # LLM 客户端 + ChatEngine + RAG
├── vectorization/    # Chroma 向量存储 + 检索
├── utils/            # 环境变量 + 日志
└── config.py         # 统一配置单例

scripts/              # 13 个分析脚本
data/
├── pipeline/         # 分析结果 + 画像
├── accuracy/consensus/rotation/timeline/anomaly/network/
├── users.json        # 监控用户列表
├── stock_alias.csv   # 股票代码映射
└── sector_map.json   # 行业分类

legacy/               # 已废弃的旧代码归档
templates/cards/      # Jinja2 卡片模板
```

## 验收指标

| 指标 | 状态 |
|------|------|
| 信号覆盖 | 95% (1076/1136) |
| 准确率样本 | TJ 41, deba 82 |
| 异常 FPR | 5.8%/8.7% |
| PE 覆盖 | 104 只美股 |
| 卡片数量 | 20 张 |
| 代码质量 | 64/72 审计项已修复 |

## License

MIT
