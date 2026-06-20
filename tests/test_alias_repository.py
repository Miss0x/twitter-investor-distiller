"""AliasRepository 单元测试。

测试策略:
    - 每次测试使用独立的 tmp_path 创建临时 CSV 文件
    - 通过 monkeypatch 替换 AliasRepository 的内部 _PATH
    - 所有测试隔离，互不影响
    - 覆盖: 回 读/写/缓存/批量/边界值
"""
from __future__ import annotations

import pytest
from pathlib import Path

from src.storage.alias_repository import AliasRepository, AliasRow, _cache


# ── Fixtures ──


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    """创建标准测试 CSV 文件。"""
    p = tmp_path / "stock_alias.csv"
    p.write_text(
        "# 注释行\n"
        "NVIDIA,NVDA,显卡\n"
        "特斯拉,TSLA,汽车\n"
        "比特币,,SKIP|crypto\n"
        "未知币,,pending\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def mock_csv(csv_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """替换 AliasRepository 的 _PATH 为临时 CSV。"""
    monkeypatch.setattr("src.storage.alias_repository._PATH", csv_path)
    AliasRepository.clear_cache()
    return csv_path


# ── Test: get_all ──


class TestGetAll:
    def test_returns_alias_rows(self, mock_csv: Path):
        rows = AliasRepository.get_all()
        assert len(rows) == 4
        assert all(isinstance(r, AliasRow) for r in rows)

    def test_row_values(self, mock_csv: Path):
        rows = AliasRepository.get_all()
        assert rows[0].alias == "NVIDIA"
        assert rows[0].ticker == "NVDA"
        assert rows[1].alias == "特斯拉"
        assert rows[1].ticker == "TSLA"

    def test_empty_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        p = tmp_path / "empty.csv"
        p.touch()
        monkeypatch.setattr("src.storage.alias_repository._PATH", p)
        AliasRepository.clear_cache()
        assert AliasRepository.get_all() == []

    def test_missing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("src.storage.alias_repository._PATH", tmp_path / "nonexistent.csv")
        AliasRepository.clear_cache()
        assert AliasRepository.get_all() == []

    def test_comments_ignored(self, mock_csv: Path):
        rows = AliasRepository.get_all()
        assert all(not r.alias.startswith("#") for r in rows)


# ── Test: get_map ──


class TestGetMap:
    def test_only_confirmed(self, mock_csv: Path):
        m = AliasRepository.get_map()
        assert m["NVIDIA"] == "NVDA"
        assert m["特斯拉"] == "TSLA"
        assert "比特币" not in m
        assert "未知币" not in m

    def test_cache_hit(self, mock_csv: Path):
        m1 = AliasRepository.get_map()
        m2 = AliasRepository.get_map()
        assert m1 is m2

    def test_cache_invalidated_by_clear(self, mock_csv: Path):
        m1 = AliasRepository.get_map()
        AliasRepository.clear_cache()
        m2 = AliasRepository.get_map()
        assert m1 is not m2


# ── Test: get_skip_set ──


class TestGetSkipSet:
    def test_skipped_entries(self, mock_csv: Path):
        s = AliasRepository.get_skip_set()
        assert "比特币" in s  # ticker 为空 + notes 含 SKIP

    def test_returns_uppercase(self, mock_csv: Path):
        s = AliasRepository.get_skip_set()
        for alias in s:
            assert alias == alias.upper()

    def test_cache_hit(self, mock_csv: Path):
        s1 = AliasRepository.get_skip_set()
        s2 = AliasRepository.get_skip_set()
        assert s1 is s2


# ── Test: is_known_ticker ──


class TestIsKnownTicker:
    def test_known(self, mock_csv: Path):
        assert AliasRepository.is_known_ticker("NVDA") is True

    def test_unknown(self, mock_csv: Path):
        assert AliasRepository.is_known_ticker("XYZ") is False

    def test_empty_returns_false(self, mock_csv: Path):
        assert AliasRepository.is_known_ticker("") is False

    def test_too_long_returns_false(self, mock_csv: Path):
        assert AliasRepository.is_known_ticker("VERYLONG") is False

    def test_case_insensitive(self, mock_csv: Path):
        assert AliasRepository.is_known_ticker("nvda") is True


# ── Test: add ──


class TestAdd:
    def test_add_new(self, mock_csv: Path):
        AliasRepository.add("苹果", "AAPL", "科技")
        AliasRepository.clear_cache()
        rows = AliasRepository.get_all()
        assert any(r.alias == "苹果" for r in rows)

    def test_add_invalidates_cache(self, mock_csv: Path):
        m1 = AliasRepository.get_map()
        AliasRepository.add("微软", "MSFT", "科技")
        m2 = AliasRepository.get_map()
        assert m1 is not m2

    def test_duplicate_skipped(self, mock_csv: Path):
        count_before = len(AliasRepository.get_all())
        AliasRepository.add("NVIDIA", "NVDA", "dup")
        AliasRepository.clear_cache()
        count_after = len(AliasRepository.get_all())
        assert count_after == count_before

    def test_empty_alias_ignored(self, mock_csv: Path):
        count_before = len(AliasRepository.get_all())
        AliasRepository.add("", "TEST", "")
        AliasRepository.clear_cache()
        assert len(AliasRepository.get_all()) == count_before


# ── Test: add_many ──


class TestAddMany:
    def test_batch_insert(self, mock_csv: Path):
        count = AliasRepository.add_many([
            {"alias": "谷歌", "ticker": "GOOGL", "notes": "search"},
            {"alias": "亚马逊", "ticker": "AMZN", "notes": "ecommerce"},
        ])
        assert count == 2
        AliasRepository.clear_cache()
        m = AliasRepository.get_map()
        assert m["谷歌"] == "GOOGL"
        assert m["亚马逊"] == "AMZN"

    def test_dedup_in_batch(self, mock_csv: Path):
        count = AliasRepository.add_many([
            {"alias": "NVIDIA", "ticker": "NVDA"},
            {"alias": "AMD", "ticker": "AMD"},
        ])
        assert count == 1  # NVIDIA 已存在

    def test_empty_batch_returns_zero(self, mock_csv: Path):
        count = AliasRepository.add_many([])
        assert count == 0

    def test_accepts_aliasrow_directly(self, mock_csv: Path):
        rows = [AliasRow("台积电", "TSM", "semi")]
        count = AliasRepository.add_many(rows)
        assert count == 1
        AliasRepository.clear_cache()
        assert AliasRepository.is_known_ticker("TSM") is True


# ── Test: mtime caching ──


class TestMtimeCache:
    def test_mtime_fingerprint_changes_on_write(self, mock_csv: Path):
        """write 操作后缓存指纹必定变化。"""
        # 先触发缓存填充
        AliasRepository.get_all()
        fp0 = _get_cache_fingerprint()
        assert fp0 is not None, "缓存未填充"

        AliasRepository.add("新公司", "NEW", "test")
        fp1 = _get_cache_fingerprint()
        assert fp1 is None, "add 后缓存应被失效"


# ── Test: CSV 转义（回归测试）──
# 背景：2026-06-20 review 发现 add/add_many 用 f-string 拼接 CSV 字段，
#       若 note 字段含逗号/引号/换行，CSV 被破坏、读取错位。
#       此处锁定修复：必须用 csv.writer 自动转义。


class TestCsvEscape:
    def test_add_with_comma_in_note(self, mock_csv: Path):
        """备注含逗号时，读取后应原样保留（不被切分）。"""
        AliasRepository.add("新币", "NEW", "Q1, 2024 财报")
        rows = AliasRepository.get_all()
        match = [r for r in rows if r.alias == "新币"]
        assert len(match) == 1
        assert match[0].ticker == "NEW"
        assert match[0].notes == "Q1, 2024 财报"

    def test_add_with_quote_in_note(self, mock_csv: Path):
        """备注含引号时，读取后应原样保留（不被破坏）。"""
        AliasRepository.add("引号", "QT", '他说"好的"')
        rows = AliasRepository.get_all()
        match = [r for r in rows if r.alias == "引号"]
        assert len(match) == 1
        assert match[0].notes == '他说"好的"'

    def test_add_many_with_commas(self, mock_csv: Path):
        """批量写入多条含逗号的备注，全部正确读回。"""
        AliasRepository.add_many([
            AliasRow("多逗号1", "M1", "a,b,c"),
            AliasRow("多逗号2", "M2", "x, y, z"),
        ])
        AliasRepository.clear_cache()
        rows = {r.alias: r for r in AliasRepository.get_all()}
        assert rows["多逗号1"].notes == "a,b,c"
        assert rows["多逗号2"].notes == "x, y, z"


def _get_cache_fingerprint() -> int | None:
    """返回当前 _cache 的 file_mtime 值。"""
    return _cache.file_mtime
