"""
NYC Property Sales — Exploratory Data Analysis
===============================================
Run this BEFORE writing ingest.py, schema chunks, or prompts.
Findings feed directly into Phase 1 + Phase 2.

Usage:
    python eda.py

Output:
    - Prints full report to stdout
    - Writes eda_findings.md in current directory

Requirements:
    pip install sodapy pandas tabulate
"""

import json
import os
from collections import Counter
from datetime import datetime

import pandas as pd
from sodapy import Socrata
from tabulate import tabulate

# ── Config ────────────────────────────────────────────────────────────────────
DOMAIN = "data.cityofnewyork.us"
DATASET_ID = "w2pb-icbu"
SAMPLE_SIZE = 10_000   # rows to pull for EDA — enough to be representative
# Get a free token:
#   1. Login at https://evergreen.data.socrata.com
#   2. Profile menu → Developer Settings → Create New App Token
#   3. Add to .env: SOCRATA_APP_TOKEN=your_token
APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", None)

# ── Fetch ─────────────────────────────────────────────────────────────────────
print(f"Fetching {SAMPLE_SIZE:,} rows from Socrata {DATASET_ID}...")
client = Socrata(DOMAIN, APP_TOKEN)
results = client.get(DATASET_ID, limit=SAMPLE_SIZE)
df = pd.DataFrame.from_records(results)
print(f"Got {len(df):,} rows, {len(df.columns)} columns\n")

findings = {}

# ── 1. Exact column names ─────────────────────────────────────────────────────
print("=" * 60)
print("1. EXACT COLUMN NAMES & TYPES (as returned by API)")
print("=" * 60)

col_info = []
for col in df.columns:
    sample_vals = df[col].dropna().head(3).tolist()
    col_info.append([col, df[col].dtype, sample_vals])

print(tabulate(col_info, headers=["Column", "dtype", "Sample values"], tablefmt="grid"))
findings["columns"] = list(df.columns)

# ── 2. Null rates ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. NULL / EMPTY RATES PER COLUMN")
print("=" * 60)

null_info = []
for col in df.columns:
    nulls = df[col].isna().sum()
    empties = (df[col] == "").sum() if df[col].dtype == object else 0
    total_missing = nulls + empties
    pct = total_missing / len(df) * 100
    null_info.append([col, nulls, empties, total_missing, f"{pct:.1f}%"])

null_info.sort(key=lambda x: x[3], reverse=True)
print(tabulate(null_info,
    headers=["Column", "Nulls", "Empty str", "Total missing", "% missing"],
    tablefmt="grid"))
findings["null_rates"] = {row[0]: row[4] for row in null_info}

# ── 3. Sale price distribution ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. SALE_PRICE DISTRIBUTION")
print("=" * 60)

if "sale_price" in df.columns:
    df["sale_price_num"] = pd.to_numeric(df["sale_price"], errors="coerce")
    prices = df["sale_price_num"].dropna()

    zero_sales = (prices == 0).sum()
    under_100 = (prices < 100).sum()
    under_10k = (prices < 10_000).sum()
    under_100k = (prices < 100_000).sum()

    print(f"  Total rows with sale_price:  {len(prices):,}")
    print(f"  $0 sales (transfers):        {zero_sales:,} ({zero_sales/len(prices)*100:.1f}%)")
    print(f"  < $100:                      {under_100:,} ({under_100/len(prices)*100:.1f}%)")
    print(f"  < $10,000:                   {under_10k:,} ({under_10k/len(prices)*100:.1f}%)")
    print(f"  < $100,000:                  {under_100k:,} ({under_100k/len(prices)*100:.1f}%)")
    print()

    market_sales = prices[prices > 10_000]
    print(f"  Market sales (> $10k):       {len(market_sales):,}")
    print()
    print(tabulate([
        ["Min",    f"${market_sales.min():,.0f}"],
        ["Median", f"${market_sales.median():,.0f}"],
        ["Mean",   f"${market_sales.mean():,.0f}"],
        ["75th %", f"${market_sales.quantile(0.75):,.0f}"],
        ["90th %", f"${market_sales.quantile(0.90):,.0f}"],
        ["99th %", f"${market_sales.quantile(0.99):,.0f}"],
        ["Max",    f"${market_sales.max():,.0f}"],
    ], headers=["Stat", "Value (market sales > $10k)"], tablefmt="grid"))

    findings["sale_price"] = {
        "zero_sales_pct": f"{zero_sales/len(prices)*100:.1f}%",
        "under_10k_pct": f"{under_10k/len(prices)*100:.1f}%",
        "market_median": f"${market_sales.median():,.0f}",
        "market_mean": f"${market_sales.mean():,.0f}",
        "market_max": f"${market_sales.max():,.0f}",
        "recommended_filter": "WHERE sale_price > 10000"
    }
