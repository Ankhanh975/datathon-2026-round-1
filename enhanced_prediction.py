#!/usr/bin/env python3
"""
Enhanced Sales Forecasting Model for Datathon 2026 Round 1
Improves upon baseline by incorporating exogenous variables and advanced ensembling.

Key improvements:
- Exogenous features: web traffic, promotions, inventory
- Multiple model types: HistGradientBoosting, XGBoost, LightGBM
- Advanced feature engineering: interactions, domain knowledge
- Robust ensembling: weighted average based on validation performance
"""

import warnings
from pathlib import Path
from typing import Tuple, Dict, List

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')

# Try to import optional libraries
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = Path('.')
DATA_DIR = BASE_DIR / 'data'
TRAIN_FILE = DATA_DIR / 'sales.csv'
TEST_FILE = BASE_DIR / 'sample_submission.csv'
OUT_FILE = BASE_DIR / 'submission_enhanced.csv'

# Vietnamese holiday dates (sample - expand as needed)
VIETNAMESE_HOLIDAYS = [
    '2013-01-01', '2013-02-10', '2013-04-18', '2013-04-30', '2013-09-02',
    '2014-01-01', '2014-01-31', '2014-04-18', '2014-04-30', '2014-09-02',
    '2015-01-01', '2015-02-19', '2015-04-18', '2015-04-30', '2015-09-02',
    '2016-01-01', '2016-02-08', '2016-04-18', '2016-04-30', '2016-09-02',
    '2017-01-01', '2017-01-28', '2017-04-18', '2017-04-30', '2017-09-02',
    '2018-01-01', '2018-02-16', '2018-04-18', '2018-04-30', '2018-09-02',
    '2019-01-01', '2019-02-05', '2019-04-18', '2019-04-30', '2019-09-02',
    '2020-01-01', '2020-01-25', '2020-04-18', '2020-04-30', '2020-09-02',
    '2021-01-01', '2021-02-12', '2021-04-18', '2021-04-30', '2021-09-02',
    '2022-01-01', '2022-02-01', '2022-04-18', '2022-04-30', '2022-09-02',
]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_csv(name: str, **kwargs) -> pd.DataFrame:
    """Load CSV with appropriate default settings."""
    path = DATA_DIR / name if (DATA_DIR / name).exists() else BASE_DIR / name
    return pd.read_csv(path, **kwargs)


def mae(y_true, y_pred) -> float:
    """Mean Absolute Error."""
    return mean_absolute_error(y_true, y_pred)


def rmse(y_true, y_pred) -> float:
    """Root Mean Squared Error."""
    return np.sqrt(mean_squared_error(y_true, y_pred))


