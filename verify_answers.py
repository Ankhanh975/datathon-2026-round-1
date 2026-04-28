#!/usr/bin/env python3
"""Verify Part 1 multiple-choice answers"""

import pandas as pd
from pathlib import Path

BASE_DIR = Path('.')
DATA_DIR = BASE_DIR / 'data'

orders = pd.read_csv(DATA_DIR / 'orders.csv', parse_dates=['order_date'])
order_items = pd.read_csv(DATA_DIR / 'order_items.csv', low_memory=False)
products = pd.read_csv(DATA_DIR / 'products.csv')
returns = pd.read_csv(DATA_DIR / 'returns.csv', parse_dates=['return_date'])
customers = pd.read_csv(DATA_DIR / 'customers.csv', parse_dates=['signup_date'])
geography = pd.read_csv(DATA_DIR / 'geography.csv')
payments = pd.read_csv(DATA_DIR / 'payments.csv')
web_traffic = pd.read_csv(DATA_DIR / 'web_traffic.csv', parse_dates=['date'])

print('=' * 80)
print('PART 1: MULTIPLE-CHOICE ANSWERS VERIFICATION')
print('=' * 80)
print()

# Q1
order_gaps = orders.sort_values(['customer_id', 'order_date']).groupby('customer_id')['order_date'].diff().dt.days.dropna()
q1_value = float(order_gaps.median())
print(f'Q1: Median inter-order gap: {q1_value:.0f} days')
print()

# Q2
products_copy = products.copy()
products_copy['gross_margin'] = (products_copy['price'] - products_copy['cogs']) / products_copy['price']
q2_table = products_copy.groupby('segment')['gross_margin'].mean().sort_values(ascending=False)
print(f'Q2: Segment with highest gross margin:')
print(q2_table)
print(f'Answer: {q2_table.index[0]} ({q2_table.iloc[0]:.1%})')
print()

# Q3
returns_joined = returns.merge(products[['product_id', 'category']], on='product_id', how='left')
q3_table = returns_joined[returns_joined['category'] == 'Streetwear']['return_reason'].value_counts()
print(f'Q3: Most common return reason for Streetwear:')
print(q3_table.head())
print(f'Answer: {q3_table.index[0]}')
print()

# Q4
q4_table = web_traffic.groupby('traffic_source')['bounce_rate'].mean().sort_values()
print(f'Q4: Traffic source with lowest bounce rate:')
print(q4_table)
print(f'Answer: {q4_table.index[0]} ({q4_table.iloc[0]:.1%})')
print()

# Q5
q5_value = order_items['promo_id'].notna().mean() * 100
print(f'Q5: Promo adoption: {q5_value:.2f}%')
print()

# Q6
orders_by_age = orders.merge(customers[['customer_id', 'age_group']], on='customer_id', how='left')
orders_by_age = orders_by_age[orders_by_age['age_group'].notna()]
q6_table = orders_by_age.groupby('age_group').agg(orders=('order_id', 'count'), customers=('customer_id', 'nunique'))
q6_table['orders_per_customer'] = q6_table['orders'] / q6_table['customers']
q6_sorted = q6_table.sort_values('orders_per_customer', ascending=False)
print(f'Q6: Orders per customer by age group:')
print(q6_sorted)
print(f'Answer: {q6_sorted.index[0]} ({q6_sorted.iloc[0]["orders_per_customer"]:.2f} orders/customer)')
print()

# Q7
order_revenue = order_items.assign(line_revenue=order_items['quantity'] * order_items['unit_price'] - order_items['discount_amount'])
order_revenue = order_revenue.groupby('order_id', as_index=False)['line_revenue'].sum()
region_revenue = orders.merge(order_revenue, on='order_id').merge(geography[['zip', 'region']], on='zip', how='left')
q7_table = region_revenue.groupby('region')['line_revenue'].sum().sort_values(ascending=False)
print(f'Q7: Revenue by region:')
print(q7_table)
print(f'Answer: {q7_table.index[0]} (${q7_table.iloc[0]/1e6:.1f}M)')
print()

# Q8
q8_table = orders[orders['order_status'] == 'cancelled']['payment_method'].value_counts()
print(f'Q8: Payment method in cancelled orders:')
print(q8_table)
if len(q8_table) > 0:
    print(f'Answer: {q8_table.index[0]}')
print()

# Q9
items_by_size = order_items.merge(products[['product_id', 'size']], on='product_id', how='left')
returns_by_size = returns.merge(products[['product_id', 'size']], on='product_id', how='left')
q9_table = (returns_by_size.groupby('size').size() / items_by_size.groupby('size').size()).sort_values(ascending=False)
print(f'Q9: Return rate by size:')
print(q9_table)
print(f'Answer: {q9_table.index[0]} ({q9_table.iloc[0]:.2%})')
print()

# Q10
q10_table = payments.groupby('installments')['payment_value'].mean().sort_values(ascending=False)
print(f'Q10: Average payment by installment plan:')
print(q10_table)
print(f'Answer: {int(q10_table.index[0])} installments (${q10_table.iloc[0]:,.0f})')
print()

print('=' * 80)
print('SUMMARY')
print('=' * 80)
print(f'Q1: {q1_value:.0f} days')
print(f'Q2: {q2_table.index[0]}')
print(f'Q3: {q3_table.index[0]}')
print(f'Q4: {q4_table.index[0]}')
print(f'Q5: {q5_value:.2f}%')
print(f'Q6: {q6_sorted.index[0]}')
print(f'Q7: {q7_table.index[0]}')
print(f'Q8: (see above)')
print(f'Q9: {q9_table.index[0]}')
print(f'Q10: {int(q10_table.index[0])} installments')
