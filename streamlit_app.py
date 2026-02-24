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

# Google Sheets Config
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

# --- 3. DATA LOADING (CACHED) ---
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

# --- 4. INTERFACE & MAP ---
st.title("📍 Interactive Distribution Map")
df = load_live_data()

# Create the Sidebar Placeholder
with st.sidebar:
    st.header("🏢 Company Directory")
    st.write("Click any **Cluster** or **Red Marker** to see the list.")
    st.divider()
    list_placeholder = st.empty() # Using empty for clean updates

# Create the Map
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# Cluster configuration: We keep zoom enabled so you can drill down, 
# but we improve the data capture.
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

# --- 5. RENDER & CAPTURE ---
# We capture 'last_object_clicked' AND 'last_active_drawing' for better detection
map_output = st_folium(
    m, 
    width=1100, 
    height=750, 
    returned_objects=["last_object_clicked", "last_active_drawing", "zoom", "bounds"]
)

# --- 6. ADVANCED SIDEBAR LOGIC ---
clicked_data = map_output.get("last_object_clicked")
bounds = map_output.get("bounds")

with list_placeholder.container():
    if clicked_data:
        lat, lng = clicked_data.get('lat'), clicked_data.get('lng')
        
        # INCREASED TOLERANCE
        # Because clusters report a "center" that might not be on a dot,
        # we search a small window around the click.
        search_window = 0.08 # Approx 8-10km radius
        
        matches = df[
            (abs(df['Address Lat'] - lat) < search_window) & 
            (abs(df['Address Long'] - lng) < search_window)
        ]
        
        if not matches.empty:
            st.success(f"Found {len(matches)} results in this area")
            matches = matches.sort_values(by='Sales amount', ascending=False)
            
            for _, item in matches.head(50).iterrows():
                with st.expander(f"📌 {item['Name']}"):
                    st.metric("Sales Amount", f"₹{item.get('Sales amount', 0):,.0f}")
                    st.write(f"**Coordinates:** `{item['Address Lat']}, {item['Address Long']}`")
            
            if len(matches) > 50:
                st.warning(f"Showing top 50 performers. Zoom in for full list.")
        else:
            st.info("No data found at this click. Try clicking a specific red dot.")
    
    elif bounds:
        # Fallback: If nothing is clicked, show a summary of the visible area
        st.write(f"**Total Records Mapped:** {len(df)}")
        st.caption("Tip: Click a cluster or marker to see specific details.")