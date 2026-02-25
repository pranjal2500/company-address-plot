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
window.addEventListener('load', function() {
  setTimeout(function() {

    var mapInstance = null;
    for (let key in window) {
      if (window[key] instanceof L.Map) {
        mapInstance = window[key];
        break;
      }
    }
    if (!mapInstance) return;

    var clusterLayer = null;
    for (let id in mapInstance._layers) {
      var layer = mapInstance._layers[id];
      if (layer instanceof L.MarkerClusterGroup) {
        clusterLayer = layer;
        break;
      }
    }
    if (!clusterLayer) return;

    function extractInfo(marker){
      var content = marker.getPopup() ? marker.getPopup().getContent() : '';
      var div = document.createElement('div');
      div.innerHTML = content;

      var name = div.querySelector('b') ? div.querySelector('b').innerText : 'Unknown';
      var salesText = div.querySelector('span') ? div.querySelector('span').innerText : '';

      var numberMatch = salesText.match(/[0-9,]+/);
      var numericSales = numberMatch ? parseFloat(numberMatch[0].replace(/,/g,'')) : 0;

      return {name:name, salesText:salesText, sales:numericSales};
    }

    // HOVER PREVIEW
    clusterLayer.on('clustermouseover', function(e) {
      var markers = e.layer.getAllChildMarkers();
      var html = '<div style="font-family:sans-serif; font-size:13px; max-width:300px;">';
      html += '<b>' + markers.length + ' Locations</b><hr>';

      var previewCount = Math.min(5, markers.length);
      var total = 0;

      for (var i=0; i<previewCount; i++){
        var info = extractInfo(markers[i]);
        total += info.sales;

        html += '<div style="margin-bottom:6px;">'
             + '<div style="font-weight:600;">' + info.name + '</div>'
             + '<div style="color:#2e7d32;">' + info.salesText + '</div>'
             + '</div>';
      }

      if (markers.length > previewCount) {
        html += '<div style="color:#666;">and '
             + (markers.length - previewCount)
             + ' more...</div>';
      }

      html += '<hr><div style="font-weight:700;">Preview Total: ₹'
           + total.toLocaleString()
           + '</div></div>';

      e.layer.bindTooltip(html, {sticky:true}).openTooltip();
    });

    clusterLayer.on('clustermouseout', function(e){
      e.layer.closeTooltip();
    });

    // CLICK FULL LIST
    clusterLayer.on('clusterclick', function(e){
      var markers = e.layer.getAllChildMarkers();

      var html = '<div style="max-height:300px; overflow-y:auto; width:280px; font-family:sans-serif;">';
      html += '<h4 style="margin:0 0 8px 0;">📍 '
           + markers.length
           + ' Locations</h4>';

      for (var i=0; i<markers.length; i++){
        var content = markers[i].getPopup().getContent();
        html += '<div style="border-bottom:1px solid #eee; padding:6px 0;">'
             + content
             + '</div>';
      }

      html += '</div>';

      L.popup({maxWidth:350})
        .setLatLng(e.layer.getLatLng())
        .setContent(html)
        .openOn(mapInstance);
    });

  }, 800);
});
</script>
"""

m.get_root().html.add_child(folium.Element(custom_js))

# --- 6. RENDER ---
st_folium(m, width=1300, height=800, returned_objects=[])