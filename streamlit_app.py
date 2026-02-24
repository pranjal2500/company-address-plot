import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import streamlit.components.v1 as components
import requests
import io
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Company Map Analytics", layout="wide")
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

# --- 4. MAP SETUP ---
st.title("📍 Distribution Map")
st.write("Click a cluster to zoom in. Hover over a red marker to see company details.")

df = load_live_data()
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# Bring back the clean, professional native clusters
marker_cluster = MarkerCluster().add_to(m)

for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    # Hover text with bracketed sales
    hover_text = f"{name} (₹{sales:,.0f})"
    
    # Detailed popup on click
    popup_html = f"<div style='min-width: 150px; font-family: sans-serif;'><b>{name}</b><br><span style='color: #d32f2f;'>Sales: ₹{sales:,.0f}</span></div>"
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=6,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=hover_text,
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(marker_cluster)

# --- 5. LAG-FREE RENDER ---
# This renders the map instantly and stops Streamlit from lagging when you drag/zoom
components.html(m._repr_html_(), height=750)