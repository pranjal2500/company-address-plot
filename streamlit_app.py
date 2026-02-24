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

# --- 1. INITIAL SETUP ---
st.set_page_config(page_title="Company Intelligence Map", layout="wide")

# Constants
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- 2. AUTHENTICATION BYPASS ---
def get_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

# --- 3. PASSWORD PROTECTION ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Secure Map Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock"):
        if pwd == st.secrets["general"]["site_password"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Invalid Password")
    st.stop()

# --- 4. DATA LOADING (CACHED) ---
@st.cache_data(ttl=3600)
def fetch_data():
    creds = get_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    return df.dropna(subset=['Address Lat', 'Address Long'])

# --- 5. BUILD THE INTERFACE ---
df = fetch_data()

# Sidebar Setup
with st.sidebar:
    st.title("🏢 Company Directory")
    st.write("Click a **Cluster** or **Marker** on the map to see the list of companies and their sales below.")
    st.divider()
    
    # Placeholder for the list
    list_container = st.container()

# Main Map Area
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# CRITICAL: Disable zoom on click
marker_cluster = MarkerCluster(options={
    'zoomToBoundsOnClick': False,  # Prevents zooming when clicking a cluster
    'spiderfyOnMaxZoom': True      # Allows seeing individual points at the deepest zoom
}).add_to(m)

for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=6,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=name,
        popup=f"Sales: {sales}"
    ).add_to(marker_cluster)

# Render Map and capture clicks
# We use 'last_object_clicked' to trigger the sidebar update
output = st_folium(m, width=1100, height=800, returned_objects=["last_object_clicked", "zoom"])

# --- 6. SIDEBAR LIST LOGIC ---
clicked = output.get("last_object_clicked")

with list_container:
    if clicked:
        lat, lon = clicked['lat'], clicked['lng']
        
        # Logic: Find companies within a small radius of the click
        # We adjust the "tolerance" based on the zoom level
        zoom_level = output.get("zoom", 5)
        tolerance = 0.5 / (2 ** zoom_level) # Dynamic radius search
        
        matches = df[
            (abs(df['Address Lat'] - lat) < tolerance) & 
            (abs(df['Address Long'] - lon) < tolerance)
        ]
        
        if not matches.empty:
            st.subheader(f"📍 {len(matches)} Locations Found")
            # Sort by Sales Amount descending
            matches = matches.sort_values(by='Sales amount', ascending=False)
            
            for _, item in matches.iterrows():
                with st.expander(f"📌 {item['Name']}"):
                    st.metric("Sales Amount", f"₹{item.get('Sales amount', 0):,.0f}")
                    st.write(f"**Coordinates:** `{item['Address Lat']}, {item['Address Long']}`")
        else:
            st.info("Try clicking directly on a red dot or a cluster number.")
    else:
        st.info("👋 Click any point on the map to start.")
        st.write(f"**Total Records Mapped:** {len(df)}")