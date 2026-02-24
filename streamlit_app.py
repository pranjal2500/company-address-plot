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

# --- 4. INTERFACE & MAP SETUP ---
st.title("📍 Interactive Distribution Map")
st.write("Click a red marker or an orange cluster to see details instantly on the right side of the map.")
df = load_live_data()

m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# CRITICAL: Disable zoom on click to keep the map exactly where you want it
marker_cluster = MarkerCluster(options={
    'zoomToBoundsOnClick': False,
    'spiderfyOnMaxZoom': True
}).add_to(m)

# Add Markers with detailed tooltips (Javascript will read these tooltips)
for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    # We package the HTML we want to show directly into the tooltip
    info_html = f"<b>{name}</b><br>Sales: ₹{sales:,.0f}<br><span style='color:gray; font-size:11px;'>Lat: {row['Address Lat']}, Lng: {row['Address Long']}</span>"
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=info_html
    ).add_to(marker_cluster)

# --- 5. THE MAGIC: JAVASCRIPT INFO PANEL ---
# This creates a white panel inside the map that acts just like a Streamlit sidebar
# but updates instantly without making the app say "Running..."
custom_js = """
<style>
.map-sidebar {
    background: white;
    padding: 15px;
    width: 300px;
    max-height: 600px;
    overflow-y: auto;
    box-shadow: 0 0 15px rgba(0,0,0,0.2);
    border-radius: 5px;
    font-family: sans-serif;
}
.map-sidebar h4 { margin-top: 0; color: #1f77b4; font-size: 16px;}
.item-card {
    border-bottom: 1px solid #eee;
    padding-bottom: 10px;
    margin-bottom: 10px;
    font-size: 13px;
    line-height: 1.4;
}
</style>

<script>
window.addEventListener('load', function() {
    setTimeout(function() {
        // Find the Map
        var mapInstance = null;
        for (let key in window) {
            if (key.startsWith('map_') && window[key] instanceof L.Map) { mapInstance = window[key]; break; }
        }
        if (!mapInstance) return;

        // Build the floating panel
        var infoPanel = L.control({position: 'topright'});
        infoPanel.onAdd = function () {
            var div = L.DomUtil.create('div', 'map-sidebar');
            div.innerHTML = '<h4>🏢 Company Details</h4><p style="color:gray; font-size:13px;">Click a marker or cluster to view data here.</p>';
            // Prevent scrolling/clicking the panel from moving the map
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            return div;
        };
        infoPanel.addTo(mapInstance);

        // Find the Cluster Layer
        var clusterLayer = null;
        for (let key in window) {
            if (key.startsWith('marker_cluster_') && window[key] instanceof L.MarkerClusterGroup) { clusterLayer = window[key]; break; }
        }

        if (clusterLayer) {
            // BEHAVIOR 1: Click a Cluster
            clusterLayer.on('clusterclick', function (a) {
                var markers = a.layer.getAllChildMarkers(); // Gets EXACTLY the markers inside
                var html = '<h4>📍 Found ' + markers.length + ' Locations</h4><hr style="margin:5px 0 10px 0;">';
                for (var i = 0; i < markers.length; i++) {
                    var content = markers[i].getTooltip() ? markers[i].getTooltip().getContent() : '';
                    html += '<div class="item-card">' + content + '</div>';
                }
                document.querySelector('.map-sidebar').innerHTML = html;
            });

            // BEHAVIOR 2: Click a Single Red Dot
            clusterLayer.on('click', function (a) {
                var content = a.layer.getTooltip() ? a.layer.getTooltip().getContent() : '';
                var html = '<h4>📍 1 Location Selected</h4><hr style="margin:5px 0 10px 0;">';
                html += '<div class="item-card">' + content + '</div>';
                document.querySelector('.map-sidebar').innerHTML = html;
            });
        }
    }, 1000);
});
</script>
"""
m.get_root().html.add_child(folium.Element(custom_js))

# --- 6. RENDER THE MAP ---
# By setting returned_objects to an empty list [], we physically cut the connection
# between the map clicks and Streamlit. This completely kills the "Running..." delay.
st_folium(m, width=1300, height=800, returned_objects=[])