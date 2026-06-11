"""R7 时间序列预测

日 GMV 预测 + 品类/SKU 预测 + 安全库存 + 补货建议。
"""

import logging
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import mean_absolute_error, mean_squared_error

from ..data_access import get_db_connection

warnings.filterwarnings("ignore")
logger = logging.getLogger("analytics.r7")


# ============================================================
# 11.1 时间序列构建
# ============================================================

def build_daily_gmv_series() -> pd.Series:
    """构建日 GMV 时间序列。"""
    conn = get_db_connection()
    try:
        df = pd.read_sql("""
            SELECT order_date, SUM(paid_amount) as gmv
            FROM fact_order WHERE status IN ('paid','completed')
            GROUP BY order_date ORDER BY order_date
        """, conn)
        df["order_date"] = pd.to_datetime(df["order_date"])
        ts = df.set_index("order_date")["gmv"]

        # 填充缺失日期
        full_range = pd.date_range(ts.index.min(), ts.index.max(), freq="D")
        ts = ts.reindex(full_range, fill_value=0)
        logger.info(f"日 GMV 序列: {len(ts)} 天 ({ts.index.min().date()} ~ {ts.index.max().date()})")
        return ts
    finally:
        conn.close()


def build_category_daily_series() -> Dict[str, pd.Series]:
    """构建品类日销量序列（TOP 5）。"""
    conn = get_db_connection()
    try:
        df = pd.read_sql("""
            SELECT oi.order_date, dp.category_name, SUM(oi.quantity) as qty
            FROM fact_order_item oi
            JOIN dim_product dp ON oi.sku_id = dp.sku_id
            GROUP BY oi.order_date, dp.category_name
        """, conn)
        df["order_date"] = pd.to_datetime(df["order_date"])

        # TOP 5 品类
        top5 = df.groupby("category_name")["qty"].sum().nlargest(5).index.tolist()

        result = {}
        for cat in top5:
            cat_df = df[df["category_name"] == cat].set_index("order_date")["qty"]
            full_range = pd.date_range(cat_df.index.min(), cat_df.index.max(), freq="D")
            result[cat] = cat_df.reindex(full_range, fill_value=0)

        return result
    finally:
        conn.close()


# ============================================================
# 11.2 趋势与季节分析
# ============================================================

def analyze_trend(ts: pd.Series) -> dict:
    """趋势分析：移动平均 + 周末效应 + 月度趋势。"""
    # 移动平均
    ma7 = ts.rolling(7, center=True).mean()
    ma30 = ts.rolling(30, center=True).mean()

    # 周末效应
    ts_df = ts.reset_index()
    ts_df.columns = ["date", "value"]
    ts_df["weekday"] = ts_df["date"].dt.weekday
    ts_df["is_weekend"] = ts_df["weekday"].isin([5, 6]).astype(int)
    weekend_avg = ts_df[ts_df["is_weekend"] == 1]["value"].mean()
    weekday_avg = ts_df[ts_df["is_weekend"] == 0]["value"].mean()
    weekend_effect = (weekend_avg - weekday_avg) / weekday_avg * 100 if weekday_avg else 0

    # 月度趋势
    ts_df["year_month"] = ts_df["date"].dt.strftime("%Y-%m")
    monthly = ts_df.groupby("year_month")["value"].agg(["sum", "mean", "std"]).reset_index()

    return {
        "ma7_values": [round(x, 2) if not pd.isna(x) else None for x in ma7.values[-90:]],
        "ma30_values": [round(x, 2) if not pd.isna(x) else None for x in ma30.values[-90:]],
        "weekend_effect_pct": round(weekend_effect, 2),
        "weekend_avg": round(weekend_avg, 2),
        "weekday_avg": round(weekday_avg, 2),
        "monthly_summary": monthly.tail(12).to_dict(orient="records"),
        "dates": [str(d.date()) for d in ts.index[-90:]],
        "values": [round(v, 2) for v in ts.values[-90:]],
    }


# ============================================================
# 11.3 平稳性检验
# ============================================================

