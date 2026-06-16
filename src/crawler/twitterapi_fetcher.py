"""
twitterapi.io 数据抓取器 —— 替代浏览器爬虫的主数据获取路径
============================================================

## 模块定位
本模块通过第三方 API 服务 twitterapi.io 拉取推文和用户数据，
是项目中**唯一的主抓取路径**（替代了早期的 Selenium/浏览器爬虫方案）。

## 核心设计

### API 分层
```
  _headers()          → 构造认证请求头（从 .env 读取 API Key）
       │
  TwitterAPIFetcher   → 面向业务的高层封装类
       │
       ├── _get()              → 底层 HTTP GET 请求（含错误处理）
       ├── fetch_user_info()   → 拉取用户资料 → 写入 User 表
       ├── fetch_tweets()      → 拉取推文 → 写入 Tweet 表
       ├── _save_tweets()      → 推文去重 + 批量入库
       ├── get_last_tweet_ts() → 查询最新推文时间戳（增量抓取用）
       └── get_user_tweet_count() → 查询用户推文总数
```

### 增量抓取策略
增量抓取的核心是 **since_ts 参数**：
1. 调用 get_last_tweet_ts(username) 获取数据库中最新的推文时间戳
2. 将时间戳传入 fetch_tweets(username, since_ts=ts) 作为下界
3. API 返回 ts 之后的推文，避免重复拉取

### Cursor 翻页机制
twitterapi.io 使用 cursor 实现分页：
- 每页返回 has_next_page 标志和 next_cursor 值
- 将 next_cursor 作为下一页请求的 cursor 参数
- 循环直到 has_next_page=false 或达到 max_pages 上限

### 去重逻辑
在 _save_tweets() 中实现两层去重：
1. **数据库级去重**：批量查询已有 tweet_id，构造 existing_ids 集合
2. **应用级跳过**：新推文在写入前检查 tweet_id 是否在 existing_ids 中

### 限流/冷却控制
- HTTP 超时设为 15 秒，避免长时间阻塞
- fetch_tweets 的 max_pages 默认 50，可限制单次拉取量
- 调用方在 fetch_tweets 之间主动等待 60-120 秒控制频率
- API Key 从 .env 读取，不在代码中硬编码
"""
from __future__ import annotations

import requests
from datetime import datetime

from src.storage.database import db
from src.storage.models import Tweet, User
from src.config import config

# twitterapi.io 的基础 URL
API_BASE = "https://api.twitterapi.io"


def _headers() -> dict:
    """构造 API 请求的认证请求头。
    
    从 .env 配置文件读取 api.twitterapi_key，
    注入 X-API-Key 请求头进行身份认证。

    Raises:
        RuntimeError: 如果 TWITTERAPI_KEY 未在 .env 中设置

    Returns:
        dict: 含 X-API-Key 的请求头字典
    """
    key = config.twitterapi_key
    if not key:
        raise RuntimeError("TWITTERAPI_KEY 未在 .env 中设置")
    return {"X-API-Key": key}


