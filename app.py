import streamlit as st
import pandas as pd
import plotly.express as px
import google.generativeai as genai
import os
import json
from datetime import datetime
from dotenv import load_dotenv

import auto_analyst
import data_cleaner
import geo_maps
from google_sheets import SheetAccessError, load_workbook, service_account_email

# 1. Load API Key
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini AI
if API_KEY:
    genai.configure(api_key=API_KEY)

# Page Configuration
st.set_page_config(page_title="AI Smart Dashboard", layout="wide", page_icon="📊")

# --- UPDATED SMART DATA CLEANING FUNCTION ---
def auto_fix_headers(df):
    unnamed_cols = [col for col in df.columns if "Unnamed" in str(col)]
    
    if len(unnamed_cols) / len(df.columns) > 0.4:
        max_non_nulls = 0
        best_row_idx = -1
        
        for i in range(min(10, len(df))):
            valid_count = df.iloc[i].notna().sum()
            if valid_count > max_non_nulls:
                max_non_nulls = valid_count
                best_row_idx = i
                
        if best_row_idx != -1:
            new_headers = df.iloc[best_row_idx]
            df = df.iloc[best_row_idx + 1:].reset_index(drop=True)
            df.columns = new_headers
            
    clean_cols = []
    for i, col in enumerate(df.columns):
        if pd.isna(col) or str(col).strip() == "" or "Unnamed" in str(col):
            clean_cols.append(f"Column_{i+1}")
        else:
            clean_cols.append(str(col).strip().replace('\n', ' '))
    
    df.columns = clean_cols
    df = df.dropna(how='all', axis=1).dropna(how='all', axis=0)
    
    df = df.infer_objects()
    # A stray date or note in a numeric column used to leave the whole column as
    # text, which silently dropped it from every chart. See data_cleaner.
    return data_cleaner.coerce_numeric_columns(df)

# --- HELPER FUNCTION: POWER BI STYLE DYNAMIC DASHBOARD ---
def generate_dashboard(dataframe, key_prefix, is_compare_mode=False):
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(label="📊 Total Records", value=f"{len(dataframe):,}")
    kpi2.metric(label="📋 Total Columns", value=len(dataframe.columns))
    kpi3.metric(label="⚠️ Missing Data (Nulls)", value=dataframe.isna().sum().sum())
    kpi4.metric(label="✨ Unique Categories", value=len(dataframe.iloc[:,0].unique()) if not dataframe.empty else 0)
    
    st.markdown("<hr style='border: 1px solid #e6e6e6;'>", unsafe_allow_html=True)
    
    cat_cols = dataframe.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    num_cols = dataframe.select_dtypes(include=['number']).columns.tolist()
    
    if not cat_cols:
        st.warning("Needs at least one text column to build visual charts.")
        return

    st.write("### 🎛️ Dashboard Slicers (Customize Your View)")
    filter1, filter2 = st.columns(2)
    
    with filter1:
        default_x = 'Source_Sheet' if is_compare_mode and 'Source_Sheet' in dataframe.columns else cat_cols[0]
        try:
            default_index = cat_cols.index(default_x)
        except:
            default_index = 0
        x_axis = st.selectbox("Select Dimension (X-Axis)", cat_cols, index=default_index, key=f"x_{key_prefix}")
        
    with filter2:
        y_options = ["Count (Frequency)"] + num_cols
        y_axis = st.selectbox("Select Metric (Y-Axis)", y_options, key=f"y_{key_prefix}")

    chart1, chart2 = st.columns(2)
    
    with chart1:
        if y_axis == "Count (Frequency)":
            chart_data = dataframe[x_axis].value_counts().reset_index().head(20)
            chart_data.columns = [x_axis, 'Count']
            fig1 = px.bar(chart_data, x=x_axis, y='Count', title=f"Volume by {x_axis}", color=x_axis, text_auto=True)
        else:
            chart_data = dataframe.groupby(x_axis)[y_axis].sum().reset_index().head(20)
            fig1 = px.bar(chart_data, x=x_axis, y=y_axis, title=f"Sum of {y_axis} by {x_axis}", color=x_axis, text_auto=True)
        
        fig1.update_layout(xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig1, use_container_width=True, key=f"mainbar_{key_prefix}")
        
    with chart2:
        fig2 = px.pie(dataframe, names=x_axis, title=f"Market Share: {x_axis}", hole=0.4)
        fig2.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig2, use_container_width=True, key=f"mainpie_{key_prefix}")
        
    # --- SMART GEOGRAPHICAL MAP LOGIC (see geo_maps.py) ---
    geo_maps.render_geo_section(dataframe, cat_cols, y_axis, key_prefix)