def check_stationarity(ts: pd.Series) -> dict:
    """ADF + KPSS 检验。"""
    from statsmodels.tsa.stattools import adfuller, kpss

    # ADF
    adf_result = adfuller(ts.dropna(), autolag="AIC")
    adf_stationary = adf_result[1] < 0.05

    # KPSS
    try:
        kpss_result = kpss(ts.dropna(), regression="c", nlags="auto")
        kpss_stationary = kpss_result[1] > 0.05
    except Exception:
        kpss_result = [0, 0.5]
        kpss_stationary = False

    # 差分
    diff1 = ts.diff().dropna()
    adf_diff = adfuller(diff1, autolag="AIC")
    diff_stationary = adf_diff[1] < 0.05

    return {
        "adf_statistic": round(adf_result[0], 4),
        "adf_pvalue": round(adf_result[1], 4),
        "adf_stationary": adf_stationary,
        "kpss_statistic": round(kpss_result[0], 4),
        "kpss_pvalue": round(kpss_result[1], 4),
        "kpss_stationary": kpss_stationary,
        "needs_differencing": not adf_stationary,
        "diff1_pvalue": round(adf_diff[1], 4),
        "diff1_stationary": diff_stationary,
        "suggested_d": 1 if not adf_stationary and diff_stationary else 0,
    }


# ============================================================
# 11.4 预测模型
# ============================================================

def forecast_naive(ts: pd.Series, periods: int = 30) -> dict:
    """朴素预测：用最后 7 日均值。"""
    last_mean = ts.iloc[-7:].mean()
    forecast = np.full(periods, last_mean)
    return {"method": "朴素预测(7日均值)", "forecast": forecast.tolist()}


def forecast_moving_avg(ts: pd.Series, periods: int = 30, window: int = 7) -> dict:
    """移动平均预测。"""
    trend = ts.rolling(window).mean().iloc[-1]
    forecast = np.full(periods, trend)
    return {"method": f"移动平均({window}日)", "forecast": forecast.tolist()}


def forecast_exponential_smoothing(ts: pd.Series, periods: int = 30) -> dict:
    """指数平滑预测。"""
    alpha = 0.3
    smoothed = ts.iloc[0]
    for v in ts.iloc[1:]:
        smoothed = alpha * v + (1 - alpha) * smoothed
    forecast = np.full(periods, smoothed)
    return {"method": "指数平滑(α=0.3)", "forecast": forecast.tolist()}


def forecast_arima(ts: pd.Series, periods: int = 30) -> dict:
    """ARIMA 预测（简单自动选参）。"""
    try:
        from statsmodels.tsa.arima.model import ARIMA
        # 简单尝试几个参数
        best_aic = float("inf")
        best_result = None
        best_order = (1, 1, 1)

        for p in [1, 2]:
            for q in [1, 2]:
                try:
                    model = ARIMA(ts.dropna(), order=(p, 1, q))
                    fitted = model.fit()
                    if fitted.aic < best_aic:
                        best_aic = fitted.aic
                        best_result = fitted
                        best_order = (p, 1, q)
                except Exception:
                    continue

        if best_result is None:
            model = ARIMA(ts.dropna(), order=(1, 1, 1))
            best_result = model.fit()
            best_order = (1, 1, 1)

        fc = best_result.get_forecast(periods)
        fc_mean = fc.predicted_mean

        try:
            ci = fc.conf_int(alpha=0.05)
            lower = ci.iloc[:, 0].tolist()
            upper = ci.iloc[:, 1].tolist()
        except Exception:
            lower = upper = []

        return {
            "method": f"ARIMA{best_order}",
            "forecast": [round(float(x), 2) for x in fc_mean],
            "lower_bound": [round(float(x), 2) for x in lower] if lower else [],
            "upper_bound": [round(float(x), 2) for x in upper] if upper else [],
            "aic": round(best_aic, 2),
        }
    except Exception as e:
        logger.warning(f"ARIMA 失败: {e}, 降级到朴素预测")
        return forecast_naive(ts, periods)


