# Part 3 Report: Sales Forecasting

## 1. Business Context
The company is a Vietnamese fashion e-commerce business that needs daily demand forecasts to improve inventory allocation, promotion timing, and logistics planning. Forecast quality at daily granularity directly affects stockouts, overstock risk, and fulfillment cost.

## 2. Problem Definition
Forecast daily Revenue and COGS for the full horizon in sales_test.csv (from 2023-01-01 to 2024-07-01), following the required submission order and format.

Target outputs per day:
- Revenue
- COGS

## 3. Data Used
Only provided competition files were used.

Core forecasting table:
- sales.csv (2012-07-04 to 2022-12-31)

Supporting context tables were used in EDA and interpretation, but the forecasting model for Part 3 uses the historical sales series and time-derived features only, which avoids data leakage from unavailable future operational variables.

## 4. Evaluation Metrics
The competition specifies MAE, RMSE, and R2.

MAE:
$$
\mathrm{MAE} = \frac{1}{n}\sum_{i=1}^{n}|\hat{y}_i - y_i|
$$

RMSE:
$$
\mathrm{RMSE} = \sqrt{\frac{1}{n}\sum_{i=1}^{n}(\hat{y}_i - y_i)^2}
$$

R2:
$$
R^2 = 1 - \frac{\sum_{i=1}^{n}(y_i-\hat{y}_i)^2}{\sum_{i=1}^{n}(y_i-\bar{y})^2}
$$

Lower MAE and RMSE are better. Higher R2 is better.

## 5. Constraints and Compliance
This pipeline follows the Part 3 constraints:
- No external data.
- No use of test Revenue or COGS as features.
- Reproducible notebook implementation.
- Explainability included via permutation feature importance.

## 6. Methodology
### 6.1 Feature Engineering
Calendar features from date:
- year, month, day, dayofweek, dayofyear, weekofyear, quarter
- month/quarter/year boundary flags
- cyclical seasonality (sin_doy, cos_doy)
- trend index

Autoregressive features:
- lags: 1, 7, 14, 28, 365
- rolling mean and rolling std over 7, 28, 90 days
- growth ratios over 7 and 28 days

### 6.2 Base Learner
The core learner is HistGradientBoostingRegressor wrapped with log1p/expm1 target transformation:
- Handles non-linear interactions and seasonality effects.
- Log transform reduces sensitivity to heavy-tailed spikes.

### 6.3 Candidate Search
Instead of one fixed configuration, three HGB parameter sets were tested on a strict final-year holdout split. This was done separately for Revenue and COGS.

### 6.4 Validation Protocol
Time-based holdout:
- Train: data before the last 365 days.
- Validation: final 365 days.

This setup mirrors real deployment and prevents future information leakage.

### 6.5 Ensemble Strategy
For each target:
1. Rank candidate models by holdout MAE.
2. Keep top two HGB models.
3. Build a weighted blend with a seasonal naive component (365-day naive with 7-day fallback).
4. Grid-search weights that minimize holdout MAE.

### 6.6 Forecast Generation
Recursive forecasting was used over the full test horizon:
- Predict day t.
- Append prediction to history.
- Recompute lag/rolling features for day t+1.

This ensures each forecast uses only historical actuals or previous predictions.

### 6.7 Post-processing Rules
- Clip negative predictions to zero.
- Enforce COGS <= 0.995 * Revenue to keep outputs economically consistent.

## 7. Quantitative Results
### 7.1 Holdout Comparison (Revenue)
- model_2: MAE 683,486.92, RMSE 971,612.30, R2 0.6630
- model_1: MAE 689,924.90, RMSE 962,632.60, R2 0.6692
- model_3: MAE 716,453.72, RMSE 1,026,545.00, R2 0.6239
- seasonal naive: MAE 837,704.09, RMSE 1,161,819.00, R2 0.5182

Selected models: model_2 and model_1

Selected blend weights:
- w(model_2) = 0.60
- w(model_1) = 0.25
- w(seasonal) = 0.15

### 7.2 Holdout Comparison (COGS)
- model_1: MAE 564,744.10, RMSE 786,236.63, R2 0.7094
- model_3: MAE 565,420.86, RMSE 763,905.79, R2 0.7257
- model_2: MAE 574,684.58, RMSE 784,230.84, R2 0.7109
- seasonal naive: MAE 701,957.57, RMSE 960,716.18, R2 0.5662

Selected models: model_1 and model_3

Selected blend weights:
- w(model_1) = 0.50
- w(model_3) = 0.45
- w(seasonal) = 0.05

## 8. Explainability
Permutation importance indicates the dominant drivers are consistent across targets:
- lag_1 (strongest)
- day
- lag_365
- lag_7 and lag_14
- sin_doy / seasonal terms

Business interpretation:
- Short-term inertia matters most (yesterday strongly influences today).
- Same-season effect across years is also strong (lag_365).
- Calendar position (day and cyclical seasonality) captures retail demand rhythm.

## 9. Error Patterns and Risk Discussion
Observed residual risk areas:
- Demand shocks and abrupt campaign effects are hard to infer from univariate history alone.
- Recursive forecasting can accumulate error across long horizons.
- Structural shifts beyond 2022 can reduce holdout-to-test transfer.

Mitigations already applied:
- Ensemble blending for robustness.
- Seasonal component for stability.
- Target transformation and clipping constraints.

## 10. Reproducibility
Implementation is fully contained in the notebook pipeline.

Reproducibility checklist:
- Deterministic random_state set in model fitting.
- No dependency on external APIs or external data files.
- Single-step run from imports to export.

## 11. Final Submission Output
Generated file:
- submission.csv

Validation summary:
- Rows: 548
- Date range: 2023-01-01 to 2024-07-01
- Columns: Date, Revenue, COGS

First sample rows:
- 2023-01-01, 1,874,898.62, 1,701,741.00
- 2023-01-02, 1,356,224.56, 1,066,358.79
- 2023-01-03, 890,947.89, 886,493.15

## 12. Conclusion
The final forecasting approach is a leakage-safe, holdout-optimized ensemble of gradient-boosted autoregressive models plus a seasonal stabilizer. It improves holdout MAE versus single-model baselines, keeps outputs economically plausible, and provides interpretable drivers for business stakeholders.

This approach is suitable as the team Part 3 baseline for leaderboard submission and technical report defense.