# --- DATA SOURCE 1: FILE UPLOAD ---
def file_upload_panel():
    """Classic upload flow. Returns {sheet_name: raw DataFrame} or None."""
    uploaded_file = st.file_uploader("Upload your Excel or CSV file here", type=['csv', 'xlsx'])

    if uploaded_file is None:
        return None

    if uploaded_file.name.endswith('.xlsx'):
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

        mode = st.radio("📑 Choose View Mode:", ["Specific Sheets (Custom Select)", "All Sheets (Combine All)"], horizontal=True)
        sheets_to_process = sheet_names if mode == "All Sheets (Combine All)" else st.multiselect("☑️ Select sheets to process:", sheet_names, default=[sheet_names[0]])

        if not sheets_to_process:
            return None

        return {sheet: xls.parse(sheet) for sheet in sheets_to_process}

    return {uploaded_file.name: pd.read_csv(uploaded_file)}


# --- DATA SOURCE 2: GOOGLE SHEETS LIVE SYNC ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_google_workbook(url_or_id, creds_json, refresh_token):
    """Cached sheet fetch (5 min TTL). `refresh_token` lets the UI force a re-sync."""
    return load_workbook(url_or_id, creds_json)


def get_service_account_json():
    """Service account key: .streamlit/secrets.toml first, then a manual upload."""
    try:
        if "gcp_service_account" in st.secrets:
            return json.dumps(dict(st.secrets["gcp_service_account"]))
    except Exception:
        pass  # secrets.toml is optional - fall through to the uploaded key
    return st.session_state.get("gs_creds_json")


def google_sheets_panel():
    """Live sync flow. Returns {worksheet_name: raw DataFrame} or None."""
    url_col, btn_col = st.columns([4, 1])

    with url_col:
        sheet_url = st.text_input(
            "Google Sheet link",
            placeholder="https://docs.google.com/spreadsheets/d/your-sheet-id/edit",
            key="gs_url",
            label_visibility="collapsed",
        )
    with btn_col:
        sync_clicked = st.button("🔄 Sync Now", use_container_width=True, type="primary")

    with st.expander("🔒 Private sheet? Connect a Google Service Account (optional)"):
        st.caption(
            "Sheets shared as **Anyone with the link** need nothing here. "
            "For private sheets, upload a service account JSON key and share the sheet with its email."
        )
        creds_file = st.file_uploader("Service account JSON key", type=["json"], key="gs_creds_file")
        if creds_file is not None:
            st.session_state["gs_creds_json"] = creds_file.getvalue().decode("utf-8")

        loaded_creds = get_service_account_json()
        if loaded_creds:
            email = service_account_email(loaded_creds)
            if email:
                st.success(f"Service account ready: `{email}`")
                st.caption("Share your sheet with this email as **Viewer**, then hit Sync Now.")
            else:
                st.error("That file is not a valid service account key. Download a fresh JSON key from Google Cloud Console.")

    if sync_clicked:
        if not sheet_url.strip():
            st.warning("Paste a Google Sheet link first.")
        else:
            st.session_state["gs_active_url"] = sheet_url.strip()
            st.session_state["gs_refresh_token"] = st.session_state.get("gs_refresh_token", 0) + 1
            st.session_state["gs_synced_at"] = datetime.now()

    active_url = st.session_state.get("gs_active_url")
    if not active_url:
        st.info("💡 Paste a Google Sheet link and hit **Sync Now** — every tab of the sheet becomes its own dashboard.")
        return None

    try:
        with st.spinner("Fetching live data from Google Sheets..."):
            workbook = fetch_google_workbook(
                active_url,
                get_service_account_json(),
                st.session_state.get("gs_refresh_token", 0),
            )
    except SheetAccessError as e:
        st.error(f"❌ {e}")
        if e.hint:
            st.info(f"👉 {e.hint}")
        return None
    except Exception as e:
        st.error(f"❌ Unexpected error while syncing: {e}")
        return None

    synced_at = st.session_state.get("gs_synced_at")
    stamp = synced_at.strftime("%d %b %Y, %I:%M:%S %p") if synced_at else "just now"
    st.success(f"✅ Live sync active · {len(workbook)} worksheet(s) loaded · Last synced: {stamp}")

    worksheet_names = list(workbook.keys())
    if len(worksheet_names) > 1:
        mode = st.radio("📑 Choose View Mode:", ["Specific Sheets (Custom Select)", "All Sheets (Combine All)"], horizontal=True, key="gs_mode")
        selected = worksheet_names if mode == "All Sheets (Combine All)" else st.multiselect("☑️ Select worksheets to process:", worksheet_names, default=[worksheet_names[0]], key="gs_pick")
    else:
        selected = worksheet_names

    if not selected:
        return None

    return {name: workbook[name] for name in selected}


