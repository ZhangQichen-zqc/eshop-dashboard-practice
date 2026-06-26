"""数据读取层

严格模式：
  - DATA_SOURCE_MODE=etl  (默认): 强制使用 ETL API，不可用则启动失败
  - DATA_SOURCE_MODE=sqlite: 直接 SQLite 直连（无需启动商城）

使用方式：
  - 先启动商城: npm run start:mall-api  (端口 38173)
  - 再启动仪表盘: python -m uvicorn app.main:app
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .config import (
    SQLITE_DB_PATH,
    ETL_API_BASE_URL,
    CACHE_TTL_SECONDS,
    DATA_SOURCE_MODE,
)

logger = logging.getLogger("analytics.data_access")

# ============================================================
# ETL API 客户端（模块级，先定义以便后续使用）
# ============================================================

class ETLClient:
    """ETL API 客户端，封装 HTTP 请求、重试。

    通过商城后端 (port 38173) 的 /api/etl/* 只读接口获取数据。
    """

    def __init__(self, base_url: str = ETL_API_BASE_URL, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._available = None  # None=未检测, True=可用, False=不可用

    def _request(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求，带重试。"""
        url = f"{self.base_url}{path}"
        last_error = None
        proxies = {"http": None, "https": None}

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout, proxies=proxies)
                resp.raise_for_status()
                self._available = True
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_error = e
                self._available = False
                if attempt < self.max_retries - 1:
                    time.sleep(1)
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                last_error = e
                break

        raise ConnectionError(f"ETL API 不可用 ({self.base_url}): {last_error}")

    def is_available(self) -> bool:
        """检测 ETL API 是否可用。"""
        if self._available is not None:
            return self._available
        try:
            self._request("/help")
            return True
        except Exception:
            return False

    def get_tables(self) -> dict:
        return self._request("/tables")

    def get_schema(self, table: str) -> dict:
        return self._request(f"/schema/{table}")

    def get_metrics(self) -> dict:
        """通过 ETL API 获取核心经营指标。"""
        result = self._request("/metrics")
        raw = result.get("metrics", result)
        return {
            "gmv": raw["gmv"]["value"],
            "net_sales": raw["netSales"]["value"],
            "refund_amount": round(raw["gmv"]["value"] - raw["netSales"]["value"], 2),
            "gross_profit": raw["grossProfit"]["value"],
            "gross_margin": round(
                raw["grossProfit"]["value"] / raw["gmv"]["value"] * 100, 2
            ) if raw["gmv"]["value"] else 0,
            "order_count": raw["orderCount"]["value"],
            "buyer_count": raw["buyerCount"]["value"],
            "aov": raw["avgOrderValue"]["value"],
        }

    def get_quality(self) -> dict:
        return self._request("/quality")

    def query(self, table: str, limit: int = 100, offset: int = 0,
              order_by: str = None, order_dir: str = "asc",
              filters: dict = None) -> pd.DataFrame:
        """通过 ETL API 分页查询表数据。"""
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if order_by:
            params["orderBy"] = order_by
            params["orderDir"] = order_dir
        if filters:
            params.update(filters)

        result = self._request(f"/query/{table}", params)
        rows = result.get("rows", result.get("data", []))
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def fetch_all(self, table: str, batch_size: int = 5000,
                  filters: dict = None) -> pd.DataFrame:
        """分批获取表的全部数据。"""
        first_params: Dict[str, Any] = {"limit": batch_size, "offset": 0}
        if filters:
            first_params.update(filters)

        result = self._request(f"/query/{table}", first_params)
        total = result.get("total", 0)
        rows = result.get("rows", result.get("data", []))

        if total <= batch_size or not rows:
            return pd.DataFrame(rows) if rows else pd.DataFrame()

        all_rows = list(rows)
        for offset_val in range(batch_size, total, batch_size):
            params: Dict[str, Any] = {"limit": batch_size, "offset": offset_val}
            if filters:
                params.update(filters)
            batch_result = self._request(f"/query/{table}", params)
            batch_rows = batch_result.get("rows", batch_result.get("data", []))
            all_rows.extend(batch_rows)

        logger.info(f"ETL 全量获取 {table}: {len(all_rows):,} 行")
        return pd.DataFrame(all_rows)


# ============================================================
# 启动时强制检查 ETL API
# ============================================================
logger.info(f"数据源模式: {DATA_SOURCE_MODE.upper()}")

if DATA_SOURCE_MODE == "etl":
    _check_client = ETLClient()
    if not _check_client.is_available():
        raise ConnectionError(
            f"\n{'='*60}\n"
            f"❌ ETL API 不可用 ({ETL_API_BASE_URL})\n"
            f"   请先启动商城 API:\n"
            f"     cd eshop-dashboard-practice && npm run start:mall-api\n"
            f"   或切换到 SQLite 模式:\n"
            f"     export DATA_SOURCE_MODE=sqlite\n"
            f"{'='*60}"
        )
    logger.info(f"✅ ETL API 已连接: {ETL_API_BASE_URL}")
    _etl_client = _check_client  # 复用已验证的客户端
else:
    logger.info(f"✅ SQLite 直连: {SQLITE_DB_PATH}")
    _etl_client = None


# ============================================================
# SQLite 模式（仅供 DATA_SOURCE_MODE='sqlite' 时使用）
# ============================================================

def get_db_connection(readonly: bool = True) -> sqlite3.Connection:
    """获取 SQLite 连接。

    ETL 模式下：用于复杂分析查询的计算引擎（表数据已通过 ETL API 获取）。
    SQLite 模式下：直接连接本地数据库。
    """
    if DATA_SOURCE_MODE == "etl":
        logger.debug("ETL 模式：使用 SQLite 作为复杂分析计算引擎")

    db_path = SQLITE_DB_PATH
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite 数据库不存在: {db_path}")

    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def query_table(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    order_by: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """分页查询表数据（SQLite 模式）。

    Args:
        table_name: 表名或视图名
        limit: 返回行数上限
        offset: 偏移量
        order_by: 排序字段
        filters: 等值过滤条件 {列名: 值}
    """
    conn = get_db_connection()
    try:
        if not table_name.replace("_", "").isalnum():
            raise ValueError(f"非法表名: {table_name}")

        sql = f'SELECT * FROM "{table_name}"'
        params = []

        if filters:
            clauses = [f'"{k}" = ?' for k in filters]
            sql += " WHERE " + " AND ".join(clauses)
            params = list(filters.values())

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit:
            sql += f" LIMIT {int(limit)}"
        if offset:
            sql += f" OFFSET {int(offset)}"

        return pd.read_sql(sql, conn, params=params or None)
    finally:
        conn.close()


def query_table_schema(table_name: str) -> pd.DataFrame:
    """查询表结构（列名、类型、是否可空）。"""
    conn = get_db_connection()
    try:
        return pd.read_sql(f'PRAGMA table_info("{table_name}")', conn)
    finally:
        conn.close()


def query_quality_report() -> List[Dict]:
    """执行数据质量检查（SQLite 模式）。"""
    conn = get_db_connection()
    checks = []
    try:
        for table, expected in [("dim_user", 20000), ("fact_order", 100000), ("fact_traffic", 700000)]:
            actual = int(pd.read_sql(f'SELECT COUNT(*) FROM "{table}"', conn).iloc[0, 0])
            checks.append({
                "category": "完整性",
                "name": f"{table} 行数",
                "status": "pass" if abs(actual - expected) / expected < 0.3 else "warn",
                "detail": f"实际 {actual:,} 行，预期约 {expected:,} 行",
                "metrics": {"actual": actual, "expected": expected},
            })

        neg = int(pd.read_sql(
            "SELECT COUNT(*) FROM fact_order WHERE paid_amount < 0", conn
        ).iloc[0, 0])
        checks.append({
            "category": "准确性",
            "name": "paid_amount 负数",
            "status": "pass" if neg == 0 else "fail",
            "detail": f"发现 {neg} 条负数",
            "metrics": {"negative_count": neg},
        })

        return checks
    finally:
        conn.close()


def query_daily_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channels: Optional[List[str]] = None,
) -> pd.DataFrame:
    """查询经营日报数据（SQLite 模式）。"""
    conn = get_db_connection()
    try:
        sql = "SELECT * FROM daily_business_summary WHERE 1=1"
        params = []
        if start_date:
            sql += " AND summary_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND summary_date <= ?"
            params.append(end_date)
        if channels:
            placeholders = ",".join(["?"] * len(channels))
            sql += f" AND channel IN ({placeholders})"
            params.extend(channels)
        sql += " ORDER BY summary_date, channel"
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


# ============================================================
# 统一数据获取层
# ============================================================

def _use_etl() -> bool:
    """判断当前是否为 ETL 模式。启动时已验证 API 可用。"""
    return DATA_SOURCE_MODE == "etl"


def query_metrics() -> Dict[str, Any]:
    """查询核心经营指标（ETL 模式从 API 获取，SQLite 模式直连）。"""
    if _use_etl():
        metrics = _etl_client.get_metrics()
        logger.info(f"✓ 指标来源: ETL API | GMV: ¥{metrics['gmv']:,.0f}")
        return metrics

    logger.info("✓ 指标来源: SQLite 直连")
    conn = get_db_connection()
    try:
        gmv = float(pd.read_sql(
            "SELECT COALESCE(SUM(paid_amount), 0) FROM fact_order WHERE status IN ('paid','completed')", conn
        ).iloc[0, 0]) or 0.0
        refund = float(pd.read_sql(
            "SELECT COALESCE(SUM(amount), 0) FROM fact_refund WHERE status='approved'", conn
        ).iloc[0, 0]) or 0.0
        gross_profit = float(pd.read_sql("""
            SELECT COALESCE(SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount), 0)
            FROM fact_order_item oi JOIN fact_order o ON oi.order_id = o.order_id
            WHERE o.status IN ('paid','completed')
        """, conn).iloc[0, 0]) or 0.0
        order_count = int(pd.read_sql(
            "SELECT COUNT(DISTINCT order_id) FROM fact_order WHERE status IN ('paid','completed')", conn
        ).iloc[0, 0])
        buyer_count = int(pd.read_sql(
            "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE status IN ('paid','completed')", conn
        ).iloc[0, 0])
        return {
            "gmv": round(gmv, 2), "net_sales": round(gmv - refund, 2),
            "refund_amount": round(refund, 2), "gross_profit": round(gross_profit, 2),
            "gross_margin": round(gross_profit / gmv * 100, 2) if gmv else 0,
            "order_count": order_count, "buyer_count": buyer_count,
            "aov": round(gmv / order_count, 2) if order_count else 0,
        }
    finally:
        conn.close()


# ============================================================
# 维度表加载（严格 ETL，无降级）
# ============================================================

def _load_table(table_name: str) -> pd.DataFrame:
    """加载表数据：ETL 模式从 API 获取，SQLite 模式直连。"""
    if _use_etl():
        df = _etl_client.fetch_all(table_name)
        logger.debug(f"  ETL ← {table_name}: {len(df):,} 行")
        return df

    conn = get_db_connection()
    try:
        df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
        logger.debug(f"  SQLite ← {table_name}: {len(df):,} 行")
        return df
    finally:
        conn.close()


def load_dim_user() -> pd.DataFrame:
    return _load_table("dim_user")

def load_dim_product() -> pd.DataFrame:
    return _load_table("dim_product")

def load_dim_date() -> pd.DataFrame:
    return _load_table("dim_date")

def load_dim_campaign() -> pd.DataFrame:
    return _load_table("dim_campaign")


# ============================================================
# 事实表加载（严格模式：ETL 走 API，SQLite 直连，无降级）
# ============================================================

def load_fact_order(start_date=None, end_date=None, channels=None) -> pd.DataFrame:
    """加载订单事实表。ETL 模式全量拉取后 pandas 过滤。"""
    if _use_etl():
        df = _etl_client.fetch_all("fact_order")
        if start_date:
            df = df[df["order_date"] >= start_date]
        if end_date:
            df = df[df["order_date"] <= end_date]
        if channels:
            df = df[df["channel"].isin(channels)]
        return df

    conn = get_db_connection()
    try:
        sql, params = "SELECT * FROM fact_order WHERE 1=1", []
        if start_date:
            sql += " AND order_date >= ?"; params.append(start_date)
        if end_date:
            sql += " AND order_date <= ?"; params.append(end_date)
        if channels:
            sql += f" AND channel IN ({','.join(['?']*len(channels))})"; params.extend(channels)
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def load_fact_order_item(start_date=None, end_date=None) -> pd.DataFrame:
    if _use_etl():
        df = _etl_client.fetch_all("fact_order_item")
        if start_date:
            df = df[df["order_date"] >= start_date]
        if end_date:
            df = df[df["order_date"] <= end_date]
        return df
    conn = get_db_connection()
    try:
        sql, params = "SELECT * FROM fact_order_item WHERE 1=1", []
        if start_date:
            sql += " AND order_date >= ?"; params.append(start_date)
        if end_date:
            sql += " AND order_date <= ?"; params.append(end_date)
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def load_fact_traffic(start_date=None, end_date=None, channels=None) -> pd.DataFrame:
    if _use_etl():
        df = _etl_client.fetch_all("fact_traffic")
        if start_date:
            df = df[df["event_date"] >= start_date]
        if end_date:
            df = df[df["event_date"] <= end_date]
        if channels:
            df = df[df["channel"].isin(channels)]
        return df
    conn = get_db_connection()
    try:
        sql, params = "SELECT * FROM fact_traffic WHERE 1=1", []
        if start_date:
            sql += " AND event_date >= ?"; params.append(start_date)
        if end_date:
            sql += " AND event_date <= ?"; params.append(end_date)
        if channels:
            sql += f" AND channel IN ({','.join(['?']*len(channels))})"; params.extend(channels)
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def load_fact_coupon_use() -> pd.DataFrame:
    return _load_table("fact_coupon_use")

def load_fact_refund() -> pd.DataFrame:
    return _load_table("fact_refund")

def load_fact_fulfillment() -> pd.DataFrame:
    return _load_table("fact_fulfillment")

def load_fact_inventory_movement() -> pd.DataFrame:
    return _load_table("fact_inventory_movement")

def load_fact_product_review() -> pd.DataFrame:
    return _load_table("fact_product_review")

def load_fact_ads_spend() -> pd.DataFrame:
    return _load_table("fact_ads_spend")


# ============================================================
# CSV 模式（离线备份）
# ============================================================

_CSV_CACHE: Dict[str, pd.DataFrame] = {}

EXPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "exports"


def load_csv_table(table_name: str) -> pd.DataFrame:
    """从 exports/ 目录读取 CSV 文件（带内存缓存）。"""
    if table_name in _CSV_CACHE:
        return _CSV_CACHE[table_name].copy()

    csv_path = EXPORTS_DIR / f"{table_name}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    df = pd.read_csv(csv_path)

    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower():
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass

    _CSV_CACHE[table_name] = df
    return df.copy()


# ============================================================
# 通用降级链：ETL API → SQLite → CSV
# ============================================================

def get_data(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    use_api: bool = True,
    use_csv: bool = False,
    **kwargs,
) -> pd.DataFrame:
    """统一数据获取入口，按优先级自动降级。

    优先级: ETL API → SQLite → CSV
    """
    # 1. 尝试 ETL API
    if use_api:
        try:
            client = ETLClient()
            if client.is_available():
                return client.query(table_name, limit=limit, offset=offset)
        except Exception as e:
            logger.info(f"ETL API 降级: {e}")

    # 2. 尝试 SQLite
    try:
        return query_table(table_name, limit=limit, offset=offset, **kwargs)
    except Exception as e:
        logger.info(f"SQLite 降级: {e}")

    # 3. 回退到 CSV
    if use_csv:
        df = load_csv_table(table_name)
        if offset:
            df = df.iloc[offset:]
        if limit:
            df = df.head(limit)
        return df

    raise RuntimeError(f"所有数据源均不可用，无法获取 {table_name}")
