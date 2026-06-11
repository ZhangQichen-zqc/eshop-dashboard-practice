"""数据读取层

支持三种数据源，按优先级自动降级：
  1. ETL API  — 远程/容器化部署（教学标准模式）
  2. SQLite   — 本地直连（降级方案）
  3. CSV      — 离线备份

使用方式：
  - 设置环境变量 DATA_SOURCE_MODE=etl  (默认) 强制使用 ETL API
  - 设置环境变量 DATA_SOURCE_MODE=sqlite 使用 SQLite 直连
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
# 启动时打印数据源信息
# ============================================================
logger.info(f"数据源模式: {DATA_SOURCE_MODE.upper()}")
if DATA_SOURCE_MODE == "etl":
    logger.info(f"ETL API 地址: {ETL_API_BASE_URL}")
else:
    logger.info(f"SQLite 路径: {SQLITE_DB_PATH}")


# ============================================================
# SQLite 模式（保留作为降级和复杂查询使用）
# ============================================================

def get_db_connection(readonly: bool = True) -> sqlite3.Connection:
    """获取 SQLite 只读连接。

    注意：当 DATA_SOURCE_MODE='etl' 时，简单表读取应通过 ETL API，
    此方法仅在需要复杂 JOIN/聚合查询时作为降级使用。

    Args:
        readonly: 是否只读（默认 True，用于分析查询）。
    """
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
# ETL API 模式
# ============================================================

class ETLClient:
    """ETL API 客户端，封装 HTTP 请求、重试、降级。

    通过商城后端 (port 38173) 的 /api/etl/* 只读接口获取数据。
    """

    def __init__(self, base_url: str = ETL_API_BASE_URL, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._available = None  # None=未检测, True=可用, False=不可用

    def _request(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求，带重试。自动绕过本地代理。"""
        url = f"{self.base_url}{path}"
        last_error = None

        # 确保本地 ETL API 不经过代理
        proxies = {"http": None, "https": None} if "127.0.0.1" in url or "localhost" in url else None

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout, proxies=proxies)
                resp.raise_for_status()
                self._available = True
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_error = e
                self._available = False
                logger.warning(f"ETL API 连接失败 (attempt {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(1)
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"ETL API 超时 (attempt {attempt+1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
            except Exception as e:
                last_error = e
                break

        raise ConnectionError(f"ETL API 不可用: {last_error}")

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
        """获取所有可用表。"""
        return self._request("/tables")

    def get_schema(self, table: str) -> dict:
        """获取表结构。"""
        return self._request(f"/schema/{table}")

    def query(self, table: str, limit: int = 100, offset: int = 0,
              order_by: str = None, order_dir: str = "asc",
              filters: dict = None) -> pd.DataFrame:
        """通过 ETL API 分页查询表数据。

        Args:
            table: 表名
            limit: 返回行数上限
            offset: 偏移量
            order_by: 排序字段
            order_dir: 排序方向 (asc/desc)
            filters: 等值过滤条件 {字段: 值}
        """
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if order_by:
            params["orderBy"] = order_by
            params["orderDir"] = order_dir
        if filters:
            params.update(filters)

        result = self._request(f"/query/{table}", params)
        # ETL API 返回 {"tableName":..., "rows": [...], "total":...}
        rows = result.get("rows", [])
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def fetch_all(self, table: str, batch_size: int = 5000,
                  filters: dict = None) -> pd.DataFrame:
        """分批获取表的全部数据。

        Args:
            table: 表名
            batch_size: 每批行数（最大 5000）
            filters: 等值过滤条件
        """
        # 先获取第一页，确定总数
        first_params: Dict[str, Any] = {"limit": batch_size, "offset": 0}
        if filters:
            first_params.update(filters)

        result = self._request(f"/query/{table}", first_params)
        total = result.get("total", 0)
        rows = result.get("rows", [])

        if total <= batch_size:
            return pd.DataFrame(rows) if rows else pd.DataFrame()

        # 分批获取剩余数据
        all_rows = list(rows)
        for offset_val in range(batch_size, total, batch_size):
            params: Dict[str, Any] = {"limit": batch_size, "offset": offset_val}
            if filters:
                params.update(filters)
            batch_result = self._request(f"/query/{table}", params)
            batch_rows = batch_result.get("rows", [])
            all_rows.extend(batch_rows)
            logger.debug(f"  ETL fetch {table}: {offset_val + len(batch_rows)}/{total}")

        logger.info(f"ETL 全量获取 {table}: {len(all_rows):,} 行")
        return pd.DataFrame(all_rows)

    def get_metrics(self) -> dict:
        """通过 ETL API 获取核心经营指标。"""
        result = self._request("/metrics")
        # ETL API 返回 {"metrics": {...}}
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
        """通过 ETL API 获取数据质量报告。"""
        return self._request("/quality")


# ============================================================
# 统一数据获取层：根据 DATA_SOURCE_MODE 路由
# ============================================================

def _use_etl() -> bool:
    """判断当前是否应使用 ETL API 模式。"""
    if DATA_SOURCE_MODE != "etl":
        return False
    try:
        client = ETLClient()
        return client.is_available()
    except Exception:
        logger.warning("ETL API 不可用，降级到 SQLite 直连")
        return False


def query_metrics() -> Dict[str, Any]:
    """查询核心经营指标。

    优先通过 ETL API，不可用时降级到 SQLite 直连。
    """
    if _use_etl():
        try:
            client = ETLClient()
            metrics = client.get_metrics()
            logger.info(f"✓ 指标来源: ETL API | GMV: ¥{metrics['gmv']:,.0f}")
            return metrics
        except Exception as e:
            logger.warning(f"ETL metrics 获取失败: {e}，降级到 SQLite")

    # SQLite 降级
    logger.info("✓ 指标来源: SQLite 直连（降级）")
    conn = get_db_connection()
    try:
        gmv = float(pd.read_sql(
            "SELECT COALESCE(SUM(paid_amount), 0) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0]) or 0.0

        refund = float(pd.read_sql(
            "SELECT COALESCE(SUM(amount), 0) FROM fact_refund WHERE status='approved'",
            conn
        ).iloc[0, 0]) or 0.0

        gross_profit = float(pd.read_sql("""
            SELECT COALESCE(SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount), 0)
            FROM fact_order_item oi
            JOIN fact_order o ON oi.order_id = o.order_id
            WHERE o.status IN ('paid','completed')
        """, conn).iloc[0, 0]) or 0.0

        order_count = int(pd.read_sql(
            "SELECT COUNT(DISTINCT order_id) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0])

        buyer_count = int(pd.read_sql(
            "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0])

        return {
            "gmv": round(gmv, 2),
            "net_sales": round(gmv - refund, 2),
            "refund_amount": round(refund, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin": round(gross_profit / gmv * 100, 2) if gmv else 0,
            "order_count": order_count,
            "buyer_count": buyer_count,
            "aov": round(gmv / order_count, 2) if order_count else 0,
        }
    finally:
        conn.close()


# ============================================================
# 维度表加载（ETL API 优先，SQLite 降级）
# ============================================================

def _etl_fetch_table(table_name: str) -> pd.DataFrame:
    """通过 ETL API 获取表的全部数据。"""
    client = ETLClient()
    return client.fetch_all(table_name)


def _sqlite_fetch_table(table_name: str) -> pd.DataFrame:
    """通过 SQLite 直接读取表。"""
    conn = get_db_connection()
    try:
        return pd.read_sql(f'SELECT * FROM "{table_name}"', conn)
    finally:
        conn.close()


def _load_table(table_name: str) -> pd.DataFrame:
    """统一表加载：ETL 优先，SQLite 降级。"""
    if _use_etl():
        try:
            df = _etl_fetch_table(table_name)
            logger.debug(f"  ETL ← {table_name}: {len(df):,} 行")
            return df
        except Exception as e:
            logger.warning(f"ETL 获取 {table_name} 失败: {e}，降级到 SQLite")

    df = _sqlite_fetch_table(table_name)
    logger.debug(f"  SQLite ← {table_name}: {len(df):,} 行")
    return df


def load_dim_user() -> pd.DataFrame:
    return _load_table("dim_user")

def load_dim_product() -> pd.DataFrame:
    return _load_table("dim_product")

def load_dim_date() -> pd.DataFrame:
    return _load_table("dim_date")

def load_dim_campaign() -> pd.DataFrame:
    return _load_table("dim_campaign")


# ============================================================
# 事实表加载（ETL API 优先，SQLite 降级）
# ============================================================

def load_fact_order(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channels: Optional[List[str]] = None,
) -> pd.DataFrame:
    """加载订单事实表。

    注意：当使用 ETL API 时，会全量拉取后在 pandas 中过滤。
    SQLite 模式下使用 SQL 下推过滤。
    """
    if _use_etl():
        try:
            df = _etl_fetch_table("fact_order")
            # pandas 端过滤
            if start_date:
                df = df[df["order_date"] >= start_date]
            if end_date:
                df = df[df["order_date"] <= end_date]
            if channels:
                df = df[df["channel"].isin(channels)]
            logger.debug(f"  ETL ← fact_order (filtered): {len(df):,} 行")
            return df
        except Exception as e:
            logger.warning(f"ETL 获取 fact_order 失败: {e}，降级到 SQLite")

    # SQLite 降级
    conn = get_db_connection()
    try:
        sql = "SELECT * FROM fact_order WHERE 1=1"
        params = []
        if start_date:
            sql += " AND order_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND order_date <= ?"
            params.append(end_date)
        if channels:
            placeholders = ",".join(["?"] * len(channels))
            sql += f" AND channel IN ({placeholders})"
            params.extend(channels)
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def load_fact_order_item(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """加载订单行事实表。"""
    if _use_etl():
        try:
            df = _etl_fetch_table("fact_order_item")
            if start_date:
                df = df[df["order_date"] >= start_date]
            if end_date:
                df = df[df["order_date"] <= end_date]
            return df
        except Exception as e:
            logger.warning(f"ETL 获取 fact_order_item 失败: {e}，降级到 SQLite")

    conn = get_db_connection()
    try:
        sql = "SELECT * FROM fact_order_item WHERE 1=1"
        params = []
        if start_date:
            sql += " AND order_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND order_date <= ?"
            params.append(end_date)
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def load_fact_traffic(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channels: Optional[List[str]] = None,
) -> pd.DataFrame:
    """加载流量事实表。"""
    if _use_etl():
        try:
            df = _etl_fetch_table("fact_traffic")
            if start_date:
                df = df[df["event_date"] >= start_date]
            if end_date:
                df = df[df["event_date"] <= end_date]
            if channels:
                df = df[df["channel"].isin(channels)]
            return df
        except Exception as e:
            logger.warning(f"ETL 获取 fact_traffic 失败: {e}，降级到 SQLite")

    conn = get_db_connection()
    try:
        sql = "SELECT * FROM fact_traffic WHERE 1=1"
        params = []
        if start_date:
            sql += " AND event_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND event_date <= ?"
            params.append(end_date)
        if channels:
            placeholders = ",".join(["?"] * len(channels))
            sql += f" AND channel IN ({placeholders})"
            params.extend(channels)
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
