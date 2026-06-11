"""工具函数模块

提供安全除法、格式化、统计、异常检测、缓存等通用工具。
"""

import json
import logging
import functools
import hashlib
import pickle
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# ============================================================
# 数值处理
# ============================================================

def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """安全除法，避免除零错误。"""
    if b is None or b == 0:
        return default
    return a / b


def format_money(value: float, currency: str = "¥") -> str:
    """金额格式化，如 ¥1,234,567.89"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return f"{currency}0.00"
    return f"{currency}{value:,.2f}"


def format_percent(value: float, decimals: int = 2) -> str:
    """百分比格式化，如 12.34%"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "0.00%"
    return f"{value * 100:.{decimals}f}%" if abs(value) < 10 else f"{value * 100:.{decimals}f}%"


def parse_date(value: Any) -> Optional[date]:
    """将字符串/时间戳转换为 date 对象。"""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


# ============================================================
# 统计函数
# ============================================================

def compute_quantiles(series: pd.Series, qs: list = None) -> dict:
    """计算分位数。"""
    if qs is None:
        qs = [0.0, 0.25, 0.5, 0.75, 1.0]
    result = {}
    for q in qs:
        result[f"p{int(q*100)}"] = series.quantile(q)
    return result


def standardize(series: pd.Series) -> pd.Series:
    """Z-score 标准化。"""
    mu, sigma = series.mean(), series.std()
    if sigma == 0:
        return series - mu
    return (series - mu) / sigma


def moving_average(series: pd.Series, window: int = 7) -> pd.Series:
    """计算移动平均。"""
    return series.rolling(window=window, min_periods=1).mean()


# ============================================================
# 增长率
# ============================================================

def mom_change(current: float, previous: float) -> Optional[float]:
    """环比增长 (Month-over-Month)。"""
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous


def yoy_change(current: float, last_year: float) -> Optional[float]:
    """同比增长 (Year-over-Year)。"""
    if last_year is None or last_year == 0:
        return None
    return (current - last_year) / last_year


# ============================================================
# 缺失值与异常检测
# ============================================================

def missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    """生成缺失值统计表。"""
    result = pd.DataFrame({
        "column": df.columns,
        "missing_count": df.isnull().sum().values,
        "missing_rate": (df.isnull().sum() / len(df)).values,
        "dtype": df.dtypes.values.astype(str),
    })
    result = result.sort_values("missing_rate", ascending=False)
    result["missing_rate"] = result["missing_rate"].apply(lambda x: f"{x:.2%}")
    return result.reset_index(drop=True)


def detect_outliers_iqr(series: pd.Series, multiplier: float = 1.5) -> pd.Series:
    """IQR 法异常值检测，返回布尔掩码（True=异常）。"""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return (series < lower) | (series > upper)


def detect_outliers_zscore(series: pd.Series, threshold: float = 3.0) -> pd.Series:
    """Z-score 法异常值检测，返回布尔掩码（True=异常）。"""
    mu, sigma = series.mean(), series.std()
    if sigma == 0:
        return pd.Series([False] * len(series), index=series.index)
    z = (series - mu).abs() / sigma
    return z > threshold


# ============================================================
# 缓存
# ============================================================

class CacheResultError(Exception):
    """缓存错误"""
    pass


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """生成缓存键。"""
    raw = f"{func_name}:{args}:{sorted(kwargs.items())}"
    return hashlib.md5(raw.encode()).hexdigest()


def cache_result(ttl: int = 3600):
    """结果缓存装饰器（基于磁盘文件）。

    Args:
        ttl: 缓存有效期（秒），默认 3600。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from .config import CACHE_DIR

            cache_dir = Path(CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)

            key = _make_cache_key(func.__name__, args, kwargs)
            cache_file = cache_dir / f"{func.__name__}_{key}.pkl"

            # 检查缓存
            if cache_file.exists():
                age = time.time() - cache_file.stat().st_mtime
                if age < ttl:
                    try:
                        with open(cache_file, "rb") as f:
                            return pickle.load(f)
                    except Exception:
                        pass  # 缓存损坏，重新计算

            # 计算并缓存
            result = func(*args, **kwargs)
            try:
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)
            except Exception as e:
                raise CacheResultError(f"缓存写入失败: {e}") from e

            return result
        return wrapper
    return decorator


# ============================================================
# 日志
# ============================================================

def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置应用日志。"""
    from .config import LOG_LEVEL

    level = level or LOG_LEVEL

    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("analytics")
    return logger


# ============================================================
# JSON 序列化
# ============================================================

class NumpyEncoder(json.JSONEncoder):
    """处理 numpy 数据类型的 JSON 编码器。"""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if not np.isnan(obj) else None
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def to_json(obj: Any, **kwargs) -> str:
    """将 Python 对象转为 JSON 字符串（自动处理 numpy 类型）。"""
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("cls", NumpyEncoder)
    return json.dumps(obj, **kwargs)
