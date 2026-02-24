import streamlit as st
import pandas as pd
import folium
import streamlit.components.v1 as components
import requests
import io
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

st.set_page_config(page_title="Company Map Analytics", layout="wide")
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo'
SHEET_TAB_NAME = 'New Address Data'

def get_google_creds():
    token_info = json.loads(st.secrets["google"]["token_json"])
    creds = Credentials.from_authorized_user_info(token_info)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return creds

@st.cache_data(ttl=3600)
def load_and_cluster_data():
    creds = get_google_creds()
    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.get(url, headers=headers)
    
    df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    df = df.dropna(subset=['Address Lat', 'Address Long'])
    
    # --- THE OUT-OF-THE-BOX MAGIC ---
    # 1. Round coordinates to 1 decimal place (~11km grid)
    df['Grid Lat'] = df['Address Lat'].round(1)
    df['Grid Lng'] = df['Address Long'].round(1)
    
    # 2. Group the data by these new grid zones
    clustered_df = df.groupby(['Grid Lat', 'Grid Lng']).agg(
        company_count=('Name', 'count'),
        total_sales=('Sales amount', 'sum'),
        # Create a bulleted HTML list of up to 20 company names in this zone
        company_list=('Name', lambda x: '<br>• '.join(x.astype(str).head(20)))
    ).reset_index()
    
    return clustered_df

st.title("📍 Regional Sales Density Map")
st.write("Hover over any zone to see total aggregated sales. Click to see the companies inside.")

# Load the mathematically grouped data
df_zones = load_and_cluster_data()

m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# We draw the zones directly. NO Leaflet MarkerCluster plugin used at all!
for index, row in df_zones.iterrows():
    count = row['company_count']
    sales = row['total_sales']
    
    # Dynamic circle size based on how many companies are in the zone
    radius_size = 6 + (count * 0.5) 
    if radius_size > 25: radius_size = 25 # Cap the max size
    
    # What shows on Hover
    hover_text = f"Zone: {count} Companies (Total Sales: ₹{sales:,.0f})"
    
    # What shows on Click
    popup_html = f"""
    <div style='min-width: 200px; max-height: 250px; overflow-y: auto; font-family: sans-serif;'>
        <h4 style='color: #d32f2f; margin-bottom: 5px;'>{count} Companies Here</h4>
        <b>Total Sales: ₹{sales:,.0f}</b><hr>
        • {row['company_list']}
    </div>
    """
    
    folium.CircleMarker(
        location=[row['Grid Lat'], row['Grid Lng']],
        radius=radius_size,
        color="red",
        fill=True,
        fill_opacity=0.6,
        tooltip=hover_text,
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(m)

# Fast HTML Render
components.html(m._repr_html_(), height=750)