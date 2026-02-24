import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import requests
import io
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Company Map Analytics", layout="wide")

# Secrets are pulled from Streamlit Cloud "Advanced Settings"
SITE_PASSWORD = st.secrets["general"]["site_password"]
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- 2. GOOGLE AUTHENTICATION ---
def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

# --- 3. PASSWORD PROTECTION ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Secure Map Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock Map"):
        if pwd == SITE_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid Password")
    st.stop()

# --- 4. DATA LOADING (WITH CACHING) ---
@st.cache_data(ttl=3600)
def load_live_data():
    creds = get_google_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    return df.dropna(subset=['Address Lat', 'Address Long'])

# --- 5. INTERFACE & MAP ---
st.title("📍 Interactive Distribution Map")
df = load_live_data()

# Create the Sidebar Placeholder
with st.sidebar:
    st.header("🏢 Company Directory")
    st.write("Click any **Cluster** or **Red Marker** to see the list here.")
    st.divider()
    list_placeholder = st.container()

# Create the Map
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# We enable zoom so the cluster "spreads" slightly to reveal data
marker_cluster = MarkerCluster(options={
    'zoomToBoundsOnClick': True,
    'spiderfyOnMaxZoom': True,
    'maxClusterRadius': 60
}).add_to(m)

for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=name, 
        popup=f"Sales: {sales}"
    ).add_to(marker_cluster)

# --- 6. RENDER & CAPTURE ---
# We capture 'last_object_clicked' to trigger the sidebar update
map_output = st_folium(m, width=1100, height=750, returned_objects=["last_object_clicked"])

# --- 7. SIDEBAR LOGIC ---
clicked_data = map_output.get("last_object_clicked")

with list_placeholder:
    if clicked_data:
        lat = clicked_data.get('lat')
        lng = clicked_data.get('lng')
        
        # Bypassing the coordinate mismatch: Search within a small radius
        # 0.05 is roughly 5km, which safely captures cluster members
        search_radius = 0.05 
        
        matches = df[
            (abs(df['Address Lat'] - lat) < search_radius) & 
            (abs(df['Address Long'] - lng) < search_radius)
        ]
        
        if not matches.empty:
            st.success(f"Found {len(matches)} companies at this location")
            
            # Sort by sales to show high-value targets first
            matches = matches.sort_values(by='Sales amount', ascending=False)
            
            for _, item in matches.head(50).iterrows(): # Show top 50 to keep sidebar fast
                with st.expander(f"📌 {item['Name']}"):
                    st.metric("Sales Amount", f"₹{item.get('Sales amount', 0):,.0f}")
                    st.write(f"**Coordinates:** `{item['Address Lat']}, {item['Address Long']}`")
            
            if len(matches) > 50:
                st.warning(f"Showing top 50 of {len(matches)} results. Zoom in for more precision.")
        else:
            st.info("Try clicking directly on a red dot or the center of a cluster number.")
    else:
        st.info("Select a marker on the map to display company info here.")
        st.divider()
        st.write(f"**Total Companies Mapped:** {len(df)}")