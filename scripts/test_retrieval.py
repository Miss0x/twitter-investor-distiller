"""检索测试脚本。"""
from __future__ import annotations

from pathlib import Path

from src.vectorization.retriever import TweetRetriever


def main() -> None:
    question = "先进封装设备"
    results = TweetRetriever().retrieve(question, top_k=5)
    out = [f"question={question}", f"results={len(results)}"]
    for index, item in enumerate(results, start=1):
        meta = item.get("metadata") or {}
        text = (item.get("text") or "").replace("\n", " ")[:200]
        out.append(f"\n#{index}")
        out.append(f"username={meta.get('username')}")
        out.append(f"tweet_id={meta.get('tweet_id')}")
        out.append(f"url={meta.get('url')}")
        out.append(f"distance={item.get('distance')}")
        out.append(f"text={text}")
    target = Path("data/raw/retrieval_test.txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
