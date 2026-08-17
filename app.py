import streamlit as st
import pandas as pd
import json
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point
from streamlit_js_eval import get_geolocation

st.set_page_config(page_title="México Map Explorer - ATS Ultra", layout="wide")

CSV_PATH = "mis_293_municipios_CON_CLAVE.csv"
GEOJSON_PATH = "municipios_mexico_simple.json"

# 1. Carga ultra-rápida indexada en GeoPandas
@st.cache_data
def cargar_base_espacial():
    gdf = gpd.read_file(GEOJSON_PATH)
    gdf['CVEGEO'] = gdf['CVEGEO'].astype(str).str.zfill(5)
    
    # Calcular centroides para búsqueda rápida por nombre
    gdf['centroide'] = gdf.geometry.centroid
    gdf['lat_cent'] = gdf['centroide'].y
    gdf['lon_cent'] = gdf['centroide'].x
    
    # Crear diccionario de búsqueda por Nombre
    cat_nombres = {}
    for _, row in gdf.iterrows():
        etiqueta = f"{row.get('NOMGEO', 'Municipio')} ({row['CVEGEO'][:2]})"
        cat_nombres[etiqueta] = {
            'cvegeo': row['CVEGEO'],
            'nomgeo': row.get('NOMGEO', 'Municipio'),
            'lat': row['lat_cent'],
            'lon': row['lon_cent']
        }
        
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        geojson = json.load(f)
        
    return gdf, cat_nombres, geojson

def cargar_visitados():
    df = pd.read_csv(CSV_PATH, dtype=str)
    return df

gdf_mexico, catálogo_nombres, geojson_data = cargar_base_espacial()
df_visitados = cargar_visitados()
claves_set = set(df_visitados['CVEGEO'].dropna().str.zfill(5))

# 2. Interface Lateral
st.title("🇲🇽 México Map Explorer")
st.sidebar.header("Progreso de Exploración")

total_visitados = len(claves_set)
porcentaje = (total_visitados / 2478) * 100

st.sidebar.metric("Municipios Desbloqueados", f"{total_visitados} / 2,478", f"{porcentaje:.1f}%")
st.sidebar.progress(porcentaje / 100)

st.sidebar.markdown("---")

# 3. GPS Nativo
loc = get_geolocation()
lat_gps, lon_gps = 20.6760, -103.3470

if loc and 'coords' in loc:
    lat_gps = loc['coords']['latitude']
    lon_gps = loc['coords']['longitude']
    st.sidebar.caption(f"📡 GPS Fijo: {lat_gps:.4f}, {lon_gps:.4f}")

# 4. Buscador Dual: Por Coordenadas O Por Nombre
st.sidebar.subheader("🔍 Desbloquear Municipio")
metodo_busqueda = st.sidebar.radio("Método de búsqueda:", ["Por Nombre / Lista", "Por Coordenadas (GPS)"])

if "punto_evaluado" not in st.session_state:
    st.session_state.punto_evaluado = None

if metodo_busqueda == "Por Nombre / Lista":
    opcion_sel = st.sidebar.selectbox("Selecciona o escribe un municipio:", ["-- Seleccionar --"] + sorted(list(catálogo_nombres.keys())))
    
    if opcion_sel != "-- Seleccionar --":
        target = catálogo_nombres[opcion_sel]
        st.session_state.punto_evaluado = {
            'lat': target['lat'],
            'lon': target['lon'],
            'nomgeo': target['nomgeo'],
            'cvegeo': target['cvegeo'],
            'ya_visitado': target['cvegeo'] in claves_set
        }

else:
    with st.sidebar.form("form_coordenadas"):
        lat_manual = st.number_input("Latitud", value=lat_gps, format="%.6f")
        lon_manual = st.number_input("Longitud", value=lon_gps, format="%.6f")
        btn_evaluar = st.form_submit_button("📍 Inspeccionar Coordenada")
        
    if btn_evaluar:
        punto = Point(lon_manual, lat_manual)
        # Búsqueda con índice espacial R-Tree (Cero Latencia)
        posibles = gdf_mexico[gdf_mexico.sindex.contains(punto)]
        coincidencia = posibles[posibles.contains(punto)]
        
        if not coincidencia.empty:
            row = coincidencia.iloc[0]
            cve = str(row['CVEGEO']).zfill(5)
            nom = row.get('NOMGEO', 'Municipio')
            st.session_state.punto_evaluado = {
                'lat': lat_manual,
                'lon': lon_manual,
                'nomgeo': nom,
                'cvegeo': cve,
                'ya_visitado': cve in claves_set
            }
        else:
            st.sidebar.warning("⚠️ Coordenada fuera del territorio.")
            st.session_state.punto_evaluado = None

# Panel de Confirmación
if st.session_state.punto_evaluado:
    info = st.session_state.punto_evaluado
    st.sidebar.markdown("---")
    st.sidebar.write(f"**Ubicación:** {info['nomgeo']}")
    st.sidebar.write(f"**Clave:** {info['cvegeo']}")
    
    if info['ya_visitado']:
        st.sidebar.info("✅ Este municipio ya está registrado.")
    else:
        st.sidebar.warning("⚡ Pendiente de desbloqueo.")
        if st.sidebar.button("🏆 Confirmar y Desbloquear"):
            nueva_fila = pd.DataFrame([{
                'MapChart_ID': f"{info['nomgeo']}_{info['cvegeo']}",
                'Municipio_Nombre': info['nomgeo'],
                'Estado_Sufijo': 'N/A',
                'CVE_ENT': info['cvegeo'][:2],
                'Nom_Limpio': info['nomgeo'].upper(),
                'CVEGEO': info['cvegeo']
            }])
            
            df_actualizado = pd.concat([df_visitados, nueva_fila], ignore_index=True)
            df_actualizado.to_csv(CSV_PATH, index=False)
            st.session_state.punto_evaluado = None
            st.sidebar.balloons()
            st.rerun()

# 5. Mapa Interactivo
centro = [st.session_state.punto_evaluado['lat'], st.session_state.punto_evaluado['lon']] if st.session_state.punto_evaluado else [lat_gps, lon_gps]

m = folium.Map(location=centro, zoom_start=8, tiles="Cartodb Positron")

# Pin Rojo GPS
folium.Marker(location=[lat_gps, lon_gps], popup="Tu GPS", icon=folium.Icon(color="red", icon="car", prefix="fa")).add_to(m)

# Pin Azul Inspección
if st.session_state.punto_evaluado:
    p = st.session_state.punto_evaluado
    folium.Marker(location=[p['lat'], p['lon']], popup=f"Seleccionado: {p['nomgeo']}", icon=folium.Icon(color="blue", icon="location-dot", prefix="fa")).add_to(m)

def estilo_municipio(feature):
    cvegeo = str(feature.get('properties', {}).get('CVEGEO', '')).zfill(5)
    es_vis = cvegeo in claves_set
    return {
        'fillColor': '#2ea44f' if es_vis else '#e3e8ec',
        'color': '#134e23' if es_vis else '#8c959f',
        'weight': 0.6 if es_vis else 0.15,
        'fillOpacity': 0.85 if es_vis else 0.2
    }

folium.GeoJson(
    geojson_data,
    style_function=estilo_municipio,
    tooltip=folium.GeoJsonTooltip(fields=['NOMGEO'], aliases=['Municipio:'])
).add_to(m)

st_folium(m, width=1300, height=720)