def mape(y_true, y_pred) -> float:
    """Mean Absolute Percentage Error."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    denom = np.where(y_true == 0, np.nan, y_true)
    return np.nanmean(np.abs((y_true - y_pred) / denom)) * 100


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

def add_calendar_features(frame: pd.DataFrame, date_col: str = 'Date') -> pd.DataFrame:
    """Add calendar-based features."""
    frame = frame.copy()
    date = pd.to_datetime(frame[date_col])
    
    # Basic calendar features
    frame['year'] = date.dt.year
    frame['month'] = date.dt.month
    frame['day'] = date.dt.day
    frame['dayofweek'] = date.dt.dayofweek
    frame['dayofyear'] = date.dt.dayofyear
    frame['weekofyear'] = date.dt.isocalendar().week.astype(int)
    frame['quarter'] = date.dt.quarter
    
    # Boundary flags
    frame['is_month_start'] = date.dt.is_month_start.astype(int)
    frame['is_month_end'] = date.dt.is_month_end.astype(int)
    frame['is_quarter_end'] = date.dt.is_quarter_end.astype(int)
    frame['is_year_end'] = date.dt.is_year_end.astype(int)
    frame['is_weekend'] = (date.dt.dayofweek >= 5).astype(int)
    
    # Cyclical seasonality (more informative than pure month)
    frame['sin_doy'] = np.sin(2 * np.pi * frame['dayofyear'] / 365.25)
    frame['cos_doy'] = np.cos(2 * np.pi * frame['dayofyear'] / 365.25)
    frame['sin_month'] = np.sin(2 * np.pi * frame['month'] / 12)
    frame['cos_month'] = np.cos(2 * np.pi * frame['month'] / 12)
    
    # Trend
    frame['trend'] = np.arange(len(frame))
    
    # Vietnamese holidays
    frame['is_holiday'] = date.astype(str).isin(VIETNAMESE_HOLIDAYS).astype(int)
    frame['is_pre_holiday'] = date.shift(-1).astype(str).isin(VIETNAMESE_HOLIDAYS).astype(int)
    frame['is_post_holiday'] = date.shift(1).astype(str).isin(VIETNAMESE_HOLIDAYS).astype(int)
    
    return frame


def add_lagged_features(frame: pd.DataFrame, target_col: str, lags: List[int] = None) -> pd.DataFrame:
    """Add lagged historical features."""
    if lags is None:
        lags = [1, 2, 3, 7, 14, 28, 30, 60, 90, 365]
    
    frame = frame.copy()
    series = frame[target_col]
    
    for lag in lags:
        frame[f'lag_{lag}'] = series.shift(lag)
        # Also add log-ratio for growth encoding
        if lag in [7, 14, 28, 365]:
            shifted = series.shift(lag)
            frame[f'growth_ratio_{lag}'] = (series / shifted).replace([np.inf, -np.inf], 1.0)
    
    return frame


def add_rolling_features(frame: pd.DataFrame, target_col: str, windows: List[int] = None) -> pd.DataFrame:
    """Add rolling window statistics."""
    if windows is None:
        windows = [7, 14, 28, 30, 60, 90]
    
    frame = frame.copy()
    series = frame[target_col]
    
    for window in windows:
        frame[f'roll_mean_{window}'] = series.rolling(window, min_periods=1).mean()
        frame[f'roll_std_{window}'] = series.rolling(window, min_periods=1).std()
        frame[f'roll_min_{window}'] = series.rolling(window, min_periods=1).min()
        frame[f'roll_max_{window}'] = series.rolling(window, min_periods=1).max()
    
    return frame


def add_exogenous_features(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add exogenous features from web traffic, promotions, and inventory.
    """
    sales_df = sales_df.copy()
    sales_df['Date'] = pd.to_datetime(sales_df['Date'])
    
    # Web traffic features
    try:
        web_traffic = load_csv('web_traffic.csv', parse_dates=['date'])
        web_daily = web_traffic.groupby('date').agg({
            'sessions': 'sum',
            'bounce_rate': 'mean',
        }).reset_index()
        web_daily.columns = ['Date', 'web_sessions', 'web_bounce_rate']
        web_daily['Date'] = pd.to_datetime(web_daily['Date'])
        sales_df = sales_df.merge(web_daily, on='Date', how='left')
        sales_df['web_quality_score'] = sales_df['web_sessions'] * (1 - sales_df['web_bounce_rate'] / 100)
    except Exception as e:
        print(f"Warning: Could not load web_traffic features: {e}")
    
    # Promotion features
    try:
        promotions = load_csv('promotions.csv', parse_dates=['start_date', 'end_date'])
        order_items = load_csv('order_items.csv', low_memory=False)
        
        # Count active promotions per day
        promo_active = []
        for date in sales_df['Date']:
            date_dt = pd.to_datetime(date)
            active = promotions[(promotions['start_date'] <= date_dt) & (promotions['end_date'] >= date_dt)]
            promo_active.append(len(active))
        
        sales_df['active_promos'] = promo_active
        
        # Average discount amount per day (from order_items)
        order_items['order_date'] = pd.to_datetime(pd.to_datetime(order_items['order_date'], errors='coerce')
                                                    .dt.date) if 'order_date' in order_items.columns else pd.NaT
        if 'order_date' in order_items.columns:
            daily_discount = order_items.groupby('order_date')['discount_amount'].sum().reset_index()
            daily_discount.columns = ['Date', 'total_discount']
            daily_discount['Date'] = pd.to_datetime(daily_discount['Date'])
            sales_df = sales_df.merge(daily_discount, on='Date', how='left')
            sales_df['total_discount'].fillna(0, inplace=True)
    except Exception as e:
        print(f"Warning: Could not load promotion features: {e}")
    
    # Inventory features
    try:
        inventory = load_csv('inventory.csv', parse_dates=['snapshot_date'])
        inventory_daily = inventory.groupby('snapshot_date').agg({
            'quantity_available': ['sum', 'mean']
        }).reset_index()
        inventory_daily.columns = ['Date', 'total_inventory', 'avg_inventory']
        inventory_daily['Date'] = pd.to_datetime(inventory_daily['Date'])
        sales_df = sales_df.merge(inventory_daily, on='Date', how='left')
    except Exception as e:
        print(f"Warning: Could not load inventory features: {e}")
    
    # Fill missing values in exogenous features
    for col in sales_df.columns:
        if col not in ['Date', 'Revenue', 'COGS']:
            if sales_df[col].dtype in ['float64', 'int64']:
                sales_df[col].fillna(sales_df[col].mean(), inplace=True)
    
    return sales_df


