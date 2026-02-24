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
st.title("📍 Interactive Distribution Map")
df = load_live_data()

m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# CRITICAL: Disable zoom on click so the map stays still
marker_cluster = MarkerCluster(options={
    'zoomToBoundsOnClick': False,
    'spiderfyOnMaxZoom': True
}).add_to(m)

# Add Markers
for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    # We format the info cleanly here so the Javascript can just copy-paste it
    info_html = f"<div style='line-height:1.3;'><b>{name}</b><br><span style='color:green;'>Sales: ₹{sales:,.0f}</span></div>"
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=name,
        popup=folium.Popup(info_html, max_width=250) # The JS reads this popup!
    ).add_to(marker_cluster)

# --- 5. JAVASCRIPT INJECTION FOR INSTANT CLUSTER POPUPS ---
# This script grabs all the points inside a cluster and combines them into one neat popup.
custom_js = """
<script>
window.addEventListener('load', function() {
    setTimeout(function() {
        var clusterLayer = null;
        
        // Find the map's cluster layer
        for (let key in window) {
            if (key.startsWith('marker_cluster_') && window[key] instanceof L.MarkerClusterGroup) { 
                clusterLayer = window[key]; 
                break; 
            }
        }

        if (clusterLayer) {
            clusterLayer.on('clusterclick', function (a) {
                // Get EXACTLY the markers inside this specific cluster
                var markers = a.layer.getAllChildMarkers(); 
                
                // Build a scrollable list popup
                var html = '<div style="max-height: 250px; overflow-y: auto; width: 220px; font-family: sans-serif;">';
                html += '<h4 style="margin: 0 0 8px 0; color: #d32f2f; border-bottom: 2px solid #eee; padding-bottom: 4px;">📍 ' + markers.length + ' Locations</h4>';
                
                for (var i = 0; i < markers.length; i++) {
                    // Extract the HTML we put into the individual marker's popup
                    var content = markers[i].getPopup() ? markers[i].getPopup().getContent() : 'Unknown Data';
                    html += '<div style="border-bottom: 1px solid #eee; padding: 6px 0; font-size: 13px;">' + content + '</div>';
                }
                html += '</div>';
                
                // Open the popup right where the user clicked
                L.popup({maxWidth: 250})
                    .setLatLng(a.layer.getLatLng())
                    .setContent(html)
                    .openOn(a.layer._map);
            });
        }
    }, 1000); // Wait 1 second for map to render before attaching script
});
</script>
"""
m.get_root().html.add_child(folium.Element(custom_js))

# --- 6. RENDER THE MAP ---
# THE FIX: returned_objects=[] tells Streamlit to completely ignore map clicks.
# This 100% eliminates the "Running..." text and lag.
st_folium(m, width=1300, height=800, returned_objects=[])