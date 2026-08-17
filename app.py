import streamlit as st
import pandas as pd
import json
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, shape
from streamlit_js_eval import get_geolocation
import gzip
import gc

st.set_page_config(page_title="World Map Explorer - ATS", layout="wide")

MX_GEO = "municipios_mexico_simple.json.gz"
MX_CSV = "mis_293_municipios_CON_CLAVE.csv"

US_GEO = "usa_counties_simple.json.gz"
US_CSV = "mis_condados_usa.csv"

ESTADOS_MX = {
    '01': 'AGS', '02': 'BC', '03': 'BCS', '04': 'CAMP', '05': 'COAH', '06': 'COL',
    '07': 'CHIS', '08': 'CHIH', '09': 'CDMX', '10': 'DGO', '11': 'GTO', '12': 'GRO',
    '13': 'HGO', '14': 'JAL', '15': 'MEX', '16': 'MICH', '17': 'MOR', '18': 'NAY',
    '19': 'NL', '20': 'OAX', '21': 'PUE', '22': 'QRO', '23': 'QROO', '24': 'SLP',
    '25': 'SIN', '26': 'SON', '27': 'TAB', '28': 'TAM', '29': 'TLAX', '30': 'VER',
    '31': 'YUC', '32': 'ZAC'
}

@st.cache_data(max_entries=1)
def cargar_mapa_mx():
    gc.collect()
    with gzip.open(MX_GEO, "rt", encoding="utf-8") as f:
        geojson = json.load(f)
        
    features = geojson['features']
    cat = {}
    
    for feat in features:
        props = feat.setdefault('properties', {})
        cve = str(props.get('CVEGEO', '')).zfill(5)
        props['CVEGEO'] = cve
        nom = props.get('NOMGEO', 'Municipio')
        est_abbr = ESTADOS_MX.get(cve[:2], 'MX')
        props['ESTADO_ABBR'] = est_abbr
        
        geom = shape(feat['geometry'])
        cent = geom.centroid
        
        label = f"{nom}, {est_abbr}"
        cat[label] = {
            'clave': cve,
            'nombre': nom,
            'estado': est_abbr,
            'lat': cent.y,
            'lon': cent.x
        }
        
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    return gdf, cat, geojson

@st.cache_data(max_entries=1)
def cargar_mapa_us():
    gc.collect()
    with gzip.open(US_GEO, "rt", encoding="utf-8") as f:
        geojson = json.load(f)
        
    features = geojson['features']
    cat = {}
    
    for feat in features:
        props = feat.setdefault('properties', {})
        fips_val = feat.get('id', props.get('FIPS', props.get('GEO_ID_FIPS', '')))
        fips = str(fips_val).zfill(5)
        props['FIPS'] = fips
        nom = props.get('NAME', 'County')
        state = props.get('STATE', 'US')
        
        geom = shape(feat['geometry'])
        cent = geom.centroid
        
        label = f"{nom} County, {state}"
        cat[label] = {
            'clave': fips,
            'nombre': nom,
            'estado': state,
            'lat': cent.y,
            'lon': cent.x
        }
        
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    gdf['FIPS'] = gdf['FIPS'].astype(str).str.zfill(5)
    return gdf, cat, geojson

# Sidebar y Selector
st.sidebar.title("World Map Explorer")

if "punto_eval" not in st.session_state:
    st.session_state.punto_eval = None

def limpiar_estado_y_memoria():
    st.session_state.punto_eval = None
    st.cache_data.clear()
    gc.collect()

pais_sel = st.sidebar.selectbox(
    "Selecciona Region:", 
    ["Mexico", "Estados Unidos"],
    on_change=limpiar_estado_y_memoria
)

if pais_sel == "Mexico":
    gdf_actual, catalogo, geojson_data = cargar_mapa_mx()
    df_vis = pd.read_csv(MX_CSV, dtype=str)
    claves_set = set(df_vis['CVEGEO'].dropna().str.zfill(5))
    total_muni = 2478
    csv_actual = MX_CSV
    label_entidad = "Municipios"
else:
    gdf_actual, catalogo, geojson_data = cargar_mapa_us()
    try:
        df_vis = pd.read_csv(US_CSV, dtype=str)
        claves_set = set(df_vis['FIPS'].dropna().str.zfill(5))
    except:
        df_vis = pd.DataFrame(columns=['FIPS', 'County_Nombre', 'Estado_Code'])
        claves_set = set()
    total_muni = 3143
    csv_actual = US_CSV
    label_entidad = "Condados"

# Métricas
total_vis = len(claves_set)
pct = (total_vis / total_muni) * 100
st.sidebar.metric(f"{label_entidad} Desbloqueados", f"{total_vis} / {total_muni:,}", f"{pct:.1f}%")
st.sidebar.progress(min(pct / 100, 1.0))
st.sidebar.markdown("---")

# GPS Nativo
loc = get_geolocation()
lat_gps, lon_gps = (38.5816, -121.4944) if pais_sel == "Estados Unidos" else (20.6760, -103.3470)

if loc and isinstance(loc, dict) and 'coords' in loc:
    lat_gps = loc['coords']['latitude']
    lon_gps = loc['coords']['longitude']
    st.sidebar.caption(f"GPS Fijo: {lat_gps:.4f}, {lon_gps:.4f}")

# Buscador Dual
st.sidebar.subheader(f"Desbloquear {label_entidad[:-1]}")
metodo = st.sidebar.radio("Metodo:", ["Por Clic en Mapa / Lista", "Por Coordenadas"])

