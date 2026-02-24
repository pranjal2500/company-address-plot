from flask import Flask, request, session, redirect, render_template_string
import os
from dotenv import load_dotenv
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from folium.features import DivIcon
import requests
import io
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- 1. LOAD SECRETS ---
load_dotenv()

app = Flask(__name__)
# Secure the session cookies
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super_secret_random_key_123") 
# Pull the site password from .env (fallback to 'mypassword123' if not found locally)
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "mypassword123") 

# --- CONFIGURATION ---
SPREADSHEET_ID = '1rmzPxd8xDBW0ZyPTlQEgSK0ZRu0FDKFo' 
SHEET_TAB_NAME = 'New Address Data'
MAX_EXPECTED_COUNT = 1200 
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]

# Render will look in the secrets vault; locally it looks in your folder
TOKEN_FILE = os.environ.get("TOKEN_FILE", "token.json")
CREDS_FILE = os.environ.get("CREDS_FILE", "credentials.json")

# --- 2. USER TOKEN AUTHENTICATION (THE BYPASS) ---
def get_access_token():
    """Silently refreshes your existing personal token without a browser."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Try to save the refreshed token locally. 
            # On Render, this folder is read-only, so it quietly skips saving, 
            # but keeps the fresh token alive in memory to serve the map!
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
            except OSError:
                pass 
        else:
            raise Exception("Token expired or missing. Please run the local script to generate a fresh token.json.")
            
    return creds.token

# --- 3. LOGIN PAGE ROUTE ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == SITE_PASSWORD:
            session['logged_in'] = True
            return redirect('/')
        else:
            error = "Invalid Password."
            
    return render_template_string("""
        <html>
        <head><title>Map Login</title></head>
        <body style="font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #f4f4f9; margin: 0;">
            <div style="background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center;">
                <h2 style="color: #333;">Secure Map Access</h2>
                <p style="color: red; font-size: 14px;">{{ error }}</p>
                <form method="POST">
                    <input type="password" name="password" placeholder="Enter Password" style="padding: 10px; width: 220px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 4px;"><br>
                    <input type="submit" value="Unlock Map" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
                </form>
            </div>
        </body>
        </html>
    """, error=error)

# --- 4. LIVE MAP ROUTE ---
@app.route('/')
def map_view():
    # Bounce user back to login if they aren't authenticated
    if not session.get('logged_in'):
        return redirect('/login')

    print("🔄 Fetching live data from Google Sheets via local token...")
    try:
        token = get_access_token()
    except Exception as e:
        return f"Authentication Error. Ensure token.json is valid. Error: {e}", 500

    url = f"https://www.googleapis.com/drive/v3/files/{SPREADSHEET_ID}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return f"Error downloading sheet: {response.text}", 500

    # Read data
    try:
        df = pd.read_excel(io.BytesIO(response.content), sheet_name=SHEET_TAB_NAME)
    except ValueError:
        return f"Error: Tab '{SHEET_TAB_NAME}' not found in the sheet.", 500

    # Clean Data
    df.columns = df.columns.astype(str).str.strip()
    df['Address Lat'] = pd.to_numeric(df['Address Lat'], errors='coerce')
    df['Address Long'] = pd.to_numeric(df['Address Long'], errors='coerce')
    df = df.dropna(subset=['Address Lat', 'Address Long'])

    if 'Sales amount' in df.columns:
        df['Sales amount'] = df['Sales amount'].astype(str).str.replace(',', '', regex=False)
        df['Sales amount'] = pd.to_numeric(df['Sales amount'], errors='coerce').fillna(0)
    else:
        df['Sales amount'] = 0

    # Build Map
    m = folium.Map(location=[20.5937, 78.9629], zoom_start=5)

    # Cluster Javascript (Unpacks Trojan Horse string for cluster math)
    icon_create_function = f"""
        function(cluster) {{
            var markers = cluster.getAllChildMarkers();
            var count = markers.length; 
            var sum = 0;
            
            for (var i = 0; i < markers.length; i++) {{
                var hiddenData = markers[i].options.title || "Unknown_#_0";
                var parts = hiddenData.split('_#_');
                var salesVal = parseFloat(parts[1]) || 0;
                sum += salesVal;
            }}
            
            var formatted_sum = Math.round(sum);
            var logVal = Math.log(count);
            var logMax = Math.log({MAX_EXPECTED_COUNT});
            var intensity = Math.max(Math.min(logVal / logMax, 1.0), 0.15); 
            var gb = Math.floor(255 * (1 - intensity));
            var borderColor = 'rgb(255, ' + gb + ', ' + gb + ')';
            var bgColor = 'rgba(255, ' + gb + ', ' + gb + ', 0.3)';

            return L.divIcon({{
                html: '<div style="background-color:' + bgColor + '; border: 3px solid ' + borderColor + '; color:black; border-radius:50%; text-align:center; font-weight:bold; width:45px; height:45px; display:flex; flex-direction:column; justify-content:center; align-items:center;">' 
                      + '<span style="font-size:12px;">' + count + '</span>' 
                      + '<span style="font-size:9px;">(' + formatted_sum + ')</span></div>',
                className: 'marker-cluster-custom',
                iconSize: L.point(45, 45) 
            }});
        }}
    """

    marker_cluster = MarkerCluster(
        options={'zoomToBoundsOnClick': False},
        icon_create_function=icon_create_function
    ).add_to(m)

    # Safe fallback for names
    names_list = df['Name'] if 'Name' in df.columns else ['Unknown'] * len(df)

    # Add Markers
    for lat, long, name, sales in zip(df['Address Lat'], df['Address Long'], names_list, df['Sales amount']):
        intensity = 0.15
        gb = int(255 * (1 - intensity))
        border_color = f'rgb(255, {gb}, {gb})'       
        bg_color = f'rgba(255, {gb}, {gb}, 0.3)'     
        
        clean_name = "Unknown" if pd.isna(name) else str(name)
        safe_name = clean_name.replace('"', '&quot;').replace("'", "&#39;") 
        
        # --- THE TROJAN HORSE ---
        hidden_data = f"{safe_name}_#_{sales}"
        
        icon_html = f"""<div style="background-color:{bg_color}; border:3px solid {border_color}; color:black; border-radius:50%; text-align:center; font-weight:bold; width:45px; height:45px; display:flex; flex-direction:column; justify-content:center; align-items:center;"><span style="font-size:12px;">1</span><span style="font-size:9px;">({round(sales)})</span></div>"""

        folium.Marker(
            location=[lat, long],
            title=hidden_data,
            popup=f"<b>{safe_name}</b><br>Sales: {sales}", 
            icon=DivIcon(html=icon_html, icon_size=(45,45), icon_anchor=(22,22))
        ).add_to(marker_cluster)

    # Popup Script (Unpacks Trojan Horse string for the HTML list)
    cluster_click_js = f"""
    <script>
    window.addEventListener('load', function() {{
        setTimeout(function() {{
            {marker_cluster.get_name()}.on('clusterclick', function (a) {{
                var markers = a.layer.getAllChildMarkers();
                var popupHtml = '<div style="max-height: 250px; overflow-y: auto; width: 280px; padding-right: 5px; font-family: Arial, sans-serif;">';
                popupHtml += '<div style="font-weight: bold; margin-bottom: 8px; font-size: 14px; border-bottom: 2px solid #ccc; padding-bottom: 4px;">Cluster Locations (' + markers.length + ')</div>';
                popupHtml += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">';
                
                for (var i = 0; i < markers.length; i++) {{
                    var hiddenData = markers[i].options.title || "Unknown Name_#_0";
                    var parts = hiddenData.split('_#_');
                    var cName = parts[0];
                    var salesVal = parseFloat(parts[1]) || 0;
                    
                    popupHtml += '<tr>';
                    popupHtml += '<td style="padding: 4px 0; border-bottom: 1px solid #eee; word-wrap: break-word; max-width: 190px;">' + cName + '</td>';
                    popupHtml += '<td style="text-align: right; padding: 4px 0; border-bottom: 1px solid #eee; font-weight: bold;">' + salesVal + '</td>';
                    popupHtml += '</tr>';
                }}
                popupHtml += '</table></div>';
                L.popup().setLatLng(a.layer.getLatLng()).setContent(popupHtml).openOn({m.get_name()});
            }});
        }}, 500); 
    }});
    </script>
    """
    m.get_root().html.add_child(folium.Element(cluster_click_js))

    # Output directly to the browser (No local HTML file saving needed!)
    return m.get_root().render()

if __name__ == '__main__':
    # Local development server
    app.run(debug=True, host='0.0.0.0', port=5000)