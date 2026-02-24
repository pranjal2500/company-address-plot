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

SITE_PASSWORD = st.secrets["general"]["site_password"]
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- 2. AUTHENTICATION ---
def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

# --- 3. LOGIN ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Secure Map Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Unlock"):
        if pwd == SITE_PASSWORD:
            st.session_state.auth = True
            st.rerun()
    st.stop()

# --- 4. DATA LOADING ---
@st.cache_data(ttl=3600)
def load_data():
    creds = get_google_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    return df.dropna(subset=['Address Lat', 'Address Long'])

# --- 5. MAIN UI & MAP ---
st.title("📍 Interactive Distribution Map")
df = load_data()

# Create the Map
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
marker_cluster = MarkerCluster().add_to(m)

# Add Markers
for _, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        # We store the unique index in the tooltip for Streamlit to find it
        tooltip=name, 
        popup=f"Sales: {sales}"
    ).add_to(marker_cluster)

# --- 6. RENDER MAP & CAPTURE CLICKS ---
# 'last_object_clicked' allows us to see what the user tapped
map_data = st_folium(m, width=1100, height=700, returned_objects=["last_object_clicked"])

# --- 7. SIDEBAR CONTENT ---
with st.sidebar:
    st.header("🏢 Company Details")
    
    clicked = map_data.get("last_object_clicked")
    
    if clicked:
        lat, lon = clicked['lat'], clicked['lng']
        
        # Find all companies at this exact location (or very close to it)
        # This effectively captures members of a cluster when you zoom in or click a point
        tolerance = 0.001 
        matched_df = df[
            (abs(df['Address Lat'] - lat) < tolerance) & 
            (abs(df['Address Long'] - lon) < tolerance)
        ]
        
        if not matched_df.empty:
            st.subheader(f"Found {len(matched_df)} results")
            for _, item in matched_df.iterrows():
                with st.expander(f"📌 {item['Name']}"):
                    st.write(f"**Sales:** {item.get('Sales amount', 'N/A')}")
                    st.write(f"**Lat/Long:** {item['Address Lat']}, {item['Address Long']}")
        else:
            st.info("Click a specific marker to see details here.")
    else:
        st.info("Click on a red marker on the map to display company information in this panel.")
        st.divider()
        st.write(f"**Total Records:** {len(df)}")