#!/usr/bin/env python3
"""Quick comparison of two submissions"""

import pandas as pd
import numpy as np

original = pd.read_csv('submission.csv')
enhanced = pd.read_csv('submission_enhanced.csv')

print('=' * 80)
print('QUICK COMPARISON: submission.csv vs submission_enhanced.csv')
print('=' * 80)
print()

# Basic validation
print('File validation:')
print(f'  Original shape: {original.shape}')
print(f'  Enhanced shape: {enhanced.shape}')
print(f'  Both have same dates: {(original["Date"] == enhanced["Date"]).all()}')
print()

# Revenue comparison
print('Revenue Comparison:')
rev_diff = enhanced['Revenue'] - original['Revenue']
print(f'  Mean difference: ${rev_diff.mean():,.0f}')
print(f'  Std difference: ${rev_diff.std():,.0f}')
print(f'  Min difference: ${rev_diff.min():,.0f}')
print(f'  Max difference: ${rev_diff.max():,.0f}')
print(f'  Count of changes: {(rev_diff != 0).sum()} / {len(rev_diff)}')
print()

# COGS comparison
print('COGS Comparison:')
cogs_diff = enhanced['COGS'] - original['COGS']
print(f'  Mean difference: ${cogs_diff.mean():,.0f}')
print(f'  Std difference: ${cogs_diff.std():,.0f}')
print(f'  Min difference: ${cogs_diff.min():,.0f}')
print(f'  Max difference: ${cogs_diff.max():,.0f}')
print(f'  Count of changes: {(cogs_diff != 0).sum()} / {len(cogs_diff)}')
print()

# Top differences
print('Top 10 Revenue differences (largest increases):')
comparison = pd.DataFrame({
    'Date': original['Date'],
    'Original_Revenue': original['Revenue'],
    'Enhanced_Revenue': enhanced['Revenue'],
    'Revenue_Diff': rev_diff,
})
top_rev = comparison.nlargest(10, 'Revenue_Diff')[['Date', 'Original_Revenue', 'Enhanced_Revenue', 'Revenue_Diff']]
print(top_rev.to_string(index=False))
print()

print('Top 10 Revenue differences (largest decreases):')
bottom_rev = comparison.nsmallest(10, 'Revenue_Diff')[['Date', 'Original_Revenue', 'Enhanced_Revenue', 'Revenue_Diff']]
print(bottom_rev.to_string(index=False))
print()

# Statistics
print('Summary Statistics:')
print(f'  Total original revenue: ${original["Revenue"].sum():,.0f}')
print(f'  Total enhanced revenue: ${enhanced["Revenue"].sum():,.0f}')
print(f'  Difference: ${(enhanced["Revenue"].sum() - original["Revenue"].sum()):,.0f}')
pct_change = ((enhanced["Revenue"].sum() - original["Revenue"].sum()) / original["Revenue"].sum() * 100)
print(f'  Percentage change: {pct_change:.2f}%')
print()

print(f'  Total original COGS: ${original["COGS"].sum():,.0f}')
print(f'  Total enhanced COGS: ${enhanced["COGS"].sum():,.0f}')
print(f'  Difference: ${(enhanced["COGS"].sum() - original["COGS"].sum()):,.0f}')
print()

print('=' * 80)
