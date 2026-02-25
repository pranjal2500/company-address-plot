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

# --- CONFIG ---
st.set_page_config(page_title="Company Map Analytics", layout="wide")

SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- GOOGLE AUTH ---
def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

# --- LOAD DATA ---
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

# --- MAIN ---
st.title("📍 Company Distribution Map")

df = load_live_data()

# Create map
m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
marker_cluster = MarkerCluster().add_to(m)

# Add markers
for _, row in df.iterrows():
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        popup=f"<b>{row['Name']}</b><br>Sales: ₹{row['Sales amount']:,.0f}"
    ).add_to(marker_cluster)

# Render map and capture bounds
map_data = st_folium(
    m,
    width=1300,
    height=750,
    returned_objects=["bounds"]
)

# --- Detect Visible Companies ---
if map_data and map_data["bounds"]:
    bounds = map_data["bounds"]

    south = bounds["_southWest"]["lat"]
    north = bounds["_northEast"]["lat"]
    west = bounds["_southWest"]["lng"]
    east = bounds["_northEast"]["lng"]

    visible_df = df[
        (df['Address Lat'] >= south) &
        (df['Address Lat'] <= north) &
        (df['Address Long'] >= west) &
        (df['Address Long'] <= east)
    ]

    st.divider()
    st.subheader(f"📊 {len(visible_df)} Companies in Current View")

    if not visible_df.empty:
        visible_df = visible_df.sort_values("Sales amount", ascending=False)

        total_sales = visible_df["Sales amount"].sum()
        st.metric("Total Sales (Visible Area)", f"₹{total_sales:,.0f}")

        for _, row in visible_df.head(50).iterrows():
            st.write(
                f"**{row['Name']}** — ₹{row['Sales amount']:,.0f}"
            )

        if len(visible_df) > 50:
            st.info("Showing top 50 companies. Zoom further to narrow results.")