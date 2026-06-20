"""stock_alias.csv CSV 转义回归测试。"""
from __future__ import annotations

import csv
from pathlib import Path

from src.interfaces.handlers_data import _handle_asset_alias
from src.interfaces.routers import pipeline


def _write_alias_file(path: Path) -> None:
    path.write_text(
        "# comment\n"
        "NVIDIA,NVDA,显卡\n"
        'CommaAlias,CMA,"old, note"\n'
        'SkipMe,SKP,"alpha, beta"\n',
        encoding="utf-8",
    )


def _rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return [row for row in csv.reader(f) if row and not row[0].startswith("#")]


def test_handle_asset_alias_add_escapes_comma_note(tmp_path: Path, monkeypatch) -> None:
    alias_path = tmp_path / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.setattr("src.storage.alias_repository._PATH", alias_path)

    result = _handle_asset_alias({
        "action": "add",
        "alias": "NewAlias",
        "ticker": "NEW",
        "notes": "Q1, 2024",
    })

    assert result == {"ok": True}
    rows = {row[0]: row for row in _rows(alias_path)}
    assert rows["NewAlias"] == ["NewAlias", "NEW", "Q1, 2024"]


def test_handle_asset_alias_edit_escapes_comma_and_quote_note(tmp_path: Path, monkeypatch) -> None:
    alias_path = tmp_path / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.setattr("src.storage.alias_repository._PATH", alias_path)

    result = _handle_asset_alias({
        "action": "edit",
        "old_alias": "CommaAlias",
        "alias": "CommaAlias",
        "ticker": "CMA",
        "notes": '他说"Q1, ok"',
    })

    assert result == {"ok": True}
    rows = {row[0]: row for row in _rows(alias_path)}
    assert rows["CommaAlias"] == ["CommaAlias", "CMA", '他说"Q1, ok"']


def test_handle_asset_alias_skip_unskip_preserves_comma_note(tmp_path: Path, monkeypatch) -> None:
    alias_path = tmp_path / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.setattr("src.storage.alias_repository._PATH", alias_path)

    assert _handle_asset_alias({"action": "skip", "alias": "SkipMe"}) == {"ok": True}
    rows = {row[0]: row for row in _rows(alias_path)}
    assert rows["SkipMe"] == ["SkipMe", "SKP", "SKIP|alpha, beta"]

    assert _handle_asset_alias({"action": "unskip", "alias": "SkipMe"}) == {"ok": True}
    rows = {row[0]: row for row in _rows(alias_path)}
    assert rows["SkipMe"] == ["SkipMe", "SKP", "alpha, beta"]


def test_handle_asset_alias_delete_matches_alias_with_comma_note(tmp_path: Path, monkeypatch) -> None:
    alias_path = tmp_path / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.setattr("src.storage.alias_repository._PATH", alias_path)

    assert _handle_asset_alias({"action": "delete", "alias": "CommaAlias"}) == {"ok": True}
    rows = {row[0]: row for row in _rows(alias_path)}
    assert "CommaAlias" not in rows
    assert rows["SkipMe"] == ["SkipMe", "SKP", "alpha, beta"]


def test_pipeline_alias_helpers_read_csv_fields_with_commas(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    alias_path = data_dir / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.chdir(tmp_path)

    pipeline._save_alias("CommaAlias", "OTHER", "dup should not append")
    assert [row[0] for row in _rows(alias_path)].count("CommaAlias") == 1
    assert "COMMAALIAS" in pipeline._load_skip_set()
    assert pipeline._is_known_stock_ticker("CMA") is False
    assert pipeline._is_known_stock_ticker("SKP") is False


def test_pipeline_save_alias_escapes_note_with_comma(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    alias_path = data_dir / "stock_alias.csv"
    _write_alias_file(alias_path)
    monkeypatch.chdir(tmp_path)

    pipeline._save_alias("Fresh", "FRSH", "manual, correction")

    rows = {row[0]: row for row in _rows(alias_path)}
    assert rows["Fresh"] == ["Fresh", "FRSH", "manual, correction"]
