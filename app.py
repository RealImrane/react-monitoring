import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import os

st.set_page_config(
    page_title="REACT — Heavy Metal Monitoring",
    page_icon="\U0001f30a",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR   = os.path.dirname(__file__)
DATA_DIR   = os.path.join(BASE_DIR, 'data')
STATS_PATH = os.path.join(DATA_DIR, 'analysis_results.json')

SITE_COLOURS = {
    'SP1': '#2196F3', 'SP2': '#4CAF50',
    'SP3': '#FF9800', 'SP4': '#9C27B0', 'SP5': '#F44336'
}
METAL_COLOURS = {
    'Pb': '#E53935', 'Cd': '#8E24AA',
    'Cu': '#F4511E', 'Zn': '#039BE5'
}

@st.cache_data
def load_sites():
    return pd.read_csv(os.path.join(DATA_DIR, 'sites.csv'))

@st.cache_data
def load_measurements():
    m   = pd.read_csv(os.path.join(DATA_DIR, 'measurements.csv'))
    se  = pd.read_csv(os.path.join(DATA_DIR, 'sampling_events.csv'))
    s   = pd.read_csv(os.path.join(DATA_DIR, 'sites.csv'))
    c   = pd.read_csv(os.path.join(DATA_DIR, 'contaminants.csv'))
    df  = m.merge(se, on='event_id')
    df  = df.merge(s, on='site_id')
    df  = df.merge(c, left_on='contaminant_id', right_on='contaminant_id')
    df  = df.rename(columns={
        'contaminant_id': 'metal',
        'contaminant_name': 'metal_name',
        'fraction_id': 'fraction',
        'method_id': 'method',
        'value_ug_l': 'value'
    })
    df['date'] = pd.to_datetime(df['date'])
    return df

@st.cache_data
def load_env_readings():
    er = pd.read_csv(os.path.join(DATA_DIR, 'environmental_readings.csv'))
    se = pd.read_csv(os.path.join(DATA_DIR, 'sampling_events.csv'))
    p  = pd.read_csv(os.path.join(DATA_DIR, 'parameters.csv'))
    df = er.merge(se, on='event_id').merge(p, on='parameter_id')
    df['date'] = pd.to_datetime(df['date'])
    return df

@st.cache_data
def load_metadata():
    df = pd.read_csv(os.path.join(DATA_DIR, 'metadata.csv'))
    return dict(zip(df['key'], df['value']))

@st.cache_data
def load_stats():
    if not os.path.exists(STATS_PATH):
        return None
    with open(STATS_PATH) as f:
        return json.load(f)

# ── SIDEBAR ──────────────────────────────────
st.sidebar.title("REACT Project")
st.sidebar.caption("Heavy Metal Monitoring Dashboard\niMERMAID Horizon Europe FSTP")
st.sidebar.divider()

page = st.sidebar.radio("Navigation", [
    "\U0001f5fa\ufe0f Site Map",
    "\U0001f4c8 Time Series",
    "\U0001f52c Sensor vs Lab",
    "\U0001f4ca Site Comparison",
    "\u26a0\ufe0f EQS Compliance",
    "\U0001f4c9 Statistical Analysis",
    "\u2139\ufe0f About"
])

st.sidebar.divider()
st.sidebar.subheader("Filters")

sites  = load_sites()
df_all = load_measurements()

sel_sites  = st.sidebar.multiselect("Sites",    sorted(df_all['site_id'].unique()),  default=sorted(df_all['site_id'].unique()))
sel_metals = st.sidebar.multiselect("Metals",   sorted(df_all['metal'].unique()),    default=sorted(df_all['metal'].unique()))
sel_frac   = st.sidebar.multiselect("Fraction", sorted(df_all['fraction'].unique()), default=sorted(df_all['fraction'].unique()))
sel_method = st.sidebar.multiselect("Method",   sorted(df_all['method'].unique()),   default=sorted(df_all['method'].unique()))

date_min  = df_all['date'].min().date()
date_max  = df_all['date'].max().date()
sel_dates = st.sidebar.date_input("Date range", value=(date_min, date_max), min_value=date_min, max_value=date_max)

df = df_all.copy()
if sel_sites:   df = df[df['site_id'].isin(sel_sites)]
if sel_metals:  df = df[df['metal'].isin(sel_metals)]
if sel_frac:    df = df[df['fraction'].isin(sel_frac)]
if sel_method:  df = df[df['method'].isin(sel_method)]
if len(sel_dates) == 2:
    df = df[(df['date'].dt.date >= sel_dates[0]) & (df['date'].dt.date <= sel_dates[1])]

# ── SITE MAP ──────────────────────────────────
if page == "\U0001f5fa\ufe0f Site Map":
    st.title("\U0001f5fa\ufe0f Sampling Site Map")
    st.caption("Five monitoring locations around the former Brskovo mining site, Montenegro")
    fig = px.scatter_mapbox(
        sites, lat='latitude', lon='longitude',
        color='site_id', color_discrete_map=SITE_COLOURS,
        hover_name='site_name',
        hover_data={'matrix_type': True, 'description': True, 'latitude': False, 'longitude': False},
        size_max=20, zoom=12, mapbox_style='carto-positron', height=550
    )
    fig.update_traces(marker=dict(size=16))
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("Site Details")
    display = sites[['site_id','site_name','matrix_type','latitude','longitude','description']].copy()
    display.columns = ['Site ID','Name','Matrix Type','Latitude','Longitude','Description']
    st.dataframe(display, use_container_width=True, hide_index=True)

# ── TIME SERIES ───────────────────────────────
elif page == "\U0001f4c8 Time Series":
    st.title("\U0001f4c8 Concentration Over Time")
    if df.empty:
        st.warning("No data matches the current filters.")
    else:
        fig = px.line(
            df.sort_values('date'),
            x='date', y='value',
            color='site_id', line_dash='method',
            color_discrete_map=SITE_COLOURS,
            facet_col='metal', facet_row='fraction',
            log_y=True,
            labels={'value': 'Concentration (µg/L)', 'date': 'Date'},
            height=600, markers=True
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Solid lines = ICP-MS (lab) · Dashed lines = HMS (sensor) · Log scale applied")

# ── SENSOR VS LAB ─────────────────────────────
elif page == "\U0001f52c Sensor vs Lab":
    st.title("\U0001f52c Sensor vs ICP-MS Comparison")
    paired = df.pivot_table(
        index=['site_id','date','metal','fraction'],
        columns='method', values='value'
    ).reset_index()
    paired.columns.name = None
    paired = paired.dropna(subset=['ICP-MS','HMS'])
    if paired.empty:
        st.warning("No paired measurements found for current filters.")
    else:
        fig = px.scatter(
            paired, x='ICP-MS', y='HMS',
            color='metal', symbol='site_id',
            color_discrete_map=METAL_COLOURS,
            log_x=True, log_y=True,
            labels={'ICP-MS':'ICP-MS Value (µg/L)', 'HMS':'HMS Sensor Value (µg/L)'},
            hover_data=['site_id','fraction'],
            height=550
        )
        min_val = max(paired[['ICP-MS','HMS']].min().min(), 0.001)
        max_val = paired[['ICP-MS','HMS']].max().max()
        fig.add_trace(go.Scatter(
            x=[min_val, max_val], y=[min_val, max_val],
            mode='lines', name='1:1 Perfect Agreement',
            line=dict(color='gray', dash='dash', width=1.5)
        ))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Dots on the dashed line = perfect agreement · Above = sensor overestimates · Below = underestimates")

# ── SITE COMPARISON ───────────────────────────
elif page == "\U0001f4ca Site Comparison":
    st.title("\U0001f4ca Site Comparison")
    if df.empty:
        st.warning("No data matches the current filters.")
    else:
        avg = df.groupby(['site_id','metal','method'])['value'].mean().reset_index()
        avg.columns = ['Site','Metal','Method','Average Concentration (µg/L)']
        fig = px.bar(
            avg, x='Site', y='Average Concentration (µg/L)',
            color='Metal', barmode='group', facet_col='Method',
            color_discrete_map=METAL_COLOURS, height=500, log_y=True
        )
        st.plotly_chart(fig, use_container_width=True)
        pivot = avg.pivot_table(
            index=['Site','Metal'], columns='Method',
            values='Average Concentration (µg/L)'
        ).reset_index()
        st.dataframe(pivot.round(3), use_container_width=True, hide_index=True)

# ── EQS COMPLIANCE ────────────────────────────
elif page == "\u26a0\ufe0f EQS Compliance":
    st.title("\u26a0\ufe0f EQS Compliance — EU Water Framework Directive")
    st.info("Comparison against Environmental Quality Standards (Directive 2013/39/EU). ICP-MS dissolved fraction used.")
    stats_data = load_stats()
    if not stats_data:
        st.error("Run analysis.py first to generate results.")
    else:
        rows = []
        for k, v in stats_data['eqs_compliance'].items():
            rows.append({
                'Site': v['site'], 'Metal': v['metal'],
                'Mean (µg/L)': v['mean_ug_l'], 'Max (µg/L)': v['max_ug_l'],
                'AA-EQS (µg/L)': v['aa_eqs'] or '—',
                'AA Status': v['aa_status'] or 'No standard',
                'MAC-EQS (µg/L)': v['mac_eqs'] or '—',
                'MAC Status': v['mac_status'] or 'No standard',
            })
        eqs_df = pd.DataFrame(rows)
        def colour_status(val):
            if val == 'EXCEEDS':   return 'background-color: #ffcccc; color: #cc0000; font-weight: bold'
            if val == 'COMPLIANT': return 'background-color: #ccffcc; color: #006600'
            return ''
        styled = eqs_df.style.applymap(colour_status, subset=['AA Status','MAC Status'])
        st.dataframe(styled, use_container_width=True, hide_index=True)
        st.caption("AA-EQS = Annual Average · MAC-EQS = Maximum Allowable Concentration")

# ── STATISTICAL ANALYSIS ──────────────────────
elif page == "\U0001f4c9 Statistical Analysis":
    st.title("\U0001f4c9 Statistical Analysis")
    stats_data = load_stats()
    if not stats_data:
        st.error("Run analysis.py first to generate results.")
    else:
        tab1, tab2 = st.tabs(["Sensor Validation (KPIs)", "Turbidity Effect"])
        with tab1:
            st.subheader("Sensor vs ICP-MS Regression Results")
            rows = []
            for k, v in stats_data['regression'].items():
                rows.append({
                    'Metal': v['metal'], 'Fraction': v['fraction'],
                    'n': v['n'], 'R²': v['r2'],
                    'Slope': v['slope'], 'Intercept': v['intercept'],
                    'RMSE (µg/L)': v['rmse'], 'Bias (µg/L)': v['bias'],
                    'KPI-3 (R²≥0.85)': '✅ PASS' if v['kpi3_pass'] else '❌ FAIL',
                })
            reg_df = pd.DataFrame(rows)
            st.dataframe(reg_df, use_container_width=True, hide_index=True)
            fig = px.bar(
                reg_df, x='Metal', y='R²', color='Fraction',
                barmode='group', range_y=[0, 1.05],
                title='R² by Metal and Fraction', height=400
            )
            fig.add_hline(y=0.85, line_dash='dash', line_color='red',
                         annotation_text='KPI-3 threshold (R²=0.85)')
            st.plotly_chart(fig, use_container_width=True)
        with tab2:
            st.subheader("Turbidity Effect on Sensor Accuracy")
            rows = []
            for k, v in stats_data['turbidity_effect'].items():
                rows.append({
                    'Metal': v['metal'], 'n': v['n'],
                    'Pearson r': v['pearson_r'], 'p-value': v['p_value'],
                    'Significant (p<0.05)': '⚠️ Yes' if v['significant'] else 'No',
                    'Interpretation': v['interpretation']
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            env = load_env_readings()
            turb_data = env[env['parameter_name'] == 'Turbidity'][['site_id','date','value_numeric']].copy()
            turb_data.columns = ['site_id','date','turbidity']
            paired = df_all[df_all['fraction']=='dissolved'].pivot_table(
                index=['site_id','date','metal'], columns='method', values='value'
            ).reset_index()
            paired.columns.name = None
            paired = paired.dropna(subset=['ICP-MS','HMS'])
            paired['rel_diff_pct'] = np.abs(paired['HMS'] - paired['ICP-MS']) / paired['ICP-MS'] * 100
            merged = paired.merge(turb_data, on=['site_id','date'])
            if not merged.empty:
                fig = px.scatter(
                    merged, x='turbidity', y='rel_diff_pct',
                    color='metal', color_discrete_map=METAL_COLOURS,
                    labels={'turbidity':'Turbidity (NTU)', 'rel_diff_pct':'Relative Difference HMS vs ICP-MS (%)'},
                    trendline='ols', height=450,
                    title='Turbidity vs Sensor-Lab Relative Difference'
                )
                st.plotly_chart(fig, use_container_width=True)

# ── ABOUT ─────────────────────────────────────
elif page == "\u2139\ufe0f About":
    st.title("\u2139\ufe0f About This Dashboard")
    meta = load_metadata()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Project")
        st.markdown(f"""
        **Title:** {meta.get('title','')}
        **Project:** {meta.get('project','')}
        **Programme:** {meta.get('programme','')}
        **Creator:** {meta.get('creator','')}
        **Period:** {meta.get('start_date','')} to {meta.get('end_date','')}
        """)
    with col2:
        st.subheader("Data & Methods")
        st.markdown(f"""
        **Parameters:** {meta.get('parameters','')}
        **Methods:** {meta.get('methods','')}
        **BDL handling:** {meta.get('bdl_handling','')}
        **License:** {meta.get('license','')}
        **DB Version:** {meta.get('version','')}
        """)
    st.divider()
    st.subheader("FAIR Compliance")
    col3, col4, col5, col6 = st.columns(4)
    col3.success(f"**Findable**\n\n{meta.get('fair_findable','')}")
    col4.success(f"**Accessible**\n\n{meta.get('fair_accessible','')}")
    col5.success(f"**Interoperable**\n\n{meta.get('fair_interoperable','')}")
    col6.success(f"**Reusable**\n\n{meta.get('fair_reusable','')}")
