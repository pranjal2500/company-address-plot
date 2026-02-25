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

SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- 2. GOOGLE AUTH ---
def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    return creds

# --- 3. LOAD DATA ---
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

# --- 4. MAP ---
st.title("📍 Interactive Distribution Map")

df = load_live_data()

m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

marker_cluster = MarkerCluster(options={
    'zoomToBoundsOnClick': False,
    'spiderfyOnMaxZoom': True
}).add_to(m)

# Add individual markers
for _, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)

    info_html = f"""
    <div style='line-height:1.4;'>
        <b>{name}</b><br>
        <span style='color:green;'>Sales: ₹{sales:,.0f}</span>
    </div>
    """

    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=name,
        popup=folium.Popup(info_html, max_width=250)
    ).add_to(marker_cluster)

# --- 5. JAVASCRIPT FOR CLUSTER HOVER + CLICK ---
custom_js = """
<script>
console.log("JS Loaded");

setTimeout(function() {
    console.log("Searching for map...");

    var maps = Object.values(window).filter(v => v instanceof L.Map);
    console.log("Maps found:", maps.length);

    if (maps.length > 0) {
        console.log("Map found successfully");
    } else {
        console.log("No map found");
    }
}, 1500);
</script>
"""

m.get_root().html.add_child(folium.Element(custom_js))

# --- 6. RENDER ---
st_folium(m, width=1300, height=800, returned_objects=[])