# --- AI HELPERS ---
def run_ai_briefing(profile_text):
    """Ask Gemini what a senior analyst would look at first in this dataset."""
    if not API_KEY or not selected_model:
        st.warning("Connect a Gemini API key in the sidebar to get the AI briefing.")
        return

    prompt = f"""
    You are a Senior Data Analyst briefing a business owner who has just opened this dashboard.
    Below is a statistical profile of their dataset (no raw rows, only column stats).

    {profile_text}

    Write a sharp, specific briefing with these sections:
    1. **What this data actually is** - one paragraph, inferred from the column names and values.
    2. **The 3 things to look at first** - name the exact columns and say what to check and why.
    3. **Risks in the data** - missing values, skew, duplicates, anything that could mislead.
    4. **Business questions this data can answer** - 4 concrete questions, each tied to real columns.
    5. **What is missing** - which extra column would unlock the most additional insight.

    Be concrete, reference real column names, and avoid generic filler advice.
    """

    try:
        model = genai.GenerativeModel(selected_model)
        st.markdown(model.generate_content(prompt).text)
    except Exception as e:
        st.error(f"AI briefing failed: {e}")


# --- CLEANING REPORT ---
def render_cleaning_panel(reports):
    """Tell the user exactly which rows were used and which were skipped."""
    if not reports:
        return

    rows_kept = sum(report.get('rows_after', 0) for report in reports.values())
    rows_skipped = sum(report.get('rows_removed', 0) for report in reports.values())

    header = f"🧹 Data cleaned — using {rows_kept:,} row(s) that actually contain data"
    if rows_skipped:
        header += f" ({rows_skipped:,} empty or junk row(s) skipped)"

    with st.expander(header, expanded=bool(rows_skipped)):
        for name, report in reports.items():
            if len(reports) > 1:
                st.markdown(f"**Sheet: {name}**")

            st.caption(
                f"Sheet had **{report['rows_before']:,} row(s)** · "
                f"charts are built on **{report['rows_after']:,} row(s)** × "
                f"{report['columns_after']} column(s)"
            )

            lines = data_cleaner.report_lines(report)
            if lines:
                for line in lines:
                    st.markdown(f"- {line}")
            else:
                st.markdown("- Nothing needed cleaning — this sheet was already tidy. ✅")


# --- WORKSPACE RENDERER (tabs + master comparison) ---
def build_master_df(dict_of_dfs):
    """One combined frame across sheets, tagged with Source_Sheet when relevant."""
    names = list(dict_of_dfs.keys())

    if len(names) == 1:
        return dict_of_dfs[names[0]]

    tagged = []
    for name in names:
        frame = dict_of_dfs[name].copy()
        frame['Source_Sheet'] = name
        tagged.append(frame)

    return pd.concat(tagged, ignore_index=True)


def render_workspace(dict_of_dfs, key_prefix):
    """Render one dashboard per sheet plus the master comparison. Returns master_df."""
    names = list(dict_of_dfs.keys())

    if len(names) == 1:
        master_df = dict_of_dfs[names[0]]
        generate_dashboard(master_df, key_prefix=f"{key_prefix}_single", is_compare_mode=False)
        st.divider()
        return master_df

    master_df = build_master_df(dict_of_dfs)

    st.header("📄 Sheet Dashboards")
    tabs = st.tabs(names)

    for i, tab in enumerate(tabs):
        with tab:
            generate_dashboard(dict_of_dfs[names[i]], key_prefix=f"{key_prefix}_tab_{i}", is_compare_mode=False)

    st.divider()

    st.header("⚖️ Master Comparison")
    if st.checkbox(f"📊 Compare all {len(names)} selected sheets", key=f"cmp_{key_prefix}"):
        st.info("💡 Comparison Active: Use 'Source_Sheet' in the slicer above to compare data between tabs.")
        generate_dashboard(master_df, key_prefix=f"{key_prefix}_compare", is_compare_mode=True)

    st.divider()
    return master_df


