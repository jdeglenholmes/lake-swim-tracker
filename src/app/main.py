import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

# ==========================================
# 1. AUTHENTICATION GATEWAY
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🏊‍♂️ Lake District Tracker")
    
    with st.form("login_form"):
        swimmer_name = st.text_input("Swimmer Name")
        pwd = st.text_input("App Password", type="password")
        submitted = st.form_submit_button("Log In", use_container_width=True)
        
        if submitted:
            if pwd == st.secrets["APP_PASSWORD"] and swimmer_name.strip():
                st.session_state["logged_in"] = True
                st.session_state["swimmer"] = swimmer_name.strip()
                st.rerun()
            elif not swimmer_name.strip():
                st.error("Please enter a name.")
            else:
                st.error("Incorrect password.")
    st.stop() # Hides the rest of the app until authenticated

import json

# ==========================================
# 2. SUPABASE INIT & LAKE LOADER
# ==========================================
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase: Client = init_connection()

@st.cache_data
def load_lakes_from_db():
    response = supabase.table("lakes").select("*").execute()
    # Build the dictionary dynamically from the database rows
    return {
        row["name"]: {"length": row["target_metres"], "path": row["svg_path"]} 
        for row in response.data
    }

LAKES = load_lakes_from_db()

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def render_lake_svg(lake_name, current_m, target_m):
    lake_info = LAKES.get(lake_name, {"path": "M 0 0 L 100 100 Z"})
    path_d = lake_info["path"]
    pct = min(current_m / target_m, 1.0)
    
    if pct >= 1.0:
        svg = f'''
        <svg viewBox="0 0 100 100" width="140" height="140" style="display: block; margin: auto;">
            <path d="{path_d}" fill="#0ea5e9" stroke="#0284c7" stroke-width="2"/>
            <text x="50" y="52" text-anchor="middle" dominant-baseline="middle" fill="white" font-family="sans-serif" font-size="14" font-weight="bold">DONE</text>
        </svg>
        '''
    else:
        dash_count = 20
        completed_dashes = int(pct * dash_count)
        blue_dash_array = ("4 1 " * completed_dashes) + "0 100"
        
        svg = f'''
        <svg viewBox="0 0 100 100" width="140" height="140" style="display: block; margin: auto;">
            <path d="{path_d}" fill="none" stroke="#e2e8f0" stroke-width="3" pathLength="100" stroke-dasharray="4 1" />
            <path d="{path_d}" fill="none" stroke="#0ea5e9" stroke-width="3" pathLength="100" stroke-dasharray="{blue_dash_array}" />
        </svg>
        '''
        
    return f'''
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 15px; display: flex; flex-direction: column; align-items: center; margin-bottom: 15px;">
        {svg}
        <span style="font-family: sans-serif; font-size: 15px; font-weight: 600; margin-top: 10px; color: #1e293b;">{lake_name}</span>
        <span style="font-family: sans-serif; font-size: 13px; color: #64748b; margin-top: 2px;">{current_m:,} / {target_m:,}m</span>
    </div>
    '''

# ==========================================
# 4. MAIN UI HEADER
# ==========================================
col1, col2 = st.columns([3, 1])
col1.title(f"Welcome, {st.session_state['swimmer']}!")
if col2.button("Log Out"):
    st.session_state.clear()
    st.rerun()

view_mode = st.radio("Display Mode", ["Total Progress", "Group by Lake"], horizontal=True)

# ==========================================
# 5. DATA ENTRY FORM
# ==========================================
with st.form("log_swim", clear_on_submit=True):
    st.subheader("Log a Swim")
    
    activity_date = st.date_input("Date of Swim")
    
    c1, c2 = st.columns(2)
    lengths = c1.number_input("Lengths completed", min_value=1, step=1)
    pool_size = c2.number_input("Pool length (m)", value=25, step=1)
    
    target_lake = "Total Progress"
    if view_mode == "Group by Lake":
        target_lake = st.selectbox("Assign session to lake", list(LAKES.keys()))
        
    if st.form_submit_button("Save Entry", use_container_width=True):
        total_m = lengths * pool_size
        
        supabase.table("lake_swims").insert({
            "swimmer": st.session_state["swimmer"],
            "activity_datetime": str(activity_date),
            "pool_length_m": pool_size,
            "lengths": lengths,
            "total_metres": total_m,
            "target_lake": target_lake
        }).execute()
        
        st.success(f"Great job! {total_m}m logged.")

