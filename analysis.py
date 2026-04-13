import sqlite3
import pandas as pd
import numpy as np
from scipy import stats
from sklearn.metrics import mean_squared_error
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'REACT_v3.db')
OUT_PATH = os.path.join(os.path.dirname(__file__), 'data', 'analysis_results.json')

conn = sqlite3.connect(DB_PATH)

# ─────────────────────────────────────────────
# 1. LOAD PAIRED MEASUREMENTS
# ─────────────────────────────────────────────
paired_query = """
SELECT
    se.site_id, se.date,
    m.contaminant_id  AS metal,
    m.fraction_id     AS fraction,
    MAX(CASE WHEN m.method_id='ICP-MS' THEN m.value_ug_l END) AS icpms,
    MAX(CASE WHEN m.method_id='HMS'    THEN m.value_ug_l END) AS hms,
    MAX(CASE WHEN m.method_id='ICP-MS' THEN m.is_bdl    END) AS icpms_bdl,
    MAX(CASE WHEN m.method_id='HMS'    THEN m.is_bdl    END) AS hms_bdl
FROM measurements m
JOIN sampling_events se ON m.event_id = se.event_id
GROUP BY se.site_id, se.date, m.contaminant_id, m.fraction_id
HAVING icpms IS NOT NULL AND hms IS NOT NULL
"""
df = pd.read_sql_query(paired_query, conn)

# ─────────────────────────────────────────────
# 2. LOAD TURBIDITY DATA
# ─────────────────────────────────────────────
turb_query = """
SELECT se.event_id, se.site_id, se.date, er.value_numeric AS turbidity
FROM environmental_readings er
JOIN sampling_events se ON er.event_id = se.event_id
WHERE er.parameter_id = 'turbidity'
"""
turb = pd.read_sql_query(turb_query, conn)
conn.close()

# ─────────────────────────────────────────────
# 3. EQS STANDARDS (EU Water Framework Directive)
#    AA-EQS = Annual Average, MAC-EQS = Maximum Allowable
#    Units: µg/L, dissolved fraction
#    Source: EU Directive 2013/39/EU + national guidance
# ─────────────────────────────────────────────
EQS = {
    'Pb': {'AA':  7.2,  'MAC': None, 'fraction': 'dissolved'},
    'Cd': {'AA':  0.08, 'MAC': 0.45, 'fraction': 'dissolved'},  # class 3 hardness
    'Cu': {'AA':  None, 'MAC': None, 'fraction': 'dissolved'},   # national standard
    'Zn': {'AA':  None, 'MAC': None, 'fraction': 'dissolved'},   # national standard
}

# ─────────────────────────────────────────────
# 4. SENSOR VS ICP-MS REGRESSION
# ─────────────────────────────────────────────
regression_results = {}

for metal in ['Pb', 'Cd', 'Cu', 'Zn']:
    for fraction in ['total', 'dissolved']:
        sub = df[(df['metal'] == metal) & (df['fraction'] == fraction)].copy()
        sub = sub.dropna(subset=['icpms', 'hms'])
        n = len(sub)
        if n < 3:
            continue

        x = sub['icpms'].values
        y = sub['hms'].values

        slope, intercept, r, p_value, se = stats.linregress(x, y)
        r2 = r ** 2
        rmse = np.sqrt(mean_squared_error(y, x))
        bias = np.mean(y - x)
        mean_ratio = np.mean(y / x) if np.all(x > 0) else None
        rsd = (np.std(y - x) / np.mean(x) * 100) if np.mean(x) > 0 else None

        key = f"{metal}_{fraction}"
        regression_results[key] = {
            'metal': metal,
            'fraction': fraction,
            'n': int(n),
            'r2': round(float(r2), 4),
            'slope': round(float(slope), 4),
            'intercept': round(float(intercept), 4),
            'p_value': round(float(p_value), 6),
            'rmse': round(float(rmse), 4),
            'bias': round(float(bias), 4),
            'mean_ratio': round(float(mean_ratio), 4) if mean_ratio else None,
            'rsd_pct': round(float(rsd), 2) if rsd else None,
            'kpi3_pass': bool(r2 >= 0.85),
            'kpi4_pass': bool(abs(bias / np.mean(x) * 100) <= 30) if np.mean(x) > 0 else None,
        }

print("=== SENSOR VS ICP-MS REGRESSION ===")
for k, v in regression_results.items():
    print(f"{k:20s} n={v['n']:3d}  R²={v['r2']:.3f}  RMSE={v['rmse']:.2f}  "
          f"bias={v['bias']:.2f}  KPI3={'PASS' if v['kpi3_pass'] else 'FAIL'}")

