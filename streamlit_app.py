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

# --- CONFIGURATION ---
st.set_page_config(page_title="Company Map", layout="wide")

# Secrets are handled via Streamlit's dashboard
SITE_PASSWORD = st.secrets["general"]["site_password"]
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# --- GOOGLE AUTH ---
def get_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

# --- LOGIN UI ---
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Secure Map Access")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Login"):
        if pwd == SITE_PASSWORD:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Incorrect Password")
    st.stop()

# --- MAIN APP ---
st.title("📍 Company Location Analytics")

@st.cache_data(ttl=3600) # Caches data for 1 hour so it loads instantly for others
def load_data():
    creds = get_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    
    # Cleaning
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    return df.dropna(subset=['Address Lat', 'Address Long'])

try:
    df = load_data()
    st.success(f"Successfully loaded {len(df)} locations.")

    # Optimized Map Logic
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
    marker_cluster = MarkerCluster().add_to(m)

    for _, row in df.iterrows():
        folium.CircleMarker(
            location=[row['Address Lat'], row['Address Long']],
            radius=5,
            popup=f"<b>{row.get('Name', 'Unknown')}</b><br>Sales: {row.get('Sales amount', 0)}",
            color="red",
            fill=True,
            fill_opacity=0.7
        ).add_to(marker_cluster)

    st_folium(m, width=1400, height=800, returned_objects=[])

except Exception as e:
    st.error(f"Error: {e}")