# ==========================================
# 6. PROGRESS TRACKING
# ==========================================
st.subheader("Your Tracker")
try:
    data = supabase.table("lake_swims").select("*").eq("swimmer", st.session_state["swimmer"]).execute().data
    df = pd.DataFrame(data)
except Exception as e:
    st.error(f"Supabase API Error Details: {e}")
    data = []

if view_mode == "Total Progress":
    total_m = df["total_metres"].sum() if not df.empty else 0
    
    target_lake_overall = st.selectbox("Select Target Lake", list(LAKES.keys()))
    target_m_overall = LAKES[target_lake_overall]["length"]
    pct_overall = min(total_m / target_m_overall, 1.0)
    
    st.markdown(f"**Total Distance** - {total_m:,}m / {target_m_overall:,}m")
    st.progress(pct_overall)
    if pct_overall >= 1.0:
        st.caption(f"🎉 You have conquered {target_lake_overall}!")

elif view_mode == "Group by Lake":
    if not df.empty:
        totals_by_lake = df.groupby("target_lake")["total_metres"].sum().to_dict()
    else:
        totals_by_lake = {}

    lake_cols = st.columns(2)
    for idx, (lake_name, lake_data) in enumerate(LAKES.items()):
        current_m = totals_by_lake.get(lake_name, 0)
        
        # Ensure unsafe_allow_html=True is present here
        with lake_cols[idx % 2]:
            svg_html = render_lake_svg(lake_name, current_m, lake_data["length"])
            st.markdown(svg_html, unsafe_allow_html=True)

# ==========================================
# 7. MANAGE PAST SWIMS
# ==========================================
st.subheader("Manage Past Swims")

user_data = supabase.table("lake_swims").select("*").eq("swimmer", st.session_state["swimmer"]).order("activity_datetime", desc=True).execute().data

if user_data:
    df_history = pd.DataFrame(user_data)[["activity_datetime", "lengths", "pool_length_m", "total_metres", "target_lake"]]
    df_history.columns = ["Date", "Lengths", "Pool (m)", "Total (m)", "Target Lake"]
    st.dataframe(df_history, hide_index=True, use_container_width=True)

    with st.expander("Edit or Delete an Entry"):
        swim_options = {f"{row['activity_datetime']} - {row['total_metres']}m ({row['target_lake']})": row for row in user_data}
        selected_label = st.selectbox("Select entry to modify", list(swim_options.keys()))
        selected_swim = swim_options[selected_label]
        
        with st.form("edit_swim"):
            current_date = datetime.strptime(selected_swim["activity_datetime"], "%Y-%m-%d").date()
            edit_date = st.date_input("Date", current_date)
            
            c1, c2 = st.columns(2)
            edit_lengths = c1.number_input("Lengths", value=selected_swim["lengths"], min_value=1)
            edit_pool = c2.number_input("Pool length (m)", value=selected_swim["pool_length_m"], min_value=1)
            
            # Combine the default total progress bucket with dynamic lakes
            lake_dropdown_options = ["Total Progress"] + list(LAKES.keys())
            
            # Safely set the index if the user previously saved a weird target_lake name
            default_index = 0
            if selected_swim["target_lake"] in lake_dropdown_options:
                default_index = lake_dropdown_options.index(selected_swim["target_lake"])
                
            edit_target_lake = st.selectbox("Target Lake", lake_dropdown_options, index=default_index)
            
            col_update, col_delete = st.columns(2)
            update_submit = col_update.form_submit_button("Update", type="primary", use_container_width=True)
            delete_submit = col_delete.form_submit_button("Delete", use_container_width=True)
            
            if update_submit:
                new_total = edit_lengths * edit_pool
                supabase.table("lake_swims").update({
                    "activity_datetime": str(edit_date),
                    "pool_length_m": edit_pool,
                    "lengths": edit_lengths,
                    "total_metres": new_total,
                    "target_lake": edit_target_lake,
                    "updated_at_datetime": "now()"
                }).eq("id", selected_swim["id"]).execute()
                st.success("Entry updated!")
                st.rerun()
                
            if delete_submit:
                supabase.table("lake_swims").delete().eq("id", selected_swim["id"]).execute()
                st.warning("Entry deleted!")
                st.rerun()
else:
    st.info("No swims logged yet. Get in the pool!")