def forecast_gmv(periods: int = 30) -> dict:
    """一站式 GMV 预测：4 种模型对比。"""
    ts = build_daily_gmv_series()

    # 用最后 365 天做训练/测试分割
    train = ts.iloc[:-30] if len(ts) > 60 else ts
    test = ts.iloc[-30:] if len(ts) > 30 else ts.iloc[-10:]

    models = {
        "naive": forecast_naive(train, len(test)),
        "moving_avg": forecast_moving_avg(train, len(test)),
        "exp_smooth": forecast_exponential_smoothing(train, len(test)),
        "arima": forecast_arima(train, len(test)),
    }

    # 评估
    evaluation = {}
    for name, result in models.items():
        pred = np.array(result["forecast"])
        actual = test.values[:len(pred)]
        mae = mean_absolute_error(actual, pred)
        rmse = np.sqrt(mean_squared_error(actual, pred))
        mape = np.mean(np.abs((actual - pred) / actual.clip(min=1))) * 100
        evaluation[name] = {"mae": round(mae, 2), "rmse": round(rmse, 2), "mape": round(mape, 1)}

    # 用最佳模型预测未来
    best_name = min(evaluation, key=lambda x: evaluation[x]["rmse"])
    future_forecast = models[best_name]

    # 生成未来日期
    last_date = ts.index.max()
    future_dates = [(last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(periods)]

    # 趋势分析
    trend = analyze_trend(ts)

    return {
        "history": {
            "dates": [str(d.date()) for d in ts.index[-365:]],
            "values": [round(v, 2) for v in ts.values[-365:]],
        },
        "models": evaluation,
        "best_model": best_name,
        "forecast": {
            "method": future_forecast["method"],
            "dates": future_dates,
            "values": [round(x, 2) for x in future_forecast["forecast"]],
        },
        "stationarity": check_stationarity(ts),
        "trend": trend,
    }


# ============================================================
# 11.5 品类预测
# ============================================================

def forecast_category(category_name: str = None, periods: int = 30) -> dict:
    """单个品类销量预测。"""
    cat_series = build_category_daily_series()
    if not cat_series:
        return {"error": "无品类数据"}
    if category_name is None:
        category_name = list(cat_series.keys())[0]

    ts = cat_series.get(category_name)
    if ts is None:
        return {"error": f"品类不存在: {category_name}"}

    train = ts.iloc[:-30] if len(ts) > 60 else ts
    test = ts.iloc[-30:] if len(ts) > 30 else ts.iloc[-7:]

    result = forecast_arima(train, len(test))
    pred = np.array(result["forecast"])
    actual = test.values[:len(pred)]
    mae = mean_absolute_error(actual, pred)
    mape = np.mean(np.abs((actual - pred) / actual.clip(min=1))) * 100

    return {
        "category": category_name,
        "mae": round(mae, 2),
        "mape": round(mape, 1),
        "forecast": [round(x, 2) for x in result["forecast"][:periods]],
    }


# ============================================================
# 11.6 安全库存与补货
# ============================================================

def compute_safety_stock() -> dict:
    """计算安全库存和补货建议。"""
    conn = get_db_connection()
    try:
        # SKU 日销量统计
        df = pd.read_sql("""
            SELECT oi.sku_id, oi.order_date, SUM(oi.quantity) as daily_qty
            FROM fact_order_item oi
            GROUP BY oi.sku_id, oi.order_date
        """, conn)

        results = []
        for sku_id, group in df.groupby("sku_id"):
            qty = group["daily_qty"]
            avg_demand = qty.mean()
            std_demand = qty.std()
            cv = std_demand / avg_demand if avg_demand > 0 else 0
            lead_time = 3  # 假设 3 天补货周期
            z = 1.65  # 95% 服务水平
            safety_stock = z * std_demand * np.sqrt(lead_time) if std_demand > 0 else 0
            rop = avg_demand * lead_time + safety_stock  # Reorder Point

            results.append({
                "sku_id": sku_id,
                "avg_daily_demand": round(avg_demand, 2),
                "cv": round(cv, 2),
                "safety_stock": round(safety_stock, 0),
                "reorder_point": round(rop, 0),
            })

        result_df = pd.DataFrame(results).sort_values("avg_daily_demand", ascending=False)

        # 紧急补货：CV 高 + 日均需求高
        urgent = result_df[(result_df["cv"] > 1.0) & (result_df["avg_daily_demand"] > 3)].head(20)
        # 库存过剩：CV 低 + 日均需求低
        excess = result_df[(result_df["cv"] < 0.5) & (result_df["avg_daily_demand"] < 2)].head(20)

        return {
            "top_skus": result_df.head(20).to_dict(orient="records"),
            "urgent_replenishment": urgent.to_dict(orient="records"),
            "excess_inventory": excess.to_dict(orient="records"),
        }
    finally:
        conn.close()
