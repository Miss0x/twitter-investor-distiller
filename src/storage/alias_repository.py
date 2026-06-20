"""资产别名映射存储 — Repository 模式统一封装 stock_alias.csv。

CSV 格式: alias,ticker,notes（无表头，# 开头为注释）
	- ticker 非空 → 已确认映射
	- ticker 为空 + notes 含 SKIP → 已跳过
	- ticker 为空 + notes 不含 SKIP → 待人工判断

设计:
	- 类式 Repository 与 ``src/governance/repository.py`` 风格统一
	- 模块级单例 ``repo = AliasRepository()``
	- 三个独立缓存 (all/map/skip_set) + mtime 检测保证一致性
	- 写操作 (add/add_many) 自动触发缓存失效 (Write-Through 模式)
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import NamedTuple


class AliasRow(NamedTuple):
	alias: str
	ticker: str
	notes: str


_PATH = Path("data/stock_alias.csv")


class _Cache:
	"""模块级缓存状态。"""

	def __init__(self) -> None:
		self.all: list[AliasRow] | None = None
		self.map: dict[str, str] | None = None
		self.skip_set: set[str] | None = None
		self.file_mtime: int | None = None

	def is_fresh(self) -> bool:
		"""检查文件指纹是否变化（双因子：mtime + size）。"""
		if not _PATH.exists():
			return self.all == [] and self.map == {} and self.skip_set == set()
		current = _get_mtime()
		return current is not None and self.file_mtime == current

	def invalidate(self) -> None:
		self.all = None
		self.map = None
		self.skip_set = None
		self.file_mtime = None


_cache = _Cache()


def _rows_from_csv() -> list[AliasRow]:
	"""统一的 CSV 解析函数。被三个 get 方法共用。"""
	if not _PATH.exists():
		return []
	result: list[AliasRow] = []
	try:
		reader = csv.reader(_PATH.read_text(encoding="utf-8").splitlines())
		for row in reader:
			if not row or not row[0] or row[0].startswith("#"):
				continue
			result.append(AliasRow(
				alias=row[0].strip(),
				ticker=row[1].strip() if len(row) >= 2 else "",
				notes=row[2].strip() if len(row) >= 3 else "",
			))
	except Exception:
		pass
	return result


def _get_mtime() -> int | None:
	"""获取文件 mtime + size 双因子指纹（跨平台兼容）。

	Windows 上 ``copy /b`` 不更新 mtime，但 size 必然变化。
	组合 `hash((mtime, size))` 比单 mtime 更可靠。
	"""
	try:
		if not _PATH.exists():
			return None
		stat = _PATH.stat()
		return hash((stat.st_mtime, stat.st_size))
	except Exception:
		return None


class AliasRepository:
	"""资产别名映射的数据访问封装。"""

	@staticmethod
	def get_all() -> list[AliasRow]:
		"""返回全部别名记录 ``[AliasRow(alias, ticker, notes), ...]``（带缓存）。"""
		if _cache.is_fresh() and _cache.all is not None:
			return _cache.all
		_cache.all = _rows_from_csv()
		_cache.file_mtime = _get_mtime()
		return _cache.all

	@staticmethod
	def get_map() -> dict[str, str]:
		"""返回 ``{alias: ticker}`` 字典（仅已确认映射，带缓存）。"""
		if _cache.is_fresh() and _cache.map is not None:
			return _cache.map
		result: dict[str, str] = {}
		for r in _rows_from_csv():
			if r.ticker:
				result[r.alias] = r.ticker
		_cache.map = result
		_cache.file_mtime = _get_mtime()
		return _cache.map

	@staticmethod
	def get_skip_set() -> set[str]:
		"""返回已跳过别名的集合（大写，带缓存）。"""
		if _cache.is_fresh() and _cache.skip_set is not None:
			return _cache.skip_set
		result: set[str] = set()
		for r in _rows_from_csv():
			if r.ticker or r.notes.startswith("SKIP"):
				result.add(r.alias.upper())
		_cache.skip_set = result
		_cache.file_mtime = _get_mtime()
		return _cache.skip_set

	@staticmethod
	def is_known_ticker(ticker: str) -> bool:
		"""判断 ticker 是否已在已确认映射表中有对应关系（大小写不敏感）。"""
		if not ticker or len(ticker) > 5:
			return False
		m = AliasRepository.get_map()
		upper_t = ticker.upper()
		return any(v.upper() == upper_t for v in m.values()) or upper_t in m

	@staticmethod
	def add(alias: str, ticker: str = "", note: str = "") -> None:
		"""追加一条别名映射（自动去重 + 写后失效缓存）。"""
		alias = alias.strip()
		if not alias:
			return
		existing = AliasRepository.get_map()
		if alias in existing:
			return
		with _PATH.open("a", encoding="utf-8", newline="") as f:
			writer = csv.writer(f)
			writer.writerow([alias, ticker, note])
		_cache.invalidate()

	@staticmethod
	def add_many(rows: list[AliasRow] | list[dict]) -> int:
		"""批量追加别名映射，返回实际新增数量。

		Args:
			rows: 每项可以是 AliasRow 或 ``{"alias", "ticker", "notes"}`` 字典
		Returns:
			实际写入的行数（去重后）
		"""
		existing = AliasRepository.get_map()
		new_rows: list[AliasRow] = []
		for row in rows:
			if isinstance(row, dict):
				r = AliasRow(
					alias=row.get("alias", ""),
					ticker=row.get("ticker", ""),
					notes=row.get("notes", ""),
				)
			else:
				r = row
			if r.alias.strip() and r.alias not in existing:
				new_rows.append(r)
				existing[r.alias] = r.ticker

		if not new_rows:
			return 0
		with _PATH.open("a", encoding="utf-8", newline="") as f:
			writer = csv.writer(f)
			for r in new_rows:
				writer.writerow([r.alias, r.ticker, r.notes])
		_cache.invalidate()
		return len(new_rows)

	@staticmethod
	def clear_cache() -> None:
		"""清理内部缓存（数据变更后调用）。"""
		_cache.invalidate()


# 模块级单例（与 GovernanceRepository 的使用方式一致）
repo = AliasRepository()