else:
    print("  WARNING: sale_price column not found!")
    findings["sale_price"] = "COLUMN NOT FOUND"

# ── 4. Borough values ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. BOROUGH — EXACT VALUES")
print("=" * 60)

if "borough" in df.columns:
    borough_counts = df["borough"].value_counts()
    print(tabulate(
        [[b, c, f"{c/len(df)*100:.1f}%"] for b, c in borough_counts.items()],
        headers=["Borough (exact string)", "Count", "% of sample"],
        tablefmt="grid"
    ))
    findings["borough_values"] = borough_counts.index.tolist()
else:
    print("  WARNING: borough column not found!")
    findings["borough_values"] = "COLUMN NOT FOUND"

# ── 5. Building class categories ──────────────────────────────────────────────
print("\n" + "=" * 60)
print("5. BUILDING_CLASS_CATEGORY — ALL UNIQUE VALUES")
print("=" * 60)

bcc_col = next((c for c in df.columns if "building_class_category" in c.lower()), None)
if bcc_col:
    bcc_counts = df[bcc_col].value_counts()
    print(tabulate(
        [[b, c, f"{c/len(df)*100:.1f}%"] for b, c in bcc_counts.items()],
        headers=["Building Class Category", "Count", "%"],
        tablefmt="grid"
    ))
    findings["building_class_categories"] = bcc_counts.index.tolist()
else:
    print("  WARNING: building_class_category column not found!")
    print(f"  Available columns: {[c for c in df.columns if 'build' in c.lower() or 'class' in c.lower()]}")
    findings["building_class_categories"] = "COLUMN NOT FOUND"

# ── 6. Date range ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("6. DATE RANGE")
print("=" * 60)

