# Datathon 2026 Round 1 Report Draft

## Overview
This project analyzes a Vietnamese e-commerce fashion dataset spanning 2012-07-04 to 2022-12-31 and forecasts daily Revenue and COGS for 2023-01-01 to 2024-07-01. The work is organized into three parts: multiple-choice validation, exploratory analysis, and sales forecasting.

## Part 2: Visual Exploration and Business Analysis

### 1. Demand moved in large seasonal waves
The daily Revenue and COGS series show strong recurring seasonal structure with a clear rise into the mid-year months and a softer demand period later in the year. Annual totals peaked around 2016-2018 before dropping sharply in 2019-2020 and stabilizing at a lower level afterward. This suggests a structural change in business scale, assortment mix, or market conditions rather than isolated noise.

Business implication: inventory, promotion, and staffing plans should not be flat across the year. The company should plan for pronounced seasonal peaks and build a separate playbook for the lower-demand post-2019 regime.

### 2. Revenue is concentrated in the East region
Region-level aggregation shows the East as the strongest revenue contributor, followed by Central and then West. The gap is material, so regional demand is not balanced across the country.

Business implication: the East should remain the default priority for stock allocation and campaign coverage. Expansion into Central and West should be treated as a growth experiment with separate conversion and fulfillment KPIs.

### 3. Segment profitability is uneven
Gross margin differs by product segment. Standard has the highest average gross margin in the dataset, while other segments sit lower. That means volume and profitability do not always move together.

Business implication: assortment decisions should consider margin as well as demand. High-margin segments deserve better shelf space, but low-margin segments may still be worth keeping if they drive traffic or customer retention.

### 4. Returns are mostly fit-related
For Streetwear items, wrong_size is the dominant return reason. The size-level return-rate chart also shows meaningful differences across S, M, L, and XL, with S highest in this slice.

Business implication: better fit guidance should be one of the highest-return interventions. Size recommendation UI, improved product descriptions, and exchange-first post-purchase flows can reduce refund cost and protect gross revenue.

### 5. Acquisition quality varies by channel and cohort
Email campaign and social_media show the lowest average bounce rates among the observed traffic sources. Older customer age groups place slightly more orders per customer than younger groups.

Business implication: budget should not be based on traffic volume alone. Channels with lower bounce rates are more efficient acquisition sources, while the older cohorts appear to have stronger repeat behavior and are worth targeted retention efforts.

## Part 3: Forecasting Method

### Modeling approach
The forecasting model uses only the provided files and follows a leakage-safe workflow:
1. Build calendar features from the date stamp.
2. Add lag features for 1, 7, 14, 28, and 365 days.
3. Add rolling means and rolling standard deviations over 7, 28, and 90 days.
4. Train separate models for Revenue and COGS using a time-series split.
5. Use a holdout-year blend search between the ML recursive forecast and a seasonal-naive forecast.
6. Forecast the test horizon recursively so each future day only depends on past actual or predicted values.

The final estimator is a HistGradientBoostingRegressor wrapped in a log1p target transform. This choice handles nonlinearity, seasonal interactions, and the heavy-tailed revenue distribution better than a plain linear baseline. The final blend weight selected on the holdout year is alpha = 0.85 for Revenue and alpha = 1.00 for COGS (full ML forecast).

### Cross-validation results
Using expanding-window time-series cross-validation, the model achieved the following average scores:
- Revenue: MAE 720,565.83, RMSE 1,034,564.37, R2 0.7967
- COGS: MAE 618,346.04, RMSE 883,731.20, R2 0.7917

These results are substantially stronger than a naive seasonal baseline because the model learns short-term inertia and yearly recurrence patterns from lag features.

### Explainability
Permutation importance on the held-out period shows that the strongest drivers are:
- lag_1
- day
- lag_365
- lag_7
- lag_14
- sin_doy
- lag_28
- growth_28

Interpretation: the model relies most heavily on recent history and annual seasonality. In business terms, tomorrow's demand is strongly anchored in yesterday's demand, but the same calendar position in the prior year also matters, which is consistent with a recurring retail cycle.

### Submission
The notebook exports a reproducible `submission.csv` with the exact row order and columns required by `sample_submission.csv`. The file was validated against the template shape before export (548 rows, date range 2023-01-01 to 2024-07-01, columns Date/Revenue/COGS).

## Reproducibility Notes
- All features are derived from the supplied CSV files only.
- The notebook uses a fixed random state for model training.
- The forecasting code is fully self-contained and can be rerun from top to bottom.
- The final submission file is written to `submission.csv` in the workspace root.
