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

# Sidebar Setup
with st.sidebar:
    st.header("🏢 Visible Companies")
    st.write("Zoom in or click a cluster. The list below will update to show companies in your current view.")
    st.divider()
    list_placeholder = st.empty()

m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

# We let the cluster zoom normally. No custom Javascript.
marker_cluster = MarkerCluster().add_to(m)

for index, row in df.iterrows():
    name = str(row.get('Name', 'Unknown'))
    sales = row.get('Sales amount', 0)
    
    folium.CircleMarker(
        location=[row['Address Lat'], row['Address Long']],
        radius=5,
        color="red",
        fill=True,
        fill_opacity=0.7,
        tooltip=name,
        popup=f"Sales: ₹{sales:,.0f}"
    ).add_to(marker_cluster)

# --- 5. CAPTURE MAP BOUNDARIES ---
# We ask Streamlit for 'bounds' (the corners of your screen) and 'last_object_clicked' (for single red dots)
map_output = st_folium(
    m, 
    width=1100, 
    height=750, 
    returned_objects=["bounds", "last_object_clicked"]
)

# --- 6. DYNAMIC SIDEBAR LOGIC ---
with list_placeholder.container():
    clicked_data = map_output.get("last_object_clicked")
    bounds = map_output.get("bounds")
    
    # SCENARIO 1: User clicked a specific red dot
    if clicked_data:
        lat, lng = clicked_data['lat'], clicked_data['lng']
        exact_match = df[
            (abs(df['Address Lat'] - lat) < 0.0001) & 
            (abs(df['Address Long'] - lng) < 0.0001)
        ]
        
        if not exact_match.empty:
            st.success("📍 Specific Location Selected")
            for _, item in exact_match.iterrows():
                with st.expander(f"📌 {item['Name']}", expanded=True):
                    st.metric("Sales Amount", f"₹{item.get('Sales amount', 0):,.0f}")
                    st.write(f"**Coordinates:** {item['Address Lat']}, {item['Address Long']}")
            
            # Button to clear selection and go back to visible area mode
            if st.button("Clear Selection"):
                st.rerun()

    # SCENARIO 2: User zoomed in or clicked a cluster (which auto-zooms)
    elif bounds:
        # Get the corners of the visible map
        south, north = bounds["_southWest"]["lat"], bounds["_northEast"]["lat"]
        west, east = bounds["_southWest"]["lng"], bounds["_northEast"]["lng"]
        
        # Filter the dataframe to only show what is inside the screen
        visible_df = df[
            (df['Address Lat'] >= south) & (df['Address Lat'] <= north) &
            (df['Address Long'] >= west) & (df['Address Long'] <= east)
        ]
        
        if len(visible_df) == len(df):
             st.info("Showing the entire country. Zoom in or click a cluster to narrow down the list.")
             st.write(f"**Total Records:** {len(df)}")
             
        elif not visible_df.empty:
            st.success(f"👀 {len(visible_df)} companies visible on screen")
            visible_df = visible_df.sort_values(by='Sales amount', ascending=False)
            
            # Limit to 50 so Streamlit doesn't lag out trying to draw thousands of boxes
            for _, item in visible_df.head(50).iterrows():
                with st.expander(f"📌 {item['Name']}"):
                    st.metric("Sales Amount", f"₹{item.get('Sales amount', 0):,.0f}")
                    
            if len(visible_df) > 50:
                st.warning(f"Showing top 50 of {len(visible_df)} visible companies. Zoom in further to see more.")