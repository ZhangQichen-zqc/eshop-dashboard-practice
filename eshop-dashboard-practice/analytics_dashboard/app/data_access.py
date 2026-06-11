"""数据读取层

支持三种数据源，按优先级自动降级：
  1. ETL API  — 远程/容器化部署
  2. SQLite   — 本地直连（默认/生产）
  3. CSV      — 离线备份
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .config import SQLITE_DB_PATH, ETL_API_BASE_URL, CACHE_TTL_SECONDS

logger = logging.getLogger("analytics.data_access")

# ============================================================
# SQLite 模式
# ============================================================

def get_db_connection(readonly: bool = True) -> sqlite3.Connection:
    """获取 SQLite 只读连接。

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
    """分页查询表数据。

    Args:
        table_name: 表名或视图名
        limit: 返回行数上限
        offset: 偏移量
        order_by: 排序字段
        filters: 等值过滤条件 {列名: 值}
    """
    conn = get_db_connection()
    try:
        # 安全校验：表名只允许字母数字下划线
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


def query_metrics() -> Dict[str, Any]:
    """查询核心经营指标。"""
    conn = get_db_connection()
    try:
        gmv = pd.read_sql(
            "SELECT SUM(paid_amount) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0] or 0

        refund = pd.read_sql(
            "SELECT SUM(amount) FROM fact_refund WHERE status='approved'",
            conn
        ).iloc[0, 0] or 0

        gross_profit = pd.read_sql("""
            SELECT SUM((oi.unit_price - oi.unit_cost) * oi.quantity - oi.discount_amount)
            FROM fact_order_item oi
            JOIN fact_order o ON oi.order_id = o.order_id
            WHERE o.status IN ('paid','completed')
        """, conn).iloc[0, 0] or 0

        order_count = pd.read_sql(
            "SELECT COUNT(DISTINCT order_id) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0]

        buyer_count = pd.read_sql(
            "SELECT COUNT(DISTINCT user_id) FROM fact_order WHERE status IN ('paid','completed')",
            conn
        ).iloc[0, 0]

        return {
            "gmv": round(float(gmv), 2),
            "net_sales": round(float(gmv - refund), 2),
            "refund_amount": round(float(refund), 2),
            "gross_profit": round(float(gross_profit), 2),
            "gross_margin": round(float(gross_profit) / float(gmv) * 100, 2) if gmv else 0,
            "order_count": int(order_count),
            "buyer_count": int(buyer_count),
            "aov": round(float(gmv) / int(order_count), 2) if order_count else 0,
        }
    finally:
        conn.close()


def query_quality_report() -> List[Dict]:
    """执行数据质量检查。"""
    conn = get_db_connection()
    checks = []
    try:
        # 行数检查
        for table, expected in [("dim_user", 20000), ("fact_order", 100000), ("fact_traffic", 700000)]:
            actual = int(pd.read_sql(f'SELECT COUNT(*) FROM "{table}"', conn).iloc[0, 0])
            checks.append({
                "category": "完整性",
                "name": f"{table} 行数",
                "status": "pass" if abs(actual - expected) / expected < 0.3 else "warn",
                "detail": f"实际 {actual:,} 行，预期约 {expected:,} 行",
                "metrics": {"actual": actual, "expected": expected},
            })

        # 金额检查
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
    """查询经营日报数据。"""
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


# 维度表加载函数
def load_dim_user() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM dim_user", conn)
    finally:
        conn.close()

def load_dim_product() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM dim_product", conn)
    finally:
        conn.close()

def load_dim_date() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM dim_date", conn)
    finally:
        conn.close()

def load_dim_campaign() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM dim_campaign", conn)
    finally:
        conn.close()

# 事实表加载函数
def load_fact_order(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    channels: Optional[List[str]] = None,
) -> pd.DataFrame:
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
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_coupon_use", conn)
    finally:
        conn.close()

def load_fact_refund() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_refund", conn)
    finally:
        conn.close()

def load_fact_fulfillment() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_fulfillment", conn)
    finally:
        conn.close()

def load_fact_inventory_movement() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_inventory_movement", conn)
    finally:
        conn.close()

def load_fact_product_review() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_product_review", conn)
    finally:
        conn.close()

def load_fact_ads_spend() -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql("SELECT * FROM fact_ads_spend", conn)
    finally:
        conn.close()


# ============================================================
# ETL API 模式
# ============================================================

class ETLClient:
    """ETL API 客户端，封装 HTTP 请求、重试、降级。"""

    def __init__(self, base_url: str = ETL_API_BASE_URL, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._available = None  # None=未检测, True=可用, False=不可用

    def _request(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求，带重试。"""
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                self._available = True
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_error = e
                self._available = False
                logger.warning(f"ETL API 连接失败 (attempt {attempt+1}/{self.max_retries})")
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
        return self._request("/tables")

    def get_schema(self, table: str) -> dict:
        return self._request(f"/schema/{table}")

    def query(self, table: str, limit: int = 100, offset: int = 0) -> pd.DataFrame:
        result = self._request(f"/query/{table}", {"limit": limit, "offset": offset})
        return pd.DataFrame(result.get("data", []))

    def export_csv(self, table: str, save_path: str) -> str:
        resp = requests.get(f"{self.base_url}/export/{table}?format=csv", timeout=self.timeout)
        resp.raise_for_status()
        Path(save_path).write_bytes(resp.content)
        return save_path

    def get_metrics(self) -> dict:
        return self._request("/metrics")

    def get_quality(self) -> dict:
        return self._request("/quality")


# ============================================================
# CSV 模式
# ============================================================

_CSV_CACHE: Dict[str, pd.DataFrame] = {}

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "exports"


def load_csv_table(table_name: str) -> pd.DataFrame:
    """从 exports/ 目录读取 CSV 文件（带内存缓存）。

    Args:
        table_name: 不含 .csv 扩展名的文件名。
    """
    if table_name in _CSV_CACHE:
        return _CSV_CACHE[table_name].copy()

    csv_path = EXPORTS_DIR / f"{table_name}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    df = pd.read_csv(csv_path)

    # 自动推断日期列
    for col in df.columns:
        if "date" in col.lower() or "time" in col.lower():
            try:
                df[col] = pd.to_datetime(df[col])
            except Exception:
                pass

    _CSV_CACHE[table_name] = df
    return df.copy()


# ============================================================
# 降级链：ETL API → SQLite → CSV
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

    # 2. 尝试 SQLite（默认）
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