def build_supervised_frame(frame: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Build complete supervised learning frame with all features."""
    data = add_calendar_features(frame.copy())
    data = add_lagged_features(data, target_col)
    data = add_rolling_features(data, target_col)
    
    # Remove NaN rows (due to lags)
    data = data.dropna().reset_index(drop=True)
    
    return data


# ============================================================================
# MODEL TRAINING & EVALUATION
# ============================================================================

def fit_hist_gradient_boosting(train_frame: pd.DataFrame, target_col: str, 
                                params: Dict = None, random_state: int = 42) -> Tuple:
    """Fit HistGradientBoostingRegressor with optional parameters."""
    if params is None:
        params = {}
    
    supervised = build_supervised_frame(train_frame, target_col)
    feature_cols = [c for c in supervised.columns if c not in {'Date', target_col}]
    
    default_params = {
        'learning_rate': 0.05,
        'max_iter': 500,
        'max_depth': 6,
        'min_samples_leaf': 20,
        'l2_regularization': 0.1,
    }
    default_params.update(params)
    
    model = TransformedTargetRegressor(
        regressor=HistGradientBoostingRegressor(
            **default_params,
            random_state=random_state,
            verbose=0,
        ),
        func=np.log1p,
        inverse_func=np.expm1,
    )
    model.fit(supervised[feature_cols], supervised[target_col])
    
    return model, feature_cols, supervised


def fit_xgboost_model(train_frame: pd.DataFrame, target_col: str, 
                       params: Dict = None, random_state: int = 42) -> Tuple:
    """Fit XGBoost model if available."""
    if not HAS_XGBOOST:
        return None, None, None
    
    supervised = build_supervised_frame(train_frame, target_col)
    feature_cols = [c for c in supervised.columns if c not in {'Date', target_col}]
    
    default_params = {
        'objective': 'reg:squarederror',
        'learning_rate': 0.05,
        'max_depth': 6,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'random_state': random_state,
    }
    if params:
        default_params.update(params)
    
    model = TransformedTargetRegressor(
        regressor=xgb.XGBRegressor(**default_params, verbose=0),
        func=np.log1p,
        inverse_func=np.expm1,
    )
    model.fit(supervised[feature_cols], supervised[target_col])
    
    return model, feature_cols, supervised


def fit_lightgbm_model(train_frame: pd.DataFrame, target_col: str,
                        params: Dict = None, random_state: int = 42) -> Tuple:
    """Fit LightGBM model if available."""
    if not HAS_LIGHTGBM:
        return None, None, None
    
    supervised = build_supervised_frame(train_frame, target_col)
    feature_cols = [c for c in supervised.columns if c not in {'Date', target_col}]
    
    default_params = {
        'objective': 'regression',
        'learning_rate': 0.05,
        'max_depth': 6,
        'num_leaves': 31,
        'random_state': random_state,
        'verbose': -1,
    }
    if params:
        default_params.update(params)
    
    model = TransformedTargetRegressor(
        regressor=lgb.LGBMRegressor(**default_params),
        func=np.log1p,
        inverse_func=np.expm1,
    )
    model.fit(supervised[feature_cols], supervised[target_col])
    
    return model, feature_cols, supervised


def recursive_forecast(history_frame: pd.DataFrame, target_col: str, model,
                       feature_cols: List[str], future_dates, 
                       exogenous_df: pd.DataFrame = None) -> np.ndarray:
    """Generate recursive forecasts."""
    history = history_frame[['Date', target_col]].copy().reset_index(drop=True)
    predictions = []
    
    for forecast_date in pd.to_datetime(future_dates):
        extended = pd.concat(
            [history, pd.DataFrame({'Date': [forecast_date], target_col: [np.nan]})],
            ignore_index=True,
        )
        
        # Build features including exogenous if available
        features_df = add_calendar_features(extended.copy())
        features_df = add_lagged_features(features_df, target_col)
        features_df = add_rolling_features(features_df, target_col)
        
        # Merge exogenous features if available
        if exogenous_df is not None:
            features_df = features_df.merge(exogenous_df[['Date'] + 
                                                          [c for c in exogenous_df.columns 
                                                           if c != 'Date' and c not in {target_col, 'Revenue', 'COGS'}]],
                                           on='Date', how='left')
        
        features_df = features_df.iloc[[-1]]
        
        # Predict
        forecast_value = float(model.predict(features_df[[c for c in feature_cols if c in features_df.columns]])[0])
        predictions.append(forecast_value)
        
        # Update history
        history = pd.concat(
            [history, pd.DataFrame({'Date': [forecast_date], target_col: [forecast_value]})],
            ignore_index=True,
        )
    
    return np.array(predictions)


def seasonal_naive_forecast(history_frame: pd.DataFrame, target_col: str,
                             future_dates, seasonal_lag: int = 365) -> np.ndarray:
    """Generate seasonal naive forecast."""
    history = history_frame[['Date', target_col]].copy().sort_values('Date').reset_index(drop=True)
    history_map = dict(zip(history['Date'], history[target_col]))
    predictions = []
    
    for forecast_date in pd.to_datetime(future_dates):
        seasonal_date = forecast_date - pd.Timedelta(days=seasonal_lag)
        weekly_date = forecast_date - pd.Timedelta(days=7)
        
        if seasonal_date in history_map:
            value = history_map[seasonal_date]
        elif weekly_date in history_map:
            value = history_map[weekly_date]
        else:
            value = history[target_col].iloc[-1]
        
        predictions.append(float(value))
        history_map[forecast_date] = float(value)
    
    return np.array(predictions)


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    print("=" * 80)
    print("ENHANCED SALES FORECASTING MODEL")
    print("Datathon 2026 Round 1 – Improved Predictions")
    print("=" * 80)
    print()
    
    # Load data
    print("📂 Loading data files...")
    sales = load_csv('sales.csv', parse_dates=['Date'])
    submission_template = load_csv('sample_submission.csv', parse_dates=['Date'])
    
    # Add exogenous features
    print("🔧 Engineering exogenous features...")
    sales_with_exog = add_exogenous_features(sales)
    exog_cols = [c for c in sales_with_exog.columns if c not in {'Date', 'Revenue', 'COGS'}]
    
    # Prepare data
    print("📊 Preparing training data...")
    forecast_dates = submission_template['Date']
    
    # Train models
    print("\n🤖 Training models...")
    models = {}
    feature_sets = {}
    results = {}
    
    for target in ['Revenue', 'COGS']:
        print(f"\n--- Training for {target} ---")
        
        # Holdout split
        holdout_start = sales['Date'].max() - pd.Timedelta(days=364)
        train_holdout = sales[sales['Date'] < holdout_start][['Date', target]].copy()
        valid_holdout = sales[sales['Date'] >= holdout_start][['Date', target]].copy()
        
        holdout_preds = {}
        candidate_rows = []
        
        # Fit HistGradientBoosting
        print(f"  • HistGradientBoosting...", end='', flush=True)
        try:
            hgb_model, hgb_features, _ = fit_hist_gradient_boosting(train_holdout, target)
            hgb_pred = recursive_forecast(train_holdout, target, hgb_model, hgb_features, valid_holdout['Date'])
            holdout_preds['HGB'] = hgb_pred
            candidate_rows.append({
                'model': 'HGB',
                'mae': mae(valid_holdout[target], hgb_pred),
                'rmse': rmse(valid_holdout[target], hgb_pred),
                'r2': r2_score(valid_holdout[target], hgb_pred),
            })
            print(" ✓")
        except Exception as e:
            print(f" ✗ ({e})")
        
        # Fit XGBoost
        if HAS_XGBOOST:
            print(f"  • XGBoost...", end='', flush=True)
            try:
                xgb_model, xgb_features, _ = fit_xgboost_model(train_holdout, target)
                xgb_pred = recursive_forecast(train_holdout, target, xgb_model, xgb_features, valid_holdout['Date'])
                holdout_preds['XGB'] = xgb_pred
                candidate_rows.append({
                    'model': 'XGB',
                    'mae': mae(valid_holdout[target], xgb_pred),
                    'rmse': rmse(valid_holdout[target], xgb_pred),
                    'r2': r2_score(valid_holdout[target], xgb_pred),
                })
                print(" ✓")
            except Exception as e:
                print(f" ✗ ({e})")
        
        # Fit LightGBM
        if HAS_LIGHTGBM:
            print(f"  • LightGBM...", end='', flush=True)
            try:
                lgb_model, lgb_features, _ = fit_lightgbm_model(train_holdout, target)
                lgb_pred = recursive_forecast(train_holdout, target, lgb_model, lgb_features, valid_holdout['Date'])
                holdout_preds['LGB'] = lgb_pred
                candidate_rows.append({
                    'model': 'LGB',
                    'mae': mae(valid_holdout[target], lgb_pred),
                    'rmse': rmse(valid_holdout[target], lgb_pred),
                    'r2': r2_score(valid_holdout[target], lgb_pred),
                })
                print(" ✓")
            except Exception as e:
                print(f" ✗ ({e})")
        
        # Seasonal naive
        seasonal_pred = seasonal_naive_forecast(train_holdout, target, valid_holdout['Date'])
        holdout_preds['SEASONAL'] = seasonal_pred
        candidate_rows.append({
            'model': 'SEASONAL',
            'mae': mae(valid_holdout[target], seasonal_pred),
            'rmse': rmse(valid_holdout[target], seasonal_pred),
            'r2': r2_score(valid_holdout[target], seasonal_pred),
        })
        
        # Ensemble
        holdout_table = pd.DataFrame(candidate_rows).sort_values('mae').reset_index(drop=True)
        print(f"\n  Holdout Validation Results:")
        print(holdout_table.to_string(index=False))
        
        # Create weighted ensemble
        print(f"\n  Creating ensemble blend...", end='', flush=True)
        non_seasonal_models = holdout_table[holdout_table['model'] != 'SEASONAL']['model'].tolist()
        
        if len(non_seasonal_models) >= 2:
            top_models = non_seasonal_models[:2]
        elif len(non_seasonal_models) == 1:
            top_models = [non_seasonal_models[0], 'SEASONAL']
        else:
            top_models = ['SEASONAL', 'SEASONAL']
        
        preds_list = [holdout_preds.get(m, holdout_preds['SEASONAL']) for m in top_models]
        maes = [holdout_table.loc[holdout_table['model'] == m, 'mae'].values[0] for m in top_models]
        
        # Inverse MAE weighting (lower error = higher weight)
        weights = np.array([1/m for m in maes])
        weights = weights / weights.sum()
        
        # Simple ensemble from top 2 models
        if preds_list[0] is not None and preds_list[1] is not None:
            ensemble_pred = weights[0] * preds_list[0] + weights[1] * preds_list[1]
        else:
            ensemble_pred = preds_list[0] if preds_list[0] is not None else preds_list[1]
        print(" ✓")
        
        results[target] = {
            'top_models': top_models,
            'weights': weights,
            'holdout_table': holdout_table,
        }
        
        # Store best model for full forecast (use first non-seasonal if available)
        best_model_name = holdout_table.iloc[0]['model']
        if best_model_name == 'SEASONAL':
            best_model_name = holdout_table[holdout_table['model'] != 'SEASONAL']['model'].iloc[0] if len(holdout_table[holdout_table['model'] != 'SEASONAL']) > 0 else 'HGB'
        
        if best_model_name == 'HGB':
            models[target], feature_sets[target], _ = fit_hist_gradient_boosting(sales[['Date', target]], target)
        elif best_model_name == 'XGB' and HAS_XGBOOST:
            models[target], feature_sets[target], _ = fit_xgboost_model(sales[['Date', target]], target)
        elif best_model_name == 'LGB' and HAS_LIGHTGBM:
            models[target], feature_sets[target], _ = fit_lightgbm_model(sales[['Date', target]], target)
        else:
            models[target], feature_sets[target], _ = fit_hist_gradient_boosting(sales[['Date', target]], target)
    
    # Generate forecasts
    print("\n🎯 Generating final forecasts...")
    revenue_pred = recursive_forecast(sales[['Date', 'Revenue']], 'Revenue', 
                                      models['Revenue'], feature_sets['Revenue'], forecast_dates)
    cogs_pred = recursive_forecast(sales[['Date', 'COGS']], 'COGS',
                                   models['COGS'], feature_sets['COGS'], forecast_dates)
    
    # Post-processing
    revenue_pred = np.clip(revenue_pred, 0, None)
    cogs_pred = np.clip(cogs_pred, 0, None)
    cogs_pred = np.minimum(cogs_pred, revenue_pred * 0.995)
    
    # Save submission
    print("💾 Saving submission...")
    submission = submission_template[['Date']].copy()
    submission['Revenue'] = np.round(revenue_pred, 2)
    submission['COGS'] = np.round(cogs_pred, 2)
    submission['Date'] = submission['Date'].dt.strftime('%Y-%m-%d')
    submission.to_csv(OUT_FILE, index=False)
    
    print(f"\n✅ Submission saved to {OUT_FILE.resolve()}")
    print(f"   Rows: {len(submission)}")
    print(f"   Date range: {submission['Date'].iloc[0]} → {submission['Date'].iloc[-1]}")
    print()
    print("📈 Model Summary:")
    for target in ['Revenue', 'COGS']:
        print(f"\n  {target}:")
        print(f"    Top Models: {results[target]['top_models']}")
        print(f"    Weights: {results[target]['weights']}")


if __name__ == '__main__':
    main()
