"""#12 投资者关联网络 — Phase 4

从 tweet 的 is_reply/is_quote 关系构建有向图，
中心度分析发现高影响力用户 → 推荐新信源。

用法：python scripts/build_network.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

OUTPUT_DIR = Path("data/network")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect("data/twitter_data.db")
    cur = conn.cursor()

    edges: list[tuple[str, str, str]] = []
    tracked_users = {"TJ_Research", "dearbaibabybus"}

    # 从 tweet 表直接查互动
    cur.execute("""
        SELECT t.id, u.username, t.replied_to_user, t.quoted_user, t.is_reply, t.is_quote
        FROM tweets t JOIN users u ON t.user_id = u.id
        WHERE t.is_reply = 1 OR t.is_quote = 1
    """)
    for row in cur.fetchall():
        tid, username, replied_to, quoted_to, is_reply, is_quote = row
        if is_reply and replied_to:
            edges.append((username, replied_to, "reply"))
        if is_quote and quoted_to:
            edges.append((username, quoted_to, "quote"))
    conn.close()

    print(f"互动边: {len(edges)} 条")

    # 构建节点和邻接表
    nodes = set()
    adj: dict[str, Counter] = defaultdict(Counter)
    for src, dst, etype in edges:
        nodes.add(src)
        nodes.add(dst)
        adj[src][dst] += 1

    # 过滤：只保留在追踪用户邻域内的节点（2 跳以内）
    neighborhood = set(tracked_users)
    for u in tracked_users:
        for v in adj.get(u, {}):
            neighborhood.add(v)
            for w in adj.get(v, {}):
                neighborhood.add(w)

    filtered_edges = [(s, d, adj[s][d]) for s, d in set((s, d) for s, d, _ in edges) if s in neighborhood and d in neighborhood]

    # 计算加权入度（被引用/回复次数）
    in_degree = Counter()
    for s, d, w in filtered_edges:
        in_degree[d] += w

    # 推荐新信源：在邻域内但不在追踪用户中的高入度节点
    candidates = [(u, in_degree[u]) for u in neighborhood if u not in tracked_users and in_degree[u] > 0]
    candidates.sort(key=lambda x: x[1], reverse=True)

    print(f"网络节点: {len(neighborhood)}")
    print(f"网络边: {len(filtered_edges)}")

    # 输出
    result = {
        "nodes": sorted(neighborhood),
        "edges": [{"from": s, "to": d, "weight": w} for s, d, w in filtered_edges],
        "in_degree": dict(in_degree.most_common(30)),
        "recommendations": [{"user": u, "in_degree": d} for u, d in candidates[:10]],
    }

    out_path = OUTPUT_DIR / "investor_network.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n🔗 推荐新信源 TOP 5:")
    for u, d in candidates[:5]:
        print(f"  {u}: 被引用 {d} 次")
    print(f"\n已写入: {out_path}")


if __name__ == "__main__":
    main()