# ─────────────────────────────────────────────
# 5. EQS COMPLIANCE
# ─────────────────────────────────────────────
eqs_results = {}

icpms_dissolved = df[
    (df['method_id'] == 'ICP-MS') if 'method_id' in df.columns
    else (df['fraction'] == 'dissolved')
].copy() if 'method_id' in df.columns else df[df['fraction'] == 'dissolved'].copy()

# Use ICP-MS dissolved values for EQS (regulatory standard)
eqs_df = df[df['fraction'] == 'dissolved'][['site_id', 'date', 'metal', 'icpms']].copy()
eqs_df = eqs_df.dropna(subset=['icpms'])

for metal, standards in EQS.items():
    aa_eqs = standards['AA']
    mac_eqs = standards['MAC']
    sub = eqs_df[eqs_df['metal'] == metal]

    for site in sub['site_id'].unique():
        site_data = sub[sub['site_id'] == site]['icpms']
        mean_val = float(site_data.mean())
        max_val = float(site_data.max())
        n = int(len(site_data))

        aa_status = None
        mac_status = None
        if aa_eqs:
            aa_status = 'EXCEEDS' if mean_val > aa_eqs else 'COMPLIANT'
        if mac_eqs:
            mac_status = 'EXCEEDS' if max_val > mac_eqs else 'COMPLIANT'

        key = f"{site}_{metal}"
        eqs_results[key] = {
            'site': site,
            'metal': metal,
            'n': n,
            'mean_ug_l': round(mean_val, 4),
            'max_ug_l': round(max_val, 4),
            'aa_eqs': aa_eqs,
            'mac_eqs': mac_eqs,
            'aa_status': aa_status,
            'mac_status': mac_status,
        }

print("\n=== EQS COMPLIANCE (ICP-MS dissolved) ===")
for k, v in eqs_results.items():
    aa = v['aa_status'] or 'N/A'
    mac = v['mac_status'] or 'N/A'
    print(f"{k:12s}  mean={v['mean_ug_l']:10.3f}  AA-EQS: {aa:10s}  MAC-EQS: {mac}")

# ─────────────────────────────────────────────
# 6. TURBIDITY EFFECT ANALYSIS
# ─────────────────────────────────────────────
turb_results = {}

# Merge turbidity with HMS vs ICP-MS difference
hms_df = df[df['fraction'] == 'dissolved'][['site_id', 'date', 'metal', 'icpms', 'hms']].copy()
hms_df = hms_df.dropna(subset=['icpms', 'hms'])
hms_df['abs_diff'] = np.abs(hms_df['hms'] - hms_df['icpms'])
hms_df['rel_diff_pct'] = (np.abs(hms_df['hms'] - hms_df['icpms']) / hms_df['icpms'] * 100).where(hms_df['icpms'] > 0)

merged = hms_df.merge(turb[['site_id', 'date', 'turbidity']], on=['site_id', 'date'], how='inner')

for metal in ['Pb', 'Cd', 'Cu', 'Zn']:
    sub = merged[merged['metal'] == metal].dropna(subset=['turbidity', 'rel_diff_pct'])
    if len(sub) < 3:
        continue
    r, p = stats.pearsonr(sub['turbidity'], sub['rel_diff_pct'])
    turb_results[metal] = {
        'metal': metal,
        'n': int(len(sub)),
        'pearson_r': round(float(r), 4),
        'p_value': round(float(p), 6),
        'significant': bool(p < 0.05),
        'interpretation': (
            'Strong positive correlation — turbidity significantly affects sensor accuracy'
            if abs(r) > 0.5 and p < 0.05 else
            'Weak or no significant correlation — turbidity has limited effect on sensor accuracy'
        )
    }

print("\n=== TURBIDITY EFFECT ON SENSOR ACCURACY ===")
for k, v in turb_results.items():
    print(f"{k:4s}  n={v['n']:3d}  r={v['pearson_r']:6.3f}  p={v['p_value']:.4f}  "
          f"{'SIGNIFICANT' if v['significant'] else 'not significant'}")

# ─────────────────────────────────────────────
# 7. SAVE ALL RESULTS
# ─────────────────────────────────────────────
results = {
    'generated': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
    'regression': regression_results,
    'eqs_compliance': eqs_results,
    'turbidity_effect': turb_results,
}

with open(OUT_PATH, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved to {OUT_PATH}")
