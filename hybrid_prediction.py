#!/usr/bin/env python3
"""Hybrid sales forecast for Datathon 2026 Round 1.

This script keeps the useful parts of the baseline and prediction notebooks,
but trims the extra complexity. It blends three simple strategies per target:

1. A lag-based HistGradientBoostingRegressor
2. A seasonal naive forecast with 365-day and 7-day fallback
3. A baseline-style seasonal profile with year-over-year scaling

The blend weights are learned on 2022 as a holdout year, then the final model
is refit on all available history and used to generate submission_hybrid.csv.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

BASE_DIR = Path(".")
DATA_DIR = BASE_DIR / "data"
TRAIN_FILE = DATA_DIR / "sales.csv"
TEST_FILE = BASE_DIR / "sample_submission.csv"
OUT_FILE = BASE_DIR / "submission_hybrid.csv"


def load_csv(name: str, **kwargs) -> pd.DataFrame:
    path = DATA_DIR / name if (DATA_DIR / name).exists() else BASE_DIR / name
    return pd.read_csv(path, **kwargs)


def mae(actual: Iterable[float], pred: Iterable[float]) -> float:
    return float(mean_absolute_error(actual, pred))


def rmse(actual: Iterable[float], pred: Iterable[float]) -> float:
    return float(np.sqrt(mean_squared_error(actual, pred)))


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    date = pd.to_datetime(data["Date"])

    data["year"] = date.dt.year
    data["month"] = date.dt.month
    data["day"] = date.dt.day
    data["dayofweek"] = date.dt.dayofweek
    data["dayofyear"] = date.dt.dayofyear
    data["weekofyear"] = date.dt.isocalendar().week.astype(int)
    data["quarter"] = date.dt.quarter
    data["is_month_start"] = date.dt.is_month_start.astype(int)
    data["is_month_end"] = date.dt.is_month_end.astype(int)
    data["is_quarter_end"] = date.dt.is_quarter_end.astype(int)
    data["is_year_end"] = date.dt.is_year_end.astype(int)
    data["is_weekend"] = (date.dt.dayofweek >= 5).astype(int)

    data["sin_doy"] = np.sin(2 * np.pi * data["dayofyear"] / 365.25)
    data["cos_doy"] = np.cos(2 * np.pi * data["dayofyear"] / 365.25)
    data["sin_month"] = np.sin(2 * np.pi * data["month"] / 12)
    data["cos_month"] = np.cos(2 * np.pi * data["month"] / 12)
    data["trend"] = (date - date.min()).dt.days.astype(float)

    return data


def add_lag_features(frame: pd.DataFrame, target_col: str) -> pd.DataFrame:
    data = frame.copy()
    series = data[target_col].astype(float)

    for lag in (1, 7, 14, 28, 365):
        data[f"lag_{lag}"] = series.shift(lag)

    shifted = series.shift(1)
    for window in (7, 28, 90):
        data[f"roll_mean_{window}"] = shifted.rolling(window, min_periods=1).mean()
        data[f"roll_std_{window}"] = shifted.rolling(window, min_periods=2).std().fillna(0.0)

    data["ewm_14"] = shifted.ewm(span=14, adjust=False, min_periods=1).mean()
    data["ewm_28"] = shifted.ewm(span=28, adjust=False, min_periods=1).mean()
    data["growth_7"] = (series.shift(1) / series.shift(8)).replace([np.inf, -np.inf], 1.0)
    data["growth_28"] = (series.shift(1) / series.shift(29)).replace([np.inf, -np.inf], 1.0)

    return data


def build_supervised_frame(frame: pd.DataFrame, target_col: str) -> pd.DataFrame:
    data = add_calendar_features(frame)
    data = add_lag_features(data, target_col)
    return data.dropna().reset_index(drop=True)


def make_model(random_state: int = 42) -> TransformedTargetRegressor:
    base = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_iter=350,
        max_depth=5,
        min_samples_leaf=20,
        l2_regularization=0.1,
        random_state=random_state,
    )
    return TransformedTargetRegressor(
        regressor=base,
        func=np.log1p,
        inverse_func=np.expm1,
    )


def seasonal_naive_forecast(
    history_frame: pd.DataFrame,
    target_col: str,
    future_dates: Iterable[pd.Timestamp],
    seasonal_lags: Tuple[int, ...] = (365, 7, 28, 1),
) -> np.ndarray:
    history = history_frame[["Date", target_col]].copy()
    history["Date"] = pd.to_datetime(history["Date"])
    history_map = {pd.Timestamp(date): float(value) for date, value in zip(history["Date"], history[target_col])}

    predictions: List[float] = []
    for forecast_date in pd.to_datetime(list(future_dates)):
        value = None
        for lag in seasonal_lags:
            ref_date = forecast_date - pd.Timedelta(days=lag)
            if ref_date in history_map:
                value = history_map[ref_date]
                break
        if value is None:
            value = float(history[target_col].iloc[-1])
        value = max(float(value), 0.0)
        predictions.append(value)
        history_map[pd.Timestamp(forecast_date)] = value

    return np.asarray(predictions, dtype=float)


def build_profile_state(history_frame: pd.DataFrame, target_col: str) -> Tuple[int, float, float, Dict[Tuple[int, int], float]]:
    history = history_frame.copy()
    history["Date"] = pd.to_datetime(history["Date"])
    history["year"] = history["Date"].dt.year
    history["month"] = history["Date"].dt.month
    history["day"] = history["Date"].dt.day

    annual = history.groupby("year")[target_col].mean().sort_index()
    usable_years = annual.loc[2013:].dropna()
    if len(usable_years) < 2:
        base_year = int(annual.index.max())
        growth = 1.0
    else:
        yoy = usable_years.pct_change().dropna()
        growth = float(np.exp(np.log1p(yoy).mean())) if len(yoy) else 1.0
        base_year = int(usable_years.index.max())

    base_level = float(annual.loc[base_year])

    seasonal_source = history[history["year"] >= 2013].copy()
    seasonal_source = seasonal_source.merge(
        annual.rename("annual_mean"),
        left_on="year",
        right_index=True,
        how="left",
    )
    seasonal_source["normalized"] = seasonal_source[target_col] / seasonal_source["annual_mean"]
    seasonal_profile = (
        seasonal_source.groupby(["month", "day"])["normalized"]
        .mean()
        .to_dict()
    )

    return base_year, base_level, growth, seasonal_profile


def profile_forecast(
    history_frame: pd.DataFrame,
    target_col: str,
    future_dates: Iterable[pd.Timestamp],
) -> np.ndarray:
    base_year, base_level, growth, seasonal_profile = build_profile_state(history_frame, target_col)

    predictions: List[float] = []
    for forecast_date in pd.to_datetime(list(future_dates)):
        seasonal_factor = seasonal_profile.get((forecast_date.month, forecast_date.day), 1.0)
        years_ahead = forecast_date.year - base_year
        value = base_level * (growth ** years_ahead) * seasonal_factor
        predictions.append(max(float(value), 0.0))

    return np.asarray(predictions, dtype=float)


def recursive_forecast(
    history_frame: pd.DataFrame,
    target_col: str,
    model: TransformedTargetRegressor,
    feature_cols: List[str],
    future_dates: Iterable[pd.Timestamp],
) -> np.ndarray:
    history = history_frame[["Date", target_col]].copy()
    history["Date"] = pd.to_datetime(history["Date"])

    predictions: List[float] = []
    for forecast_date in pd.to_datetime(list(future_dates)):
        frame = pd.concat(
            [history, pd.DataFrame({"Date": [forecast_date], target_col: [np.nan]})],
            ignore_index=True,
        )
        features = build_supervised_frame(frame, target_col)
        row = features.iloc[[-1]]
        row_features = row[feature_cols]
        value = float(model.predict(row_features)[0])
        value = max(value, 0.0)
        predictions.append(value)

        history = pd.concat(
            [history, pd.DataFrame({"Date": [forecast_date], target_col: [value]})],
            ignore_index=True,
        )

    return np.asarray(predictions, dtype=float)


def fit_and_score_model(
    train_history: pd.DataFrame,
    valid_history: pd.DataFrame,
    target_col: str,
) -> Tuple[Dict[str, np.ndarray], pd.DataFrame, Dict[str, float], List[str]]:
    train_supervised = build_supervised_frame(train_history, target_col)
    feature_cols = [c for c in train_supervised.columns if c not in {"Date", target_col}]

    model = make_model()
    model.fit(train_supervised[feature_cols], train_supervised[target_col])

    future_dates = valid_history["Date"]
    candidates = {
        "model": recursive_forecast(train_history, target_col, model, feature_cols, future_dates),
        "seasonal": seasonal_naive_forecast(train_history, target_col, future_dates),
        "profile": profile_forecast(train_history, target_col, future_dates),
    }

    actual = valid_history[target_col].to_numpy(dtype=float)
    rows = []
    for name, pred in candidates.items():
        rows.append(
            {
                "strategy": name,
                "mae": mae(actual, pred),
                "rmse": rmse(actual, pred),
                "r2": r2_score(actual, pred),
            }
        )
    table = pd.DataFrame(rows).sort_values("mae").reset_index(drop=True)

    inverse = 1.0 / np.clip(table.set_index("strategy")["mae"].to_numpy(dtype=float), 1e-9, None)
    inverse = inverse / inverse.sum()
    weights = {strategy: float(weight) for strategy, weight in zip(table["strategy"], inverse)}

    return candidates, table, weights, feature_cols


def weighted_blend(candidates: Dict[str, np.ndarray], weights: Dict[str, float]) -> np.ndarray:
    blended = np.zeros(len(next(iter(candidates.values()))), dtype=float)
    for name, pred in candidates.items():
        blended += weights.get(name, 0.0) * pred
    return blended


def forecast_target(
    history_frame: pd.DataFrame,
    target_col: str,
    future_dates: Iterable[pd.Timestamp],
    validation_cutoff_year: int = 2022,
) -> Tuple[np.ndarray, pd.DataFrame, Dict[str, float]]:
    history_frame = history_frame.copy()
    history_frame["Date"] = pd.to_datetime(history_frame["Date"])

    train_history = history_frame[history_frame["Date"].dt.year < validation_cutoff_year].copy()
    valid_history = history_frame[history_frame["Date"].dt.year == validation_cutoff_year].copy()

    candidates, holdout_table, weights, feature_cols = fit_and_score_model(train_history, valid_history, target_col)

    print(f"\n[{target_col}] Holdout validation on {validation_cutoff_year}")
    print(holdout_table.to_string(index=False))
    print(f"[{target_col}] Blend weights: {weights}")

    full_supervised = build_supervised_frame(history_frame, target_col)
    final_model = make_model(random_state=43)
    final_model.fit(full_supervised[feature_cols], full_supervised[target_col])

    final_candidates = {
        "model": recursive_forecast(history_frame, target_col, final_model, feature_cols, future_dates),
        "seasonal": seasonal_naive_forecast(history_frame, target_col, future_dates),
        "profile": profile_forecast(history_frame, target_col, future_dates),
    }
    blended = weighted_blend(final_candidates, weights)

    return blended, holdout_table, weights


def main() -> None:
    print("HYBRID SALES FORECAST")
    print("Baseline + prediction notebook strategies, simplified")

    sales = load_csv("sales.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    submission = load_csv("sample_submission.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)

    revenue_pred, revenue_table, revenue_weights = forecast_target(sales[["Date", "Revenue"]], "Revenue", submission["Date"])
    cogs_pred, cogs_table, cogs_weights = forecast_target(sales[["Date", "COGS"]], "COGS", submission["Date"])

    result = submission.copy()
    result["Revenue"] = np.round(revenue_pred, 2)
    result["COGS"] = np.round(cogs_pred, 2)
    result.to_csv(OUT_FILE, index=False)

    print("\nForecast summary:")
    print(f"  Revenue weights: {revenue_weights}")
    print(f"  COGS weights: {cogs_weights}")
    print(f"  Saved: {OUT_FILE}")
    print(f"  Rows: {len(result)}")
    print(f"  Revenue sum: {result['Revenue'].sum():,.0f}")
    print(f"  COGS sum: {result['COGS'].sum():,.0f}")


if __name__ == "__main__":
    main()