date_col = next((c for c in df.columns if "sale_date" in c.lower()), None)
if date_col:
    df["sale_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = df["sale_date_parsed"].dropna()
    print(f"  Earliest sale: {valid_dates.min().date()}")
    print(f"  Latest sale:   {valid_dates.max().date()}")
    print(f"  Years covered: {sorted(valid_dates.dt.year.unique().tolist())}")
    year_counts = valid_dates.dt.year.value_counts().sort_index()
    print()
    print(tabulate(
        [[yr, cnt] for yr, cnt in year_counts.items()],
        headers=["Year", "Sales count"],
        tablefmt="grid"
    ))
    findings["date_range"] = {
        "earliest": str(valid_dates.min().date()),
        "latest": str(valid_dates.max().date()),
        "years": sorted(valid_dates.dt.year.unique().tolist())
    }
else:
    print("  WARNING: sale_date column not found!")
    findings["date_range"] = "COLUMN NOT FOUND"

# ── 7. Duplicates ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("7. DUPLICATE RECORDS")
print("=" * 60)

dup_count = df.duplicated().sum()
print(f"  Exact duplicate rows: {dup_count:,} ({dup_count/len(df)*100:.1f}%)")

key_cols = [c for c in ["borough", "block", "lot", "sale_date", "sale_price"] if c in df.columns]
if key_cols:
    key_dups = df.duplicated(subset=key_cols).sum()
    print(f"  Duplicates on {key_cols}: {key_dups:,}")
findings["duplicates"] = {"exact": dup_count}

# ── 8. Gross sq ft nulls by building type ─────────────────────────────────────
print("\n" + "=" * 60)
print("8. GROSS_SQ_FT NULLS BY BUILDING CLASS")
print("=" * 60)

sqft_col = next((c for c in df.columns if "gross_sq_ft" in c.lower() or "gross_square" in c.lower()), None)
if sqft_col and bcc_col:
    df["sqft_num"] = pd.to_numeric(df[sqft_col], errors="coerce")
    sqft_null_by_class = df.groupby(bcc_col)["sqft_num"].apply(
        lambda x: f"{x.isna().sum()}/{len(x)} ({x.isna().mean()*100:.0f}%)"
    ).reset_index()
    sqft_null_by_class.columns = ["Building Class", "Null sqft (count/total/%)"]
    print(tabulate(sqft_null_by_class.values.tolist(),
        headers=["Building Class", "Null sqft"],
        tablefmt="grid"))
    findings["sqft_nulls"] = "See output above"
else:
    print(f"  gross_sq_ft col found: {sqft_col}, bcc col found: {bcc_col}")

# ── 9. Outlier bounds ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("9. OUTLIER BOUNDS ON SALE PRICE")
print("=" * 60)

if "sale_price_num" in df.columns:
    market = df[df["sale_price_num"] > 10_000]["sale_price_num"]
    p99 = market.quantile(0.99)
    p999 = market.quantile(0.999)
    extreme = market[market > p999]
    print(f"  99th percentile:  ${p99:,.0f}")
    print(f"  99.9th percentile: ${p999:,.0f}")
    print(f"  Values above 99.9th: {len(extreme):,}")
    if len(extreme) > 0:
        print(f"  Top 5 prices: {sorted(extreme.tolist(), reverse=True)[:5]}")
    findings["outlier_bounds"] = {
        "p99": f"${p99:,.0f}",
        "p999": f"${p999:,.0f}",
        "recommendation": f"Consider flagging sales > ${p999:,.0f} as potential outliers"
    }

# ── 10. Column name mismatches from data dictionary ───────────────────────────
print("\n" + "=" * 60)
print("10. COLUMN NAME CHECK vs DATA DICTIONARY")
print("=" * 60)

expected = [
    "borough", "neighborhood", "building_class_category", "tax_class_at_present",
    "block", "lot", "easement", "building_class_as_of_final_roll", "address",
    "apartment_number", "zip_code", "residential_units", "commercial_units",
    "total_units", "land_square_feet", "gross_square_feet", "year_built",
    "tax_class_at_time_of_sale", "building_class_at_time_of_sale",
    "sale_price", "sale_date"
]

actual = set(df.columns)
print("  Expected vs actual column names:")
match_info = []
for exp in expected:
    if exp in actual:
        match_info.append([exp, "✓ MATCH", ""])
    else:
        # fuzzy find closest
        close = [c for c in actual if exp.replace("_", "") in c.replace("_", "") or
                 c.replace("_", "") in exp.replace("_", "")]
        match_info.append([exp, "✗ MISSING", f"Similar: {close[:2] if close else 'none'}"])

print(tabulate(match_info, headers=["Expected", "Status", "Note"], tablefmt="grid"))
findings["column_mismatches"] = [r for r in match_info if r[1] != "✓ MATCH"]

# ── Write findings markdown ────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("WRITING eda_findings.md")
print("=" * 60)

md = f"""# NYC Property Sales — EDA Findings
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Sample size: {len(df):,} rows from Socrata {DATASET_ID}

---

## 1. Actual Column Names
```
{chr(10).join(findings['columns'])}
```

## 2. Null Rates
{chr(10).join([f"- `{k}`: {v}" for k, v in findings['null_rates'].items()])}

## 3. Sale Price
{json.dumps(findings.get('sale_price', {}), indent=2)}

## 4. Borough Values (exact strings)
{chr(10).join([f"- `{b}`" for b in findings.get('borough_values', [])])}

## 5. Building Class Categories
{chr(10).join([f"- `{b}`" for b in findings.get('building_class_categories', [])])}

## 6. Date Range
{json.dumps(findings.get('date_range', {}), indent=2)}

## 7. Duplicates
{json.dumps(findings.get('duplicates', {}), indent=2)}

## 8. Sqft Nulls
{findings.get('sqft_nulls', 'See stdout')}

## 9. Outlier Bounds
{json.dumps(findings.get('outlier_bounds', {}), indent=2)}

## 10. Column Mismatches vs Data Dictionary
{chr(10).join([f"- Expected `{r[0]}`: {r[2]}" for r in findings.get('column_mismatches', [])])}

---

## Prompt Rules (update prompts.py from these findings)

Based on the above, the SQL prompt should include:
- Filter: `WHERE sale_price > 10000` (removes {findings.get('sale_price', {}).get('under_10k_pct', '?')} of rows)
- Borough values: {findings.get('borough_values', [])}
- Date range: {findings.get('date_range', {}).get('earliest', '?')} to {findings.get('date_range', {}).get('latest', '?')}
- Outlier note: flag sales > {findings.get('outlier_bounds', {}).get('p999', '?')}
"""

with open("eda_findings.md", "w") as f:
    f.write(md)

print("  Written to eda_findings.md")
print("\nEDA complete. Review eda_findings.md before writing ingest.py or prompts.py.")
