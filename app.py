import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import json
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="REACT — Heavy Metal Monitoring",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR  = os.path.dirname(__file__)
DB_PATH   = os.path.join(BASE_DIR, 'data', 'REACT_v3.db')
STATS_PATH = os.path.join(BASE_DIR, 'data', 'analysis_results.json')

SITE_COLOURS = {
    'SP1': '#2196F3', 'SP2': '#4CAF50',
    'SP3': '#FF9800', 'SP4': '#9C27B0', 'SP5': '#F44336'
}
METAL_COLOURS = {
    'Pb': '#E53935', 'Cd': '#8E24AA',
    'Cu': '#F4511E', 'Zn': '#039BE5'
}

# ─────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────
def get_conn():
    if not os.path.exists(DB_PATH):
        st.error(f"Database file not found. Expected path: {DB_PATH}")
        st.stop()
    return sqlite3.connect(DB_PATH, check_same_thread=False)

@st.cache_data
def load_sites():
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM sites", conn)
    conn.close()
    return df

@st.cache_data
def load_measurements():
    query = """
    SELECT
        se.site_id, s.site_name, s.latitude, s.longitude, s.matrix_type,
        se.date, se.ceti_protocol_no,
        m.contaminant_id AS metal, c.contaminant_name AS metal_name,
        m.fraction_id AS fraction,
        m.method_id AS method,
        m.value_ug_l AS value,
        m.is_bdl
    FROM measurements m
    JOIN sampling_events se  ON m.event_id       = se.event_id
    JOIN sites s             ON se.site_id        = s.site_id
    JOIN contaminants c      ON m.contaminant_id  = c.contaminant_id
    ORDER BY se.date, se.site_id
    """
    conn = get_conn()
    df = pd.read_sql(query, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df

@st.cache_data
def load_env_readings():
    query = """
    SELECT se.site_id, se.date, p.parameter_name, p.unit, p.category,
           er.value_numeric, er.value_text
    FROM environmental_readings er
    JOIN sampling_events se ON er.event_id    = se.event_id
    JOIN parameters p       ON er.parameter_id = p.parameter_id
    """
    conn = get_conn()
    df = pd.read_sql(query, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df

@st.cache_data
def load_stats():
    if not os.path.exists(STATS_PATH):
        return None
    with open(STATS_PATH) as f:
        return json.load(f)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/Flag_of_Europe.svg/320px-Flag_of_Europe.svg.png", width=80)
st.sidebar.title("REACT Project")
st.sidebar.caption("Heavy Metal Monitoring Dashboard\niMERMAID Horizon Europe FSTP")
st.sidebar.divider()

page = st.sidebar.radio("Navigation", [
    "🗺️ Site Map",
    "📈 Time Series",
    "🔬 Sensor vs Lab",
    "📊 Site Comparison",
    "⚠️ EQS Compliance",
    "📉 Statistical Analysis",
    "ℹ️ About"
])

st.sidebar.divider()
st.sidebar.subheader("Filters")

df_all = load_measurements()
sites  = load_sites()

sel_sites   = st.sidebar.multiselect("Sites",   sorted(df_all['site_id'].unique()),   default=sorted(df_all['site_id'].unique()))
sel_metals  = st.sidebar.multiselect("Metals",  sorted(df_all['metal'].unique()),     default=sorted(df_all['metal'].unique()))
sel_frac    = st.sidebar.multiselect("Fraction",sorted(df_all['fraction'].unique()),  default=sorted(df_all['fraction'].unique()))
sel_method  = st.sidebar.multiselect("Method",  sorted(df_all['method'].unique()),    default=sorted(df_all['method'].unique()))

date_min = df_all['date'].min().date()
date_max = df_all['date'].max().date()
sel_dates = st.sidebar.date_input("Date range", value=(date_min, date_max), min_value=date_min, max_value=date_max)

# Apply filters
df = df_all.copy()
if sel_sites:   df = df[df['site_id'].isin(sel_sites)]
if sel_metals:  df = df[df['metal'].isin(sel_metals)]
if sel_frac:    df = df[df['fraction'].isin(sel_frac)]
if sel_method:  df = df[df['method'].isin(sel_method)]
if len(sel_dates) == 2:
    df = df[(df['date'].dt.date >= sel_dates[0]) & (df['date'].dt.date <= sel_dates[1])]

# ─────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────

# ── Site Map ──────────────────────────────────
if page == "🗺️ Site Map":
    st.title("🗺️ Sampling Site Map")
    st.caption("Five monitoring locations around the former Brskovo mining site, Montenegro")

    site_stats = df.groupby(['site_id','metal'])['value'].mean().reset_index()
    site_stats = site_stats.merge(sites[['site_id','site_name','latitude','longitude','matrix_type','description']], on='site_id')

    fig = px.scatter_mapbox(
        sites, lat='latitude', lon='longitude',
        color='site_id', color_discrete_map=SITE_COLOURS,
        hover_name='site_name',
        hover_data={'matrix_type': True, 'description': True, 'latitude': False, 'longitude': False},
        size_max=20, zoom=12,
        mapbox_style='carto-positron',
        height=550
    )
    fig.update_traces(marker=dict(size=16))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Site Details")
    display_sites = sites[['site_id','site_name','matrix_type','latitude','longitude','description']].copy()
    display_sites.columns = ['Site ID','Name','Matrix Type','Latitude','Longitude','Description']
    st.dataframe(display_sites, use_container_width=True, hide_index=True)

# ── Time Series ───────────────────────────────
elif page == "📈 Time Series":
    st.title("📈 Concentration Over Time")

    if df.empty:
        st.warning("No data matches the current filters.")
    else:
        df['site_method'] = df['site_id'] + ' — ' + df['method']
        fig = px.line(
            df.sort_values('date'),
            x='date', y='value',
            color='site_id', line_dash='method',
            color_discrete_map=SITE_COLOURS,
            facet_col='metal', facet_row='fraction',
            log_y=True,
            labels={'value': 'Concentration (µg/L)', 'date': 'Date'},
            height=600,
            markers=True
        )
        fig.update_layout(legend_title_text='Site')
        st.plotly_chart(fig, use_container_width=True)

        st.caption("Solid lines = ICP-MS (lab) · Dashed lines = HMS (sensor) · Log scale applied")

# ── Sensor vs Lab ─────────────────────────────
elif page == "🔬 Sensor vs Lab":
    st.title("🔬 Sensor vs ICP-MS Comparison")

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
            hover_data=['site_id','date','fraction'],
            height=550
        )
        # 1:1 reference line
        min_val = max(paired[['ICP-MS','HMS']].min().min(), 0.001)
        max_val = paired[['ICP-MS','HMS']].max().max()
        fig.add_trace(go.Scatter(
            x=[min_val, max_val], y=[min_val, max_val],
            mode='lines', name='1:1 Perfect Agreement',
            line=dict(color='gray', dash='dash', width=1.5)
        ))
        fig.update_layout(legend_title_text='Metal / Site')
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Dots on the dashed line = perfect sensor-lab agreement · Above = sensor overestimates · Below = underestimates")

# ── Site Comparison ───────────────────────────
elif page == "📊 Site Comparison":
    st.title("📊 Site Comparison")

    if df.empty:
        st.warning("No data matches the current filters.")
    else:
        avg = df.groupby(['site_id','metal','method'])['value'].mean().reset_index()
        avg.columns = ['Site','Metal','Method','Average Concentration (µg/L)']

        fig = px.bar(
            avg, x='Site', y='Average Concentration (µg/L)',
            color='Metal', barmode='group',
            facet_col='Method',
            color_discrete_map=METAL_COLOURS,
            height=500,
            log_y=True
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Summary Table")
        pivot = avg.pivot_table(
            index=['Site','Metal'], columns='Method',
            values='Average Concentration (µg/L)'
        ).reset_index()
        st.dataframe(pivot.round(3), use_container_width=True, hide_index=True)

# ── EQS Compliance ────────────────────────────
elif page == "⚠️ EQS Compliance":
    st.title("⚠️ EQS Compliance — EU Water Framework Directive")
    st.info("Comparison against Environmental Quality Standards (Directive 2013/39/EU). ICP-MS dissolved fraction used as the regulatory measurement.")

    stats_data = load_stats()
    if not stats_data:
        st.error("Run analysis.py first to generate results.")
    else:
        eqs = stats_data['eqs_compliance']
        rows = []
        for k, v in eqs.items():
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
        st.caption("AA-EQS = Annual Average · MAC-EQS = Maximum Allowable Concentration · Cu and Zn follow national standards not listed here")

# ── Statistical Analysis ──────────────────────
elif page == "📉 Statistical Analysis":
    st.title("📉 Statistical Analysis")

    stats_data = load_stats()
    if not stats_data:
        st.error("Run analysis.py first to generate results.")
    else:
        tab1, tab2 = st.tabs(["Sensor Validation (KPIs)", "Turbidity Effect"])

        with tab1:
            st.subheader("Sensor vs ICP-MS Regression Results")
            st.caption(f"Generated: {stats_data['generated']}")

            reg = stats_data['regression']
            rows = []
            for k, v in reg.items():
                rows.append({
                    'Metal': v['metal'], 'Fraction': v['fraction'],
                    'n': v['n'], 'R²': v['r2'],
                    'Slope': v['slope'], 'Intercept': v['intercept'],
                    'RMSE (µg/L)': v['rmse'], 'Bias (µg/L)': v['bias'],
                    'KPI-3 (R²≥0.85)': '✅ PASS' if v['kpi3_pass'] else '❌ FAIL',
                    'KPI-4 (bias≤30%)': '✅ PASS' if v.get('kpi4_pass') else '❌ FAIL' if v.get('kpi4_pass') is False else '—',
                })
            reg_df = pd.DataFrame(rows)
            st.dataframe(reg_df, use_container_width=True, hide_index=True)

            # R² bar chart
            fig = px.bar(
                reg_df, x='Metal', y='R²', color='Fraction',
                barmode='group', range_y=[0, 1.05],
                title='R² by Metal and Fraction',
                height=400
            )
            fig.add_hline(y=0.85, line_dash='dash', line_color='red',
                         annotation_text='KPI-3 threshold (R²=0.85)')
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("Turbidity Effect on Sensor Accuracy")
            turb = stats_data['turbidity_effect']
            rows = []
            for k, v in turb.items():
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
                    trendline='ols',
                    height=450,
                    title='Turbidity vs Sensor-Lab Relative Difference'
                )
                st.plotly_chart(fig, use_container_width=True)

# ── About ─────────────────────────────────────
elif page == "ℹ️ About":
    st.title("ℹ️ About This Dashboard")

    conn = get_conn()
    meta = dict(pd.read_sql("SELECT key, value FROM metadata", conn).values)
    conn.close()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Project")
        st.markdown(f"""
        **Title:** {meta.get('title','')}

        **Project:** {meta.get('project','')}

        **Programme:** {meta.get('programme','')}

        **Creator:** {meta.get('creator','')}

        **Period:** {meta.get('start_date','')} → {meta.get('end_date','')}
        """)
    with col2:
        st.subheader("Data & Methods")
        st.markdown(f"""
        **Parameters:** {meta.get('parameters','')}

        **Methods:** {meta.get('methods','')}

        **Units:** {meta.get('units','')}

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