# --- MAIN APP LOGIC ---
st.sidebar.header("⚙️ AI Settings")
selected_model = None

if API_KEY:
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        selected_model = st.sidebar.selectbox("Select AI Engine", available_models)
        st.sidebar.success("API Connected! ✅")
    except Exception as e:
        st.sidebar.error(f"Error fetching models: {e}")

st.title("🚀 AI-Powered Master Dashboard (Power BI Edition)")
st.caption("Upload a file or sync a live Google Sheet — the dashboard builds itself.")
st.divider()

data_source = st.segmented_control(
    "Data Source",
    ["📁 Upload File", "🔗 Google Sheet (Live Sync)"],
    default="📁 Upload File",
    key="data_source",
) or "📁 Upload File"

raw_sheets = file_upload_panel() if data_source == "📁 Upload File" else google_sheets_panel()

master_df = None

if raw_sheets:
    dict_of_dfs = {}
    cleaning_reports = {}

    for name, frame in raw_sheets.items():
        cleaned = auto_fix_headers(frame.copy())
        cleaned, report = data_cleaner.clean_dataframe(cleaned)
        cleaning_reports[name] = report
        if not cleaned.empty:
            dict_of_dfs[name] = cleaned

    render_cleaning_panel(cleaning_reports)

    if not dict_of_dfs:
        st.warning("Data loaded, but every sheet came out empty after cleaning. Check the source for stray formatting.")
    else:
        key_prefix = "upload" if data_source == "📁 Upload File" else "gsheet"
        master_df = build_master_df(dict_of_dfs)

        auto_tab, manual_tab = st.tabs(["🤖 Auto Analyst", "🎛️ Manual Dashboard"])

        with auto_tab:
            st.caption(
                "No axis picking needed — the data is profiled, and every dashboard it can "
                "support is built for you."
            )
            auto_analyst.render_sheet_sections(dict_of_dfs, key_prefix, ai_callback=run_ai_briefing)

        with manual_tab:
            render_workspace(dict_of_dfs, key_prefix)

if master_df is not None and not master_df.empty:
    st.header("🔬 AI Micro-Level Deep Dive Analyst")

    col_ai1, col_ai2 = st.columns([1, 2])

    with col_ai1:
        st.info("Select a specific column to instruct the AI to dig deep into that specific area.")
        target_column = st.selectbox("Select Target Column for Deep Dive:", master_df.columns)
        deep_dive_btn = st.button("🔍 Run Micro-Analysis")

    with col_ai2:
        if deep_dive_btn and API_KEY:
            with st.spinner(f"AI is deeply analyzing '{target_column}'..."):
                col_data = master_df[target_column].value_counts().head(20).to_string()
                prompt = f"""
                You are a Senior Data Analyst. The user wants a MICRO-LEVEL deep dive into the column '{target_column}'.
                Here are the top values and their counts in this column:
                {col_data}

                Provide a highly detailed, 4-point micro-analysis covering:
                1. Dominant patterns/trends.
                2. Hidden anomalies or risks.
                3. Business impact of this specific data distribution.
                4. Strategic recommendation based on this column.
                Be highly specific and avoid generic answers.
                """
                try:
                    model = genai.GenerativeModel(selected_model)
                    response = model.generate_content(prompt)
                    st.success(response.text)
                except Exception as e:
                    st.error(f"AI analysis failed: {e}")

    st.divider()
    st.subheader("💬 Custom Chat")
    user_question = st.text_input("Ask any custom question about the entire dataset...")
    if user_question and API_KEY:
        with st.spinner("Thinking..."):
            try:
                model = genai.GenerativeModel(selected_model)
                chat_prompt = f"Data overview (Columns: {', '.join(master_df.columns)}). User Question: {user_question}"
                reply = model.generate_content(chat_prompt)
                st.success(reply.text)
            except Exception as e:
                st.error(f"AI chat failed: {e}")