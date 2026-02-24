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

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Company Map Analytics", layout="wide")

# Fetching secrets from Streamlit's "Advanced Settings"
SITE_PASSWORD = st.secrets["general"]["site_password"]
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

# --- 2. AUTHENTICATION LOGIC ---
def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    # Note: Only Drive scope is needed because we fetch the file binary
    creds = Credentials.from_authorized_user_info(token_info)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

# --- 3. LOGIN INTERFACE ---
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
@st.cache_data(ttl=3600)  # Caches data for 1 hour to save memory/speed
def load_live_data():
    creds = get_google_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    return df.dropna(subset=['Address Lat', 'Address Long'])

# --- 5. MAP BUILDING ---
st.title("📍 Company Distribution Map")

try:
    df = load_live_data()
    st.sidebar.success(f"Successfully loaded {len(df)} locations.")

    # Create Map
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)
    
    # Disable 'zoomToBoundsOnClick' to allow for our custom list popup
    marker_cluster = MarkerCluster(options={'zoomToBoundsOnClick': False}).add_to(m)

    for _, row in df.iterrows():
        name = str(row.get('Name', 'Unknown'))
        sales = row.get('Sales amount', 0)
        
        folium.CircleMarker(
            location=[row['Address Lat'], row['Address Long']],
            radius=5,
            popup=f"<b>{name}</b><br>Sales: {sales}",
            color="red",
            fill=True,
            fill_opacity=0.6
        ).add_to(marker_cluster)

    # --- JAVASCRIPT INJECTION FOR CLUSTER POPUPS ---
    cluster_click_js = f"""
    <script>
    window.addEventListener('load', function() {{
        setTimeout(function() {{
            var clusterLayer = null;
            // Identify the specific cluster group layer
            for (let key in window) {{
                if (key.startsWith('marker_cluster_') && window[key] instanceof L.MarkerClusterGroup) {{
                    clusterLayer = window[key];
                    break;
                }}
            }}

            if (clusterLayer) {{
                clusterLayer.on('clusterclick', function (a) {{
                    var markers = a.layer.getAllChildMarkers();
                    var popupHtml = '<div style="max-height: 200px; overflow-y: auto; width: 250px; font-family: sans-serif;">';
                    popupHtml += '<b>Locations in this area (' + markers.length + ')</b><hr>';
                    
                    for (var i = 0; i < markers.length; i++) {{
                        var nameContent = markers[i].getPopup().getContent();
                        popupHtml += '<div style="margin-bottom:8px; padding-bottom:4px; border-bottom:1px solid #eee;">' + nameContent + '</div>';
                    }}
                    popupHtml += '</div>';
                    
                    L.popup().setLatLng(a.layer.getLatLng()).setContent(popupHtml).openOn(a.target._map);
                }});
            }}
        }}, 1000);
    }});
    </script>
    """
    m.get_root().html.add_child(folium.Element(cluster_click_js))

    # Display Map
    st_folium(m, width=1400, height=800, returned_objects=[])

except Exception as e:
    st.error(f"Critical Error: {e}")