class TwitterAPIFetcher:
    """通过 twitterapi.io 拉取推文和用户数据的主抓取器。

    使用方法：
        fetcher = TwitterAPIFetcher()
        fetcher.fetch_user_info("username")   # 拉取/更新用户资料
        fetcher.fetch_tweets("username")      # 拉取用户推文
    """

    def __init__(self):
        """初始化数据库连接。"""
        db.init_db()

    # ── 底层 HTTP 请求 ──

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """底层 HTTP GET 请求封装（带错误处理）。
        
        统一处理认证、超时和 HTTP 错误，上层调用方只需关注业务逻辑。

        Args:
            endpoint: API 端点路径（如 "/twitter/user/info"）
            params: URL 查询参数字典

        Returns:
            dict: API 返回的 JSON 数据

        Raises:
            requests.HTTPError: HTTP 状态码错误时自动抛出
        """
        r = requests.get(
            f"{API_BASE}{endpoint}",
            headers=_headers(),
            params=params,
            timeout=15  # 15 秒超时，防止无限等待
        )
        r.raise_for_status()  # 非 2xx 状态码自动抛异常
        return r.json()

    # ── 用户资料抓取 ──

    def fetch_user_info(self, username: str) -> dict:
        """拉取单个推特用户的资料并写入/更新数据库。
        
        如果用户已存在（按 username 查重），则更新现有记录；
        如果不存在，则创建新记录。

        更新的字段：
            - 显示名称（display_name）
            - 粉丝数（followers_count）
            - 关注数（following_count）
            - 个人简介（description）
            - 推文总数（tweet_count）
            - 头像 URL（profile_image_url）

        Args:
            username: 推特用户名（不含 @）

        Returns:
            dict: {"ok": True, "followers": 粉丝数} 
                  或 {"ok": False, "error": "错误信息"}
        """
        data = self._get("/twitter/user/info", {"userName": username})
        user_data = data.get("data", {})
        
        # API 返回空数据时的处理
        if not user_data:
            err = data.get("message") or data.get("error") or f"@{username} 不存在或API返回空"
            return {"ok": False, "error": err}

        session = db.get_session()
        try:
            existing = session.query(User).filter(User.username == username).first()
            if existing:
                # ── 更新已有用户信息 ──
                existing.display_name = user_data.get("name")
                existing.followers_count = user_data.get("followers", 0)
                existing.following_count = user_data.get("following", 0)
                existing.description = user_data.get("description")
                existing.tweet_count = user_data.get("statusesCount", 0)
                existing.profile_image_url = user_data.get("profilePicture")
                existing.updated_at = datetime.now()  # 标记更新时间
            else:
                # ── 创建新用户记录 ──
                u = User(
                    username=username,
                    display_name=user_data.get("name"),
                    followers_count=user_data.get("followers", 0),
                    following_count=user_data.get("following", 0),
                    description=user_data.get("description"),
                    tweet_count=user_data.get("statusesCount", 0),
                    profile_image_url=user_data.get("profilePicture"),
                )
                session.add(u)
            session.commit()
            return {"ok": True, "followers": user_data.get("followers")}
        except Exception as e:
            session.rollback()  # 异常时回滚事务
            return {"ok": False, "error": str(e)}
        finally:
            session.close()

    # ── 时间戳查询 —— 增量抓取的基础 ──

    def get_last_tweet_ts(self, username: str) -> int:
        """查询某用户数据库中最新推文的 Unix 时间戳。
        
        这是增量抓取的核心函数。通过返回最新推文的时间戳 + 1，
        调用方可以将其作为 fetch_tweets 的 since_ts 参数，
        实现只拉取上次之后的新推文。

        查询逻辑：
            1. 通过 User 关系找到该用户的所有推文
            2. 按 created_at_twitter 降序排序取第一条
            3. 返回时间戳 + 1（确保不重复拉取同一秒的推文）

        Args:
            username: 推特用户名

        Returns:
            int: Unix 时间戳（秒）。如果用户无推文则返回 0
        """
        session = db.get_session()
        try:
            last = session.query(Tweet).filter(
                Tweet.user.has(username=username)  # 关联查询：通过 relationship
            ).order_by(Tweet.created_at_twitter.desc()).first()
            
            if last and last.created_at_twitter:
                return int(last.created_at_twitter.timestamp()) + 1  # +1 避免重复
            return 0  # 无存量推文 → 从 0 开始全量拉取
        except Exception as e:
            __import__('logging').warning(f"get_last_tweet_ts({username}) failed: {e}")
            return 0
        finally:
            session.close()

    def get_user_tweet_count(self, username: str) -> int:
        """查询某用户数据库中的推文总数。
        
        用于 UI 显示进度和判断是否需要增量拉取。

        Args:
            username: 推特用户名

        Returns:
            int: 推文总数。异常时返回 0
        """
        session = db.get_session()
        try:
            return session.query(Tweet).join(User).filter(User.username == username).count()
        except Exception as e:
            __import__('logging').warning(f"get_user_tweet_count({username}) failed: {e}")
            return 0
        finally:
            session.close()

    # ── 推文抓取主函数 ──

    def fetch_tweets(self, username: str, max_pages: int = 50, cursor: str = "",
                     since_ts: int = 0, until_ts: int = 0) -> dict:
        """拉取指定用户的推文（支持增量、翻页、限频）。
        
        这是整个抓取流程的入口函数。

        参数说明：
        ┌─────────────┬───────────────────────────────────────┐
        │ max_pages   │ 最大翻页数，默认 50                    │
        │ cursor      │ 起始翻页游标（续拉时用）              │
        │ since_ts    │ Unix 时间戳下界（增量拉取用）         │
        │ until_ts    │ Unix 时间戳上界（限定拉取范围）       │
        └─────────────┴───────────────────────────────────────┘

        Cursor 翻页工作机制：
            1. 发送请求（带当前 cursor）
            2. API 返回 tweets[] + has_next_page + next_cursor
            3. 如果 has_next_page=true 且有 next_cursor：
               将 next_cursor 赋给 cursor 变量继续循环
            4. 否则停止翻页

        since_ts 增量拉取工作原理：
            1. 调用方先通过 get_last_tweet_ts() 获取 DB 中最新的时间戳
            2. 将时间戳作为 since_ts 传入
            3. API 只返回 since_ts 之后发布的推文
            4. 增量保存到数据库（_save_tweets 内部去重）

        Args:
            username: 推特用户名
            max_pages: 最大翻页数（防止无限循环和超出配额）
            cursor: 翻页游标（为空表示从第一页开始）
            since_ts: 只拉取此时间之后的推文（增量模式）
            until_ts: 只拉取此时间之前的推文（可选上限）

        Returns:
            dict: {
                "ok": True/False,
                "pages": 实际翻页数,
                "total_new": 新增推文数,
                "cursor": 下一页游标（为空表示已到末尾）
            }
        """
        total_new = 0  # 本次新增推文计数
        pages = 0      # 已翻页计数

        # ── 构造搜索查询语句 ──
        # twitterapi.io 使用类似 Twitter 搜索语法的 query 参数
        query_parts = [f"from:{username}"]
        if since_ts > 0:
            query_parts.append(f"since_time:{since_ts}")  # 时间下界
        if until_ts > 0:
            query_parts.append(f"until_time:{until_ts}")  # 时间上界
        base_query = " ".join(query_parts)

        # ── Cursor 翻页循环 ──
        for page in range(max_pages):
            params = {"query": base_query, "queryType": "Latest"}  # Latest = 最新优先
            if cursor:
                params["cursor"] = cursor  # 传入上一页的游标

            try:
                data = self._get("/twitter/tweet/advanced_search", params)
            except Exception as e:
                # 单页失败时返回已拉取的数据，不丢弃已保存的
                return {
                    "ok": False, "error": str(e),
                    "pages": pages, "total_new": total_new, "cursor": cursor
                }

            tweets = data.get("tweets", [])
            saved = self._save_tweets(username, tweets)  # 去重+入库
            total_new += saved
            pages += 1

            # ── 翻页终止条件 ──
            if not data.get("has_next_page"):
                break  # API 表明没有后续数据
            cursor = data.get("next_cursor", "")
            if not cursor:
                break  # 无下一页游标（防御性检查）

        return {"ok": True, "pages": pages, "total_new": total_new, "cursor": cursor}

    # ── 推文入库（含去重） ──

    def _save_tweets(self, username: str, api_tweets: list[dict]) -> int:
        """将 API 返回的推文批量保存到数据库（带去重）。

        入库流程：
            1. 查找/创建 User 记录
            2. 批量查询已有 tweet_id → 构建去重集合（避免 N+1 查询）
            3. 遍历 API 推文：
               a. 检查 tweet_id 是否已存在 → 跳过
               b. 解析推文属性（原文/引用/转发/回复/互动数据）
               c. 创建 Tweet 对象并加入 session
            4. 一次性 commit 所有新推文

        去重策略 —— 为什么用批量查询而非逐条查询：
            如果逐条 SELECT（N+1 模式），100 条推文产生 100 次 DB 查询。
            批量模式：500 条一组，100 条只需 1 次查询，大幅提升性能。

        翻页去重场景：
            同一用户的抓取可能分多页进行，每页调用一次 _save_tweets，
            但同一推文可能出现在不同页的 API 返回中（API 去重不完美）。
            通过 existing_ids 确保每条推文只写入一次。

        Args:
            username: 推特用户名（用于查找/创建 User）
            api_tweets: API 返回的原始推文列表

        Returns:
            int: 本次实际新增的推文数
        """
        session = db.get_session()
        saved = 0
        try:
            # 查找或创建用户记录
            user = session.query(User).filter(User.username == username).first()
            if not user:
                user = User(username=username, display_name=username)
                session.add(user)
                session.flush()  # 立即获取 user.id 用于后续关联

            # ── 批量去重查询 ──
            # 收集所有 API 返回的 tweet_id
            api_ids = [t.get("id") for t in api_tweets if t.get("id")]
            existing_ids = set()
            # 分批查询（每次 500 个 ID），防止 SQL IN 子句过长
            for start in range(0, len(api_ids), 500):
                chunk = api_ids[start:start + 500]
                existing_ids.update(
                    row[0] for row in session.query(Tweet.tweet_id).filter(
                        Tweet.tweet_id.in_(chunk)
                    ).all()
                )

            # ── 逐条处理推文 ──
            for t in api_tweets:
                tw_id = t.get("id")
                # ★ 核心去重：已在库中的推文直接跳过
                if not tw_id or tw_id in existing_ids:
                    continue

                # 提取引用和转发的子推文
                qt = t.get("quoted_tweet")       # 引用推文
                rt = t.get("retweeted_tweet")     # 被转发的推文
                created = _parse_twitter_time(t.get("createdAt", ""))

                # 构建 Tweet ORM 对象
                tw = Tweet(
                    tweet_id=tw_id,
                    user_id=user.id,
                    text=t.get("text", ""),
                    created_at_twitter=created,
                    # ── 推文类型标记 ──
                    is_reply=t.get("isReply", False),      # 是否为回复
                    is_retweet=rt is not None,             # 是否为纯转发
                    is_quote=qt is not None,               # 是否为引用推文
                    # ── 回复相关 ──
                    replied_to_tweet_id=t.get("inReplyToId"),
                    replied_to_user=t.get("inReplyToUsername"),
                    # ── 引用相关 ──
                    quoted_tweet_id=qt.get("id") if qt else None,
                    quoted_user=qt.get("author", {}).get("userName") if qt else None,
                    quoted_text=qt.get("text") if qt else None,
                    # ── 互动数据 ──
                    like_count=t.get("likeCount", 0),       # 点赞数
                    retweet_count=t.get("retweetCount", 0),  # 转发数
                    reply_count=t.get("replyCount", 0),      # 回复数
                    quote_count=t.get("quoteCount", 0),      # 引用数
                    view_count=t.get("viewCount", 0),        # 浏览数
                    url=t.get("url", ""),                    # 推文链接
                    # ── 扩展数据（JSON 格式存储额外字段） ──
                    extra_data={
                        "bookmark_count": t.get("bookmarkCount", 0),  # 收藏数
                        "lang": t.get("lang", ""),                    # 语言
                        "source": t.get("source", ""),               # 发布客户端
                        "conversation_id": t.get("conversationId"),  # 对话 ID
                    },
                )
                session.add(tw)
                saved += 1

            session.commit()
            return saved
        except Exception:
            session.rollback()  # 任何异常回滚整个事务
            raise
        finally:
            session.close()


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def _parse_twitter_time(s: str) -> datetime:
    """解析 Twitter API 返回的时间字符串为标准 Python datetime。

    Twitter API 的时间格式： "Mon Apr 07 12:34:56 +0000 2025"
    对应的 strftime 格式： "%a %b %d %H:%M:%S %z %Y"

    Args:
        s: Twitter API 的时间字符串

    Returns:
        datetime: 解析后的 Python datetime 对象。
                 解析失败时返回当前时间（兜底策略，避免插入失败）
    """
    if not s:
        return datetime.now()
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        # 时间格式不匹配时返回当前时间，保证数据能正常入库
        return datetime.now()