if metodo == "Por Clic en Mapa / Lista":
    st.sidebar.caption("💡 Haz clic sobre cualquier zona del mapa para inspeccionarla directamente.")
    sel = st.sidebar.selectbox("O selecciona de la lista:", ["-- Seleccionar --"] + sorted(list(catalogo.keys())))
    if sel != "-- Seleccionar --":
        t = catalogo[sel]
        st.session_state.punto_eval = {
            'lat': t['lat'], 'lon': t['lon'], 'nom': f"{t['nombre']} ({t['estado']})",
            'clave': t['clave'], 'vis': t['clave'] in claves_set
        }
else:
    with st.sidebar.form("form_coord"):
        lat_m = st.number_input("Latitud", value=lat_gps, format="%.6f")
        lon_m = st.number_input("Longitud", value=lon_gps, format="%.6f")
        if st.form_submit_button("Inspeccionar Coordenada"):
            pt = Point(lon_m, lat_m)
            match = gdf_actual[gdf_actual.contains(pt)]
            if not match.empty:
                r = match.iloc[0]
                cve = str(r['CVEGEO' if pais_sel == "Mexico" else 'FIPS']).zfill(5)
                nom = r.get('NOMGEO' if pais_sel == "Mexico" else 'NAME', 'Lugar')
                st.session_state.punto_eval = {
                    'lat': lat_m, 'lon': lon_m, 'nom': nom,
                    'clave': cve, 'vis': cve in claves_set
                }
            else:
                st.sidebar.warning("Coordenada fuera del territorio de la region.")
                st.session_state.punto_eval = None

# Panel de Confirmación
if st.session_state.punto_eval:
    info = st.session_state.punto_eval
    st.sidebar.markdown("---")
    st.sidebar.write(f"**Lugar:** {info['nom']}")
    st.sidebar.write(f"**Codigo ID:** {info['clave']}")
    if info['vis']:
        st.sidebar.info("Ya registrado en tu lista.")
    else:
        if st.sidebar.button("Confirmar y Desbloquear"):
            if pais_sel == "Mexico":
                nueva = pd.DataFrame([{'MapChart_ID': f"{info['nom']}_{info['clave']}", 'Municipio_Nombre': info['nom'], 'Estado_Sufijo': 'N/A', 'CVE_ENT': info['clave'][:2], 'Nom_Limpio': info['nom'].upper(), 'CVEGEO': info['clave']}])
            else:
                nueva = pd.DataFrame([{'FIPS': info['clave'], 'County_Nombre': info['nom'], 'Estado_Code': info['clave'][:2]}])
            
            df_up = pd.concat([df_vis, nueva], ignore_index=True)
            df_up.to_csv(csv_actual, index=False)
            st.session_state.punto_eval = None
            st.rerun()

# Mapa Interactivo Base
center = [st.session_state.punto_eval['lat'], st.session_state.punto_eval['lon']] if st.session_state.punto_eval else [lat_gps, lon_gps]
m = folium.Map(location=center, zoom_start=7 if pais_sel == "Estados Unidos" else 6, tiles=None)

# 1. Capas Base Disponibles
folium.TileLayer('Cartodb Positron', name='Mapa Claro (Defecto)').add_to(m)
folium.TileLayer('Cartodb dark_matter', name='Mapa Oscuro').add_to(m)
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri World Imagery',
    name='Satelital (Esri)',
    max_zoom=19
).add_to(m)

folium.Marker(location=[lat_gps, lon_gps], popup="GPS", icon=folium.Icon(color="red", icon="car", prefix="fa")).add_to(m)

if st.session_state.punto_eval:
    p = st.session_state.punto_eval
    folium.Marker(location=[p['lat'], p['lon']], popup=p['nom'], icon=folium.Icon(color="blue", icon="location-dot", prefix="fa")).add_to(m)

# 2. Estilo Ajustado (Opacidad más alta para ver el fondo claramente)
def estilo(feature):
    props = feature.get('properties', {})
    cve = str(props.get('CVEGEO' if pais_sel == "Mexico" else 'FIPS', '')).zfill(5)
    vis = cve in claves_set
    return {
        'fillColor': '#2ea44f' if vis else '#e3e8ec',
        'color': '#0d3818' if vis else '#57606a',
        'weight': 1.0 if vis else 0.3,
        'fillOpacity': 0.38 if vis else 0.08  # Opacidad reducida para no tapar terrenos/calles
    }

folium.GeoJson(
    geojson_data, 
    name="Capa de Territorio",
    style_function=estilo,
    tooltip=folium.GeoJsonTooltip(
        fields=['NOMGEO', 'ESTADO_ABBR'] if pais_sel == "Mexico" else ['NAME', 'STATE'], 
        aliases=['Lugar:', 'Estado:']
    )
).add_to(m)

# Control de Capas en la esquina superior derecha
folium.LayerControl(position='topright').add_to(m)

# Renderizado y Clics
mapa_out = st_folium(m, width=1300, height=720)

if mapa_out and mapa_out.get('last_clicked'):
    click_lat = mapa_out['last_clicked']['lat']
    click_lon = mapa_out['last_clicked']['lng']
    
    pt = Point(click_lon, click_lat)
    match = gdf_actual[gdf_actual.contains(pt)]
    
    if not match.empty:
        r = match.iloc[0]
        cve = str(r['CVEGEO' if pais_sel == "Mexico" else 'FIPS']).zfill(5)
        nom = r.get('NOMGEO' if pais_sel == "Mexico" else 'NAME', 'Lugar')
        est = r.get('ESTADO_ABBR' if pais_sel == "Mexico" else 'STATE', '')
        
        if not st.session_state.punto_eval or st.session_state.punto_eval['clave'] != cve:
            st.session_state.punto_eval = {
                'lat': click_lat, 'lon': click_lon, 'nom': f"{nom} ({est})",
                'clave': cve, 'vis': cve in claves_set
            }
            st.rerun()
