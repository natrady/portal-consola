import streamlit as st
import pandas as pd
import datetime
import os
import json
from io import BytesIO 
import gspread
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import requests

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA Y COLORES
# ==========================================
st.set_page_config(page_title="Portal Consola", page_icon="💻", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f1f2f2; }
    h1, h2, h3, h4 { color: #161a1d; }
    [data-testid="stMetricValue"] { color: #9b2247; font-weight: bold; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 2px solid #9b2247; }
    th { background-color: #9b2247 !important; color: white !important; }
    
    /* Clase maestra para nuestras tarjetas */
    .dashboard-card {
        background-color: #ffffff;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
        padding: 20px;
        margin-bottom: 20px;
        height: 100%;
    }
    
    /* Nueva regla: Convertir contenedores de Plotly en tarjetas */
    [data-testid="stPlotlyChart"] {
        background-color: #ffffff;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
        padding: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 🛑 SISTEMA DE LOGIN CON GOOGLE
# ==========================================
if 'logeado' not in st.session_state:
    st.session_state['logeado'] = False

# Leemos las llaves de Google desde nuestra bóveda
client_id = st.secrets["google_oauth"]["client_id"]
client_secret = st.secrets["google_oauth"]["client_secret"]
redirect_uri = "https://consola-verificaciondigital.streamlit.app"

if not st.session_state['logeado']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_espacio1, col_login, col_espacio3 = st.columns([1, 1.5, 1])
    
    with col_login:
        st.markdown("""
        <div class="dashboard-card" style="text-align: center; border-top: 5px solid #9b2247;">
            <h2 style="color: #161a1d; margin-bottom: 5px;">Portal Consola</h2>
            <p style="color: #6c757d; font-weight: bold; margin-bottom: 20px;">Acceso exclusivo</p>
        </div>
        """, unsafe_allow_html=True)

        # 1. Revisar si Google nos acaba de regresar a la página con un "código de acceso"
        if "code" in st.query_params:
            codigo_auth = st.query_params["code"]
            
            # Intercambiamos ese código por una credencial oficial
            token_url = "https://oauth2.googleapis.com/token"
            datos_token = {
                "code": codigo_auth,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
            respuesta_token = requests.post(token_url, data=datos_token)
            
            if respuesta_token.status_code == 200:
                access_token = respuesta_token.json().get("access_token")
                
                # Le preguntamos a Google el correo de la persona que acaba de entrar
                user_info_url = "https://www.googleapis.com/oauth2/v1/userinfo"
                respuesta_usuario = requests.get(user_info_url, headers={"Authorization": f"Bearer {access_token}"})
                correo_usuario = respuesta_usuario.json().get("email")
                
                # Revisamos si el correo está en nuestra Lista VIP de st.secrets
                credenciales_validas = st.secrets.get("usuarios", {})
                if correo_usuario in credenciales_validas:
                    st.session_state['logeado'] = True
                    st.session_state['usuario_actual'] = correo_usuario
                    st.query_params.clear() # Limpiamos la URL para que se vea bonita
                    st.rerun()
                else:
                    st.error(f"🚨 El correo {correo_usuario} no está en la lista de acceso.")
                    st.query_params.clear()
            else:
                st.error("🚨 Hubo un error al conectar con Google. Intenta de nuevo.")
                st.query_params.clear()

        # 2. Si no hay código, mostramos el botón visual para ir a Google
        else:
            # Usamos .strip() para borrar espacios accidentales en tu llave
            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id.strip()}&response_type=code&scope=openid%20email%20profile&redirect_uri={redirect_uri}"
            
            # Cambiamos target="_self" a target="_top" para evitar bloqueos de marcos
            st.markdown(f'''
                <a href="{auth_url}" target="_top" style="text-decoration: none;">
                    <div style="background-color: #ffffff; border: 1px solid #dadce0; border-radius: 4px; padding: 10px 15px; text-align: center; color: #3c4043; font-weight: 500; font-family: 'Google Sans',Roboto,Arial,sans-serif; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 2px 0 rgba(60,64,67,0.3); transition: background-color .218s ease, border-color .218s ease, box-shadow .218s ease;">
                        <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" style="width: 20px; height: 20px; margin-right: 10px;">
                        Continuar con Google
                    </div>
                </a>
            ''', unsafe_allow_html=True)

    # Detenemos la ejecución aquí si no están logueados
    st.stop()

# ==========================================
# AUTENTICACIÓN CON GOOGLE CLOUD (SECRETS)
# ==========================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

try:
    # Ahora leemos el JSON directamente desde los "secretos" de Streamlit en la nube
    # (O desde un archivo .streamlit/secrets.toml en tu computadora local)
    credenciales_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(credenciales_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    st.error(f"🚨 Error de autenticación. Revisa tus st.secrets. Detalle: {e}")
    gc = None
# IDs de tus Google Sheets
SHEET_PERSONAL_ID = "1WWJ1Y-Ay_iSJIOATMAEfBPEIDfhz2xdqsTnECojWSXo"
SHEET_PENDIENTES_ID = "1B1WQstMuWfvjh2wcAEtJS6FP78nbbTU6im2J7qzaYYo"
SHEET_CUBOS_ID = "1euu5Bu9cCgZwRstMQ1HXGyzH3z5HGxcWqi_Fh41oFoM"

# ==========================================
# DICCIONARIO DE HOMOLOGACIÓN DE REGIONES
# ==========================================
mapa_regiones = {
    "Centro 1": "C1", "C1": "C1",
    "Centro 2": "C2", "C2": "C2",
    "Norte": "N", "N": "N",
    "Sur": "Sur", 
    "Sur Sureste": "Ss", "Ss": "Ss",
    "AD": "AD", "Apoyo": "Apoyo"
}

# ==========================================
# FUNCIONES LECTORAS/ESCRITORAS (EN LA NUBE)
# ==========================================
@st.cache_data(ttl=600, show_spinner="Descargando Personal desde Google...")
def cargar_personal():
    if not gc: return pd.DataFrame()
    try:
        hoja = gc.open_by_key(SHEET_PERSONAL_ID).worksheet("Hoja 1")
        datos = hoja.get_all_records()
        df = pd.DataFrame(datos)
        
        if 'Inicio Incidencia (Fecha)' in df.columns:
            df['Inicio Incidencia (Fecha)'] = pd.to_datetime(df['Inicio Incidencia (Fecha)'], errors='coerce').dt.date
        if 'Fin Incidencia (Fecha)' in df.columns:
            df['Fin Incidencia (Fecha)'] = pd.to_datetime(df['Fin Incidencia (Fecha)'], errors='coerce').dt.date
        
        for col in ['Estado Asignado', 'Municipio Asignado', 'Prioridad', 'Observaciones Coord', 'Suma Pendientes']:
            if col not in df.columns:
                df[col] = ""
            df[col] = df[col].fillna("").astype(str) 
                
        hoy = datetime.date.today()
        def calcular_disponibilidad(fila):
            if pd.isna(fila.get('Nombre_ordenado')) or str(fila.get('Nombre_ordenado')).strip() == "" or pd.isna(fila.get('Región')):
                return ""
            inicio = fila.get('Inicio Incidencia (Fecha)')
            fin = fila.get('Fin Incidencia (Fecha)')
            
            if pd.notna(inicio) and pd.notna(fin):
                if inicio <= hoy <= fin:
                    return "No"
            return "Si"
        
        df['Disponibles'] = df.apply(calcular_disponibilidad, axis=1)
        df['Región'] = df['Región'].map(mapa_regiones).fillna(df['Región'])
        return df
    except Exception as e:
        st.error(f"Error leyendo Personal_DB en la nube: {e}")
        return pd.DataFrame()

def guardar_personal_nube(df_a_guardar):
    if not gc: return False
    try:
        ws = gc.open_by_key(SHEET_PERSONAL_ID).worksheet("Hoja 1")
        ws.clear() 
        
        df_clean = df_a_guardar.copy()
        for col in df_clean.columns:
            df_clean[col] = df_clean[col].astype(str).replace(["nan", "NaT", "None"], "")
            
        data_to_write = [df_clean.columns.tolist()] + df_clean.values.tolist()
        ws.update(values=data_to_write, range_name="A1")
        return True
    except Exception as e:
        st.error(f"❌ Error al guardar en Google Sheets: {e}")
        return False

def extraer_tabla_saltando_filas(doc, nombre_ws, indices_columnas, nombres_columnas):
    try:
        ws = doc.worksheet(nombre_ws)
        data = ws.get_all_values()
        if len(data) > 2:
            max_cols = max(len(r) for r in data)
            padded = [r + [""]*(max_cols - len(r)) for r in data[2:]]
            df_temp = pd.DataFrame(padded)
            df_temp = df_temp[indices_columnas]
            df_temp.columns = nombres_columnas
            df_temp = df_temp[df_temp["Estado"].astype(str).str.strip() != ""] 
            df_temp['Pendientes'] = pd.to_numeric(df_temp['Pendientes'], errors='coerce').fillna(0)
            return df_temp
        return None
    except:
        return None

@st.cache_data(ttl=600, show_spinner="Descargando Pendientes desde Google...")
def cargar_pendientes():
    if not gc: return None, None, None
    try:
        doc = gc.open_by_key(SHEET_PENDIENTES_ID)
        
        try:
            cat_data = doc.worksheet("Catálogo_Geográfico").get_all_records()
            cat = pd.DataFrame(cat_data)
            cat['Región'] = cat['Región'].map(mapa_regiones).fillna(cat['Región']) 
        except:
            cat = None

        pendientes = {}
        
        tabs_basicas = ["RE_P1", "RE_P2", "BB_P1", "BB_P2", "BB_P3", "BB_P4"]
        for tab in tabs_basicas:
            df_t = extraer_tabla_saltando_filas(doc, tab, [0, 3], ["Estado", "Pendientes"])
            if df_t is not None: pendientes[tab] = df_t
            
        df_tch = extraer_tabla_saltando_filas(doc, "TCH", [0, 1, 4], ["Estado", "Municipio", "Pendientes"])
        if df_tch is not None: pendientes["TCH"] = df_tch
        
        df_ct = extraer_tabla_saltando_filas(doc, "CT", [0, 1, 2], ["Estado", "Municipio", "Pendientes"])
        if df_ct is not None: pendientes["CT"] = df_ct

        fecha_mod = datetime.datetime.now() 
        return cat, pendientes, fecha_mod
    except Exception as e:
        st.error(f"Error al leer la base de Pendientes en la nube: {e}")
        return None, None, None

@st.cache_data(ttl=300, show_spinner="Descargando Cubos desde Google...")
def cargar_cubos(_df_personal):
    if not gc: return pd.DataFrame()
    try:
        doc = gc.open_by_key(SHEET_CUBOS_ID)
        dict_nombres = dict(zip(_df_personal['Nombre_Plataforma'].astype(str).str.strip().str.upper(), _df_personal['Nombre_ordenado']))
        
        base_unificada = []

        def procesar_hoja(nombre_hoja, idx_verificador, idx_folio, idx_estado, idx_resultado, idx_fecha, idx_hora, modulo):
            try:
                ws = doc.worksheet(nombre_hoja)
                data = ws.get_all_values()
                if len(data) < 3: return
                for fila in data[2:]:
                    if len(fila) <= max(idx_verificador, idx_folio) or str(fila[idx_folio]).strip() == "":
                        continue 
                    
                    nom_plat = str(fila[idx_verificador]).strip().upper()
                    nom_bonito = dict_nombres.get(nom_plat, f"⚠️ NO ENCONTRADO: {nom_plat}")
                    
                    base_unificada.append({
                        "Módulo": modulo,
                        "Verificador": nom_bonito,
                        "Folio": fila[idx_folio],
                        "Estado": fila[idx_estado] if len(fila) > idx_estado else "",
                        "Resultado": fila[idx_resultado] if len(fila) > idx_resultado else "",
                        "Fecha_Cruda": fila[idx_fecha] if len(fila) > idx_fecha else "",
                        "Hora_Fin": fila[idx_hora] if len(fila) > idx_hora else ""
                    })
            except Exception as e:
                pass 

        procesar_hoja("RE_Cubos", 3, 5, 7, 4, 11, 13, "RE")
        procesar_hoja("BB_Cubos", 2, 3, 7, 6, 13, 15, "BB")
        procesar_hoja("CT_Cubos", 2, 3, 5, 9, 11, 12, "CT")
        procesar_hoja("TCH_Cubos", 1, 3, 6, 8, 15, 16, "TCH") 

        df_final = pd.DataFrame(base_unificada)
        if df_final.empty:
            return df_final

        df_final['Hora_HHMM'] = pd.to_datetime(df_final['Hora_Fin'], errors='coerce').dt.strftime('%H:%M')
        df_final['Fecha'] = pd.to_datetime(df_final['Fecha_Cruda'], errors='coerce', dayfirst=True).dt.date
        df_final = df_final.drop_duplicates(subset=['Módulo', 'Folio', 'Hora_HHMM'])
        
        return df_final
    except Exception as e:
        st.error(f"Error maestro al leer Cubos_DB: {e}")
        return pd.DataFrame()

# -----------------------------------
df_global = cargar_personal()
df_catalogo, dict_pendientes, fecha_actualizacion = cargar_pendientes()

def dibujar_velocimetro(valor_actual, valor_esperado, titulo):
    esperado = valor_esperado * 100
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = valor_actual,
        title = {'text': f"<span style='color:#161a1d; font-size:24px; font-weight:bold;'>{titulo}</span>"},
        delta = {'reference': esperado, 'increasing': {'color': "#1e5b4f"}, 'decreasing': {'color': "#9b2247"}},
        number = {'suffix': "%", 'font': {'size': 60, 'color': '#9b2247'}}, # Número gigante y en color tinto
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 2, 'tickcolor': "#6c757d", 'tickfont': {'size': 14}},
            'bar': {'color': "#161a1d", 'thickness': 0.4}, # Aguja súper gruesa para que sea inconfundible
            'bgcolor': "#e9ecef", # Fondo del arco en gris claro sólido
            'borderwidth': 0,
            'steps': [
                {'range': [0, max(0, esperado - 5)], 'color': "#fdf3f5"}, # Zona tinto pastel
                {'range': [max(0, esperado - 5), min(100, esperado + 5)], 'color': "#eef8f6"}, # Zona verde pastel
                {'range': [min(100, esperado + 5), 100], 'color': "#fffaf0"}  # Zona dorada pastel
            ],
            'threshold': {
                'line': {'color': "#161a1d", 'width': 6},
                'thickness': 0.9,
                'value': esperado 
            }
        }
    ))
    
    fig.update_layout(
        height=360, 
        margin=dict(l=30, r=30, t=60, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    return fig
# ==========================================
# BARRA LATERAL Y OPCIONES GLOBALES
# ==========================================
st.sidebar.title("Menú Principal")
menu = st.sidebar.radio("Selecciona un Módulo:", ["👥 Personal", "🗺️ Distribución", "⏱️ Velocímetro", "📈 Tablero de Control", "🔮 Proyecciones (WIP)"])
st.sidebar.divider()
st.sidebar.caption("Portal Consola v1.0 (Cloud)")
st.sidebar.divider()

if st.sidebar.button("🔄 Actualizar Datos desde la Nube", use_container_width=True):
    cargar_personal.clear()
    cargar_pendientes.clear()
    cargar_cubos.clear()
    st.rerun()

opciones_region = ["C1", "C2", "N", "Sur", "Ss", "AD", "Apoyo"]
opciones_rol = ["Administrativo", "Verificador", "Coordinador", "Back"]
opciones_modulo = [None, "Ad", "Admin", "Coordinador", "RE", "BB", "CT", "TCH", "Vacaciones", "Incapacidad", "Capacitación", "Actividad Especial", "Apoyo"]

# ==========================================
# 👥 MÓDULO: PERSONAL
# ==========================================
if menu == "👥 Personal":
    st.title("👥 Módulo: Personal")
    st.markdown("Administración del equipo en la nube.")

    if not df_global.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Personal", len(df_global))
        col2.metric("Verificadores", len(df_global[df_global['Rol'] == 'Verificador']) if 'Rol' in df_global.columns else 0)
        col3.metric("Disponibles Hoy", len(df_global[df_global['Disponibles'] == 'Si']) if 'Disponibles' in df_global.columns else 0)
        col4.metric("Regiones Activas", df_global['Región'].nunique() if 'Región' in df_global.columns else 0)
        
        st.divider()

        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            lista_regiones = ["Todas"] + sorted([str(x) for x in df_global.get('Región', []).dropna().unique()])
            region_filtro = st.selectbox("Filtrar por Región:", lista_regiones)
        with col_filtro2:
            lista_roles = ["Todos"] + sorted([str(x) for x in df_global.get('Rol', []).dropna().unique()])
            rol_filtro = st.selectbox("Filtrar por Rol:", lista_roles)
        
        df_mostrar = df_global.copy()
        if region_filtro != "Todas":
            df_mostrar = df_mostrar[df_mostrar['Región'] == region_filtro]
        if rol_filtro != "Todos":
            df_mostrar = df_mostrar[df_mostrar['Rol'] == rol_filtro]
        
        df_editado = st.data_editor(
            df_mostrar,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Id_verificador": st.column_config.TextColumn("ID", disabled=True),
                "Nombre_Plataforma": st.column_config.TextColumn("Nombre Plataforma", disabled=True),
                "Nombre_ordenado": st.column_config.TextColumn("Nombre", disabled=True), 
                "Región": st.column_config.SelectboxColumn("Región", options=opciones_region),
                "Rol": st.column_config.SelectboxColumn("Rol", options=opciones_rol),
                "Módulo": st.column_config.SelectboxColumn("Módulo", options=opciones_modulo),
                "Inicio Incidencia (Fecha)": st.column_config.DateColumn("Inicio Incidencia"),
                "Fin Incidencia (Fecha)": st.column_config.DateColumn("Fin Incidencia"),
                "Disponibles": st.column_config.TextColumn("Disponibles", disabled=True),
                "Drive": st.column_config.TextColumn("Drive", disabled=True), 
                "Observaciones Coord": None 
            }
        )

        if st.button("☁️ Guardar Cambios en Google Sheets"):
            df_global.loc[df_editado.index] = df_editado
            df_guardar = df_global.drop(columns=['Disponibles'], errors='ignore')
            if guardar_personal_nube(df_guardar):
                cargar_personal.clear()
                st.success("✅ ¡Cambios guardados exitosamente en la nube!")
                st.rerun()

# ==========================================
# 🗺️ MÓDULO: DISTRIBUCIÓN
# ==========================================
elif menu == "🗺️ Distribución":
    st.title("🗺️ Asignación Operativa")
    
    if fecha_actualizacion:
        hora_str = fecha_actualizacion.strftime("%H:%M hrs")
        fecha_str = fecha_actualizacion.strftime("%d/%m/%Y")
        st.success(f"🟢 **Base de pendientes leída desde Google Sheets:** {fecha_str} a las {hora_str}")
    else:
        st.warning("⚠️ No se pudo conectar con el archivo de Pendientes en la nube.")

    if not df_global.empty:
        col_fecha, col_vacia = st.columns([1, 2])
        with col_fecha:
            fecha_distribucion = st.date_input("📅 ¿Para qué fecha es esta distribución?", value=datetime.date.today() + datetime.timedelta(days=1), min_value=datetime.date.today())

        def recalcular_disp(fila):
            if pd.isna(fila.get('Nombre_ordenado')) or pd.isna(fila.get('Región')): return ""
            inicio = fila.get('Inicio Incidencia (Fecha)')
            fin = fila.get('Fin Incidencia (Fecha)')
            if pd.notna(inicio) and pd.notna(fin):
                if inicio <= fecha_distribucion <= fin: return "No"
            return "Si"
        
        df_global['Disponibles'] = df_global.apply(recalcular_disp, axis=1)
        df_disponibles = df_global[df_global['Disponibles'] == 'Si'].copy()
        
        st.divider()

        regiones_activas = sorted([str(x) for x in df_disponibles['Región'].dropna().unique()])
        if "AD" not in regiones_activas:
            regiones_activas.append("AD")

        region_seleccionada = st.selectbox("📍 Selecciona tu Región para repartir trabajo:", ["Elige una opción..."] + regiones_activas)

        if region_seleccionada != "Elige una opción...":
            
            if region_seleccionada == "AD":
                st.markdown("### 🐱 Panel de Estrategia Global")
                try:
                    with open("estrategia_diaria.json", "r") as f:
                        est_guardada = json.load(f)
                except:
                    est_guardada = {"RE": 0, "BB": 0, "TCH": 0, "CT": 0, "Resto": "RE", "Meta_RE": 341, "Meta_BB": 341, "Meta_TCH": 130, "Meta_CT": 130}

                with st.expander("⚙️ Configurar Metas Base"):
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    with col_m1: meta_re = st.number_input("Meta RE:", min_value=1, value=int(est_guardada.get("Meta_RE", 341)))
                    with col_m2: meta_bb = st.number_input("Meta BB:", min_value=1, value=int(est_guardada.get("Meta_BB", 341)))
                    with col_m3: meta_tch = st.number_input("Meta TCH:", min_value=1, value=int(est_guardada.get("Meta_TCH", 130)))
                    with col_m4: meta_ct = st.number_input("Meta CT:", min_value=1, value=int(est_guardada.get("Meta_CT", 130)))

                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    st.write("**Asignación de personal por región:**")
                    q_re = st.number_input("Personas para RE (Aprendices):", min_value=0, value=int(est_guardada.get("RE", 0)))
                    q_bb = st.number_input("Personas para BB (BaBien):", min_value=0, value=int(est_guardada.get("BB", 0)))
                    q_tch = st.number_input("Personas para TCH (Tercer Check):", min_value=0, value=int(est_guardada.get("TCH", 0)))
                    q_ct = st.number_input("Personas para CT (Centros de Trabajo):", min_value=0, value=int(est_guardada.get("CT", 0)))
                
                with col_e2:
                    st.write("**Comodín y Mensaje:**")
                    opciones_comodin = ["Actividad especial"]
                    if q_ct == 0: opciones_comodin.insert(0, "CT")
                    if q_tch == 0: opciones_comodin.insert(0, "TCH")
                    if q_bb == 0: opciones_comodin.insert(0, "BB")
                    if q_re == 0: opciones_comodin.insert(0, "RE")

                    resto_guardado = est_guardada.get("Resto", "RE")
                    idx_resto = opciones_comodin.index(resto_guardado) if resto_guardado in opciones_comodin else len(opciones_comodin) - 1
                    
                    resto_a = st.selectbox("El resto de las personas se irán a:", opciones_comodin, index=idx_resto)
                    saludo = st.text_input("Saludo:", value="Buenas noches, compañeras/os, la distribución para mañana es:")
                    despedida = st.text_input("Despedida:", value="Gracias. 🌙")

                if st.button("📝 Generar Mensaje y Guardar Estrategia"):
                    partes = []
                    if q_re > 0: partes.append(f"{q_re} persona(s) por región en Revisión de Expedientes Aprendices")
                    if q_bb > 0: partes.append(f"{q_bb} persona(s) por región en Revisión de Expedientes BaBien")
                    if q_tch > 0: partes.append(f"{q_tch} persona(s) por región en Tercer Check")
                    if q_ct > 0: partes.append(f"{q_ct} persona(s) por región en Centros de Trabajo")
                    
                    texto_medio = ", ".join(partes)
                    nombres_modulos = {"RE": "Revisión de Expedientes de Aprendices", "BB": "Revisión de Expedientes BaBien", "TCH": "Tercer Check", "CT": "Centros de Trabajo", "Actividad especial": "Actividades Especiales"}
                    texto_final = f"{saludo} {texto_medio}; y el resto de personas en {nombres_modulos[resto_a]}. {despedida}"
                    
                    estrategia = {
                        "RE": q_re, "BB": q_bb, "TCH": q_tch, "CT": q_ct, "Resto": resto_a,
                        "Meta_RE": meta_re, "Meta_BB": meta_bb, "Meta_TCH": meta_tch, "Meta_CT": meta_ct
                    }
                    with open("estrategia_diaria.json", "w") as f:
                        json.dump(estrategia, f)
                    
                    st.success("✅ Estrategia guardada con éxito.")
                    st.text_area("Copia este mensaje para enviarlo:", value=texto_final, height=100)

            else:
                if df_catalogo is not None and dict_pendientes:
                    estados_region = df_catalogo[df_catalogo['Región'] == region_seleccionada]['Estado'].unique()
                    st.markdown("### 📋 Resumen de Pendientes")
                    resumen_data = {"RE (todas las prioridades)": 0, "BB (todas las prioridades)": 0, "CT": 0, "TCH": 0}
                    
                    for mod, df_mod in dict_pendientes.items():
                        df_filtrado = df_mod[df_mod['Estado'].isin(estados_region)]
                        total = int(df_filtrado['Pendientes'].sum()) if not df_filtrado.empty else 0
                        if "RE" in mod: resumen_data["RE (todas las prioridades)"] += total
                        elif "BB" in mod: resumen_data["BB (todas las prioridades)"] += total
                        elif mod == "CT": resumen_data["CT"] += total
                        elif mod == "TCH": resumen_data["TCH"] += total
                    
                    st.dataframe(pd.DataFrame(list(resumen_data.items()), columns=["Módulo", "Pendientes de la región"]), hide_index=True, use_container_width=True)

                    with st.expander("🔍 Explorar Detalles por Estado / Municipio", expanded=False):
                        modulo_visor = st.selectbox("¿De qué módulo quieres ver los folios?", list(dict_pendientes.keys()))
                        df_pendientes_modulo = dict_pendientes[modulo_visor]
                        df_filtrado = df_pendientes_modulo[df_pendientes_modulo['Estado'].isin(estados_region)]
                        df_filtrado = df_filtrado[df_filtrado['Pendientes'] > 0]
                        
                        if not df_filtrado.empty:
                            if 'Municipio' in df_filtrado.columns:
                                agrupado_estado = df_filtrado.groupby('Estado')['Pendientes'].sum().reset_index()
                                st.dataframe(agrupado_estado, hide_index=True, use_container_width=True)
                                estado_elegido = st.selectbox("👉 Elige un Estado:", ["..."] + list(agrupado_estado['Estado']))
                                if estado_elegido != "...":
                                    detalle_mun = df_filtrado[df_filtrado['Estado'] == estado_elegido]
                                    st.write(f"**Municipios de {estado_elegido}:**")
                                    st.dataframe(detalle_mun[['Municipio', 'Pendientes']], hide_index=True, use_container_width=True)
                            else:
                                st.dataframe(df_filtrado[['Estado', 'Pendientes']], hide_index=True, use_container_width=True)
                        else:
                            st.info("No hay pendientes para este módulo.")

                df_region = df_disponibles[df_disponibles['Región'] == region_seleccionada]
                columnas_distribucion = ['Nombre_ordenado', 'Módulo', 'Estado Asignado', 'Municipio Asignado', 'Suma Pendientes', 'Prioridad', 'Observaciones Coord']
                for col in columnas_distribucion:
                    if col not in df_region.columns: df_region[col] = ""
                
                df_vista_coord = df_region[columnas_distribucion].copy()

                st.divider()
                col_texto, col_dados = st.columns([3, 1])
                with col_texto:
                    st.write(f"Mostrando a **{len(df_region)}** personas disponibles para el **{fecha_distribucion.strftime('%d/%m/%Y')}**.")
                
                with col_dados:
                    if st.button("🎲 Tirar los Dados", help="Genera distribución automática cumpliendo metas o repartiendo equitativamente"):
                        import random
                        import math 
                        
                        try:
                            with open("estrategia_diaria.json", "r") as f:
                                estrategia = json.load(f)
                        except:
                            st.warning("⚠️ No hay estrategia AD. Se usará default.")
                            estrategia = {"RE": 0, "BB": 0, "TCH": 0, "CT": 0, "Resto": "RE", "Meta_RE":341, "Meta_BB":341, "Meta_TCH":130, "Meta_CT":130}

                        metas_dict = {"RE": estrategia.get("Meta_RE", 341), "BB": estrategia.get("Meta_BB", 341), "TCH": estrategia.get("Meta_TCH", 130), "CT": estrategia.get("Meta_CT", 130)}

                        total_personas = len(df_vista_coord)
                        asientos = []
                        asientos.extend(["RE"] * int(estrategia.get("RE", 0)))
                        asientos.extend(["BB"] * int(estrategia.get("BB", 0)))
                        asientos.extend(["TCH"] * int(estrategia.get("TCH", 0)))
                        asientos.extend(["CT"] * int(estrategia.get("CT", 0)))

                        if len(asientos) < total_personas:
                            asientos.extend([estrategia.get("Resto", "RE")] * (total_personas - len(asientos)))
                        elif len(asientos) > total_personas:
                            asientos = asientos[:total_personas] 
                        
                        random.shuffle(asientos)

                        inventario = []
                        for mod, df_mod in dict_pendientes.items():
                            df_f = df_mod[df_mod['Estado'].isin(estados_region)].copy()
                            df_f = df_f[df_f['Pendientes'] > 0]
                            if not df_f.empty:
                                df_f['Módulo_Origen'] = "RE" if "RE" in mod else ("BB" if "BB" in mod else mod)
                                
                                prioridad_str = ""
                                if "_P" in mod:
                                    prioridad_str = mod.split("_P")[1]
                                df_f['Prioridad_Origen'] = prioridad_str
                                df_f['Pendientes'] = df_f['Pendientes'].astype(float)

                                if df_catalogo is not None:
                                    df_f['Estado'] = df_f['Estado'].fillna("").astype(str)
                                    df_catalogo_tmp = df_catalogo.copy()
                                    df_catalogo_tmp['Estado'] = df_catalogo_tmp['Estado'].fillna("").astype(str)
                                    
                                    if 'Municipio' in df_f.columns and 'Municipio' in df_catalogo_tmp.columns:
                                        df_f['Municipio'] = df_f['Municipio'].fillna("").astype(str)
                                        df_catalogo_tmp['Municipio'] = df_catalogo_tmp['Municipio'].fillna("").astype(str)
                                        df_f = pd.merge(df_f, df_catalogo_tmp[['Estado', 'Municipio', 'Prioridad de asignación']], on=['Estado', 'Municipio'], how='left')
                                    else:
                                        df_cat_estado = df_catalogo_tmp[['Estado', 'Prioridad de asignación']].drop_duplicates(subset=['Estado'])
                                        df_f = pd.merge(df_f, df_cat_estado, on='Estado', how='left')
                                else:
                                    df_f['Prioridad de asignación'] = ""

                                def asignar_peso(val):
                                    val_str = str(val).lower()
                                    if "focalizado" in val_str: return 1
                                    elif "irregular" in val_str: return 3
                                    else: return 2
                                df_f['Peso_Prioridad'] = df_f['Prioridad de asignación'].apply(asignar_peso)
                                inventario.append(df_f)

                        df_pool = pd.concat(inventario, ignore_index=True) if inventario else pd.DataFrame()

                        conteo_asientos = {mod: asientos.count(mod) for mod in set(asientos)}
                        meta_ajustada = {}
                        for mod in ["RE", "BB", "TCH", "CT"]:
                            meta_original = metas_dict.get(mod, 50)
                            personas_mod = conteo_asientos.get(mod, 0)
                            if personas_mod > 0 and not df_pool.empty:
                                df_mod_pool = df_pool[df_pool['Módulo_Origen'] == mod]
                                total_pendientes_mod = df_mod_pool['Pendientes'].sum() if not df_mod_pool.empty else 0
                                if total_pendientes_mod < (meta_original * personas_mod):
                                    meta_ajustada[mod] = max(1, math.ceil(total_pendientes_mod / personas_mod))
                                else:
                                    meta_ajustada[mod] = meta_original
                            else:
                                 meta_ajustada[mod] = meta_original

                        for i in range(total_personas):
                            mod_asignado = asientos[i]
                            df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Módulo')] = mod_asignado

                            if mod_asignado == "Actividad especial":
                                df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Estado Asignado')] = "N/A"
                                df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Municipio Asignado')] = "Actividad Especial"
                                df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Suma Pendientes')] = "-"
                                df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = None
                                continue

                            meta_actual = meta_ajustada.get(mod_asignado, metas_dict.get(mod_asignado, 50))
                            
                            if not df_pool.empty:
                                tareas_modulo = df_pool[df_pool['Módulo_Origen'] == mod_asignado].sample(frac=1).sort_values(by='Peso_Prioridad')
                                
                                estados_asig = []
                                muns_asig = []
                                prioridades_asig = set() 
                                suma_asig = 0
                                
                                for idx, tarea in tareas_modulo.iterrows():
                                    if suma_asig >= meta_actual:
                                        break
                                        
                                    disponible = tarea['Pendientes']
                                    if disponible <= 0:
                                        continue
                                        
                                    necesario = meta_actual - suma_asig
                                    tomar = min(necesario, disponible)
                                    
                                    suma_asig += tomar
                                    df_pool.at[idx, 'Pendientes'] -= tomar
                                    
                                    estados_asig.append(str(tarea['Estado']))
                                    mun = str(tarea['Municipio']) if 'Municipio' in tarea and pd.notna(tarea['Municipio']) and str(tarea['Municipio']).strip() != "" else "Barrido"
                                    muns_asig.append(mun)
                                    
                                    if tarea['Prioridad_Origen']:
                                        prioridades_asig.add(tarea['Prioridad_Origen'])
                                
                                df_pool = df_pool[df_pool['Pendientes'] > 0]
                                
                                if estados_asig:
                                    ruta_asignada = list(zip(estados_asig, muns_asig))
                                    random.shuffle(ruta_asignada) 
                                    
                                    estados_revueltos = [par[0] for par in ruta_asignada]
                                    muns_revueltos = [par[1] for par in ruta_asignada]
                                    
                                    estados_unicos = list(dict.fromkeys(estados_revueltos)) 
                                    muns_unicos = list(dict.fromkeys(muns_revueltos)) 
                                    
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Estado Asignado')] = ", ".join(estados_unicos)
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Municipio Asignado')] = ", ".join(muns_unicos)
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Suma Pendientes')] = str(int(suma_asig))
                                    
                                    if mod_asignado in ["CT", "TCH"]:
                                        df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = None
                                    else:
                                        if prioridades_asig:
                                            df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = " y ".join(sorted(list(prioridades_asig)))
                                        else:
                                            df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = None
                                else:
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Estado Asignado')] = "Sin pendientes"
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Suma Pendientes')] = "0"
                                    df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = None
                            else:
                                 df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Estado Asignado')] = "Sin pendientes"
                                 df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Suma Pendientes')] = "0"
                                 df_vista_coord.iloc[i, df_vista_coord.columns.get_loc('Prioridad')] = None
                        
                        st.session_state[f'propuesta_{region_seleccionada}'] = df_vista_coord

                if f'propuesta_{region_seleccionada}' in st.session_state:
                    df_a_editar = st.session_state[f'propuesta_{region_seleccionada}']
                else:
                    df_a_editar = df_vista_coord

                df_distribucion_editada = st.data_editor(
                    df_a_editar, use_container_width=True, hide_index=True,
                    column_config={
                        "Nombre_ordenado": st.column_config.TextColumn("Nombre", disabled=True),
                        "Módulo": st.column_config.SelectboxColumn("Módulo", options=opciones_modulo),
                        "Estado Asignado": st.column_config.TextColumn("Estado"),
                        "Municipio Asignado": st.column_config.TextColumn("Municipio"),
                        "Suma Pendientes": st.column_config.TextColumn("Total Asignado", disabled=True),
                        "Prioridad": st.column_config.SelectboxColumn("Prioridad", options=[None, "1", "2", "3", "Urgente", "Especial"]),
                        "Observaciones Coord": st.column_config.TextColumn("Notas Extra")
                    }
                )

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("☁️ Guardar Asignaciones en Google Sheets"):
                        df_global.loc[df_distribucion_editada.index, columnas_distribucion] = df_distribucion_editada
                        df_guardar = df_global.drop(columns=['Disponibles'], errors='ignore')
                        if guardar_personal_nube(df_guardar):
                            cargar_personal.clear()
                            st.success("✅ Asignación guardada en la nube.")
                            st.rerun()

                with col_btn2:
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df_distribucion_editada.to_excel(writer, index=False, sheet_name=f'Distribucion_{region_seleccionada}')
                    st.download_button(
                        label="📥 Descargar Excel de Distribución",
                        data=output.getvalue(), file_name=f"Distribucion_{region_seleccionada}_{fecha_distribucion.strftime('%d-%m-%Y')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

# ==========================================
# Velocímetro
# ==========================================
elif menu == "⏱️ Velocímetro":
    st.title("⏱️ Velocímetro Operativo")
    
    col_v1, col_v2 = st.columns([1, 4])
    with col_v1:
        if st.button("🔄 Actualizar Cubos", use_container_width=True):
            cargar_cubos.clear() 
            st.rerun()
            
    with col_v2:
        st.markdown("Monitor de productividad en tiempo real. Analiza tiempos, pausas y ritmo de trabajo del equipo operativo.")
    
    st.divider()
    
    df_cubos = cargar_cubos(df_global)
    
    if df_cubos.empty:
        st.warning("📭 No se encontraron datos válidos en el Google Sheet de Cubos. Asegúrate de pegar la información a partir de la fila 3.")
    else:
        # --- 1. MATEMÁTICA DEL RITMO CONTRA META ---
        fechas_disponibles = sorted([f for f in df_cubos['Fecha'].unique() if pd.notna(f)], reverse=True)
        fecha_temp = fechas_disponibles[0] if fechas_disponibles else datetime.date.today()
        
        hoy = datetime.date.today()
        ahora = datetime.datetime.now().time()
        
        inicio_jornada = datetime.time(9, 0, 0)
        inicio_comida = datetime.time(15, 0, 0)
        fin_comida = datetime.time(16, 0, 0)
        fin_jornada = datetime.time(18, 0, 0)
        
        if ahora < inicio_jornada: horas_trans = 0.0
        elif ahora <= inicio_comida: horas_trans = (datetime.datetime.combine(hoy, ahora) - datetime.datetime.combine(hoy, inicio_jornada)).total_seconds() / 3600
        elif ahora <= fin_comida: horas_trans = 6.0 
        elif ahora <= fin_jornada: horas_trans = 6.0 + (datetime.datetime.combine(hoy, ahora) - datetime.datetime.combine(hoy, fin_comida)).total_seconds() / 3600
        else: horas_trans = 8.0 
        
        avance_esperado_hoy = horas_trans / 8.0

        # --- 2. VIAJE EN EL TIEMPO Y REGIONALIZACIÓN ---
        regiones_activas = ["Todas"] + sorted([str(x) for x in df_global['Región'].dropna().unique()])
        
        col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 1, 1])
        with col_f1:
            if fechas_disponibles:
                fecha_seleccionada = st.selectbox("📅 Día a analizar:", fechas_disponibles)
                df_filtrado = df_cubos[df_cubos['Fecha'] == fecha_seleccionada].copy()
            else:
                st.info("No hay fechas.")
                df_filtrado = df_cubos.copy()
                fecha_seleccionada = hoy
        
        with col_f2:
            region_seleccionada = st.selectbox("📍 Filtrar por Región:", regiones_activas)

        with col_f3:
            st.metric("Gestiones Totales", len(df_filtrado))
            
        with col_f4:
            if fecha_seleccionada < hoy: 
                avance_esperado = 1.0 
                texto_hora = "Jornada concluida"
            elif fecha_seleccionada > hoy: 
                avance_esperado = 0.0 
                texto_hora = "Jornada futura"
            else: 
                avance_esperado = avance_esperado_hoy
                texto_hora = f"A las {ahora.strftime('%H:%M')} hrs"
            
            st.metric("Meta de Tiempo", f"{avance_esperado:.0%}")
            st.caption(f"🕒 {texto_hora}")
        
        # --- 3. CÁLCULO DE TIEMPOS Y PAUSAS NETAS ---
        try:
            with open("estrategia_diaria.json", "r") as f:
                est_guardada = json.load(f)
        except:
            est_guardada = {"Meta_RE": 341, "Meta_BB": 341, "Meta_TCH": 130, "Meta_CT": 130}
            
        meta_re_val = est_guardada.get("Meta_RE", 341)
        meta_bb_val = est_guardada.get("Meta_BB", 341)
        meta_ct_val = est_guardada.get("Meta_CT", 130)
        meta_tch_val = est_guardada.get("Meta_TCH", 130)

        avg_re = 480 / meta_re_val if meta_re_val > 0 else 0
        avg_bb = 480 / meta_bb_val if meta_bb_val > 0 else 0
        avg_ct = 480 / meta_ct_val if meta_ct_val > 0 else 0
        avg_tch = 480 / meta_tch_val if meta_tch_val > 0 else 0
        dict_avg = {"RE": avg_re, "BB": avg_bb, "CT": avg_ct, "TCH": avg_tch}

        df_filtrado['Hora_Obj'] = pd.to_datetime(df_filtrado['Hora_HHMM'], format='%H:%M', errors='coerce')
        df_filtrado = df_filtrado.sort_values(['Verificador', 'Hora_Obj'])
        df_filtrado['Tiempo_Promedio'] = df_filtrado['Módulo'].map(dict_avg).fillna(0)
        
        df_filtrado['Diff_Minutos'] = df_filtrado.groupby('Verificador')['Hora_Obj'].diff().dt.total_seconds() / 60
        df_filtrado['Pausa_Minutos'] = df_filtrado['Diff_Minutos'] - df_filtrado['Tiempo_Promedio']
        
        metricas_tiempo = df_filtrado.groupby('Verificador').agg(Pausa_Maxima=('Pausa_Minutos', 'max')).reset_index()
        metricas_tiempo['Pausa_Maxima'] = metricas_tiempo['Pausa_Maxima'].fillna(0).astype(int)
        metricas_tiempo['Pausa_Maxima'] = metricas_tiempo['Pausa_Maxima'].apply(lambda x: x if x >= 20 else 0)

        def asignar_semaforo_pausa(pausa):
            if pausa >= 45: return "🔴 Crítico (>45m)"
            elif pausa >= 20: return "🟡 Alerta (>20m)"
            else: return "🟢 Activo"
        metricas_tiempo['Semáforo'] = metricas_tiempo['Pausa_Maxima'].apply(asignar_semaforo_pausa)
        
        tiempos_mod = df_filtrado.groupby(['Verificador', 'Módulo']).agg(In=('Hora_HHMM', 'min'), Out=('Hora_HHMM', 'max')).reset_index()
        tiempos_pivot = tiempos_mod.pivot(index='Verificador', columns='Módulo', values=['In', 'Out'])
        if not tiempos_pivot.empty:
            tiempos_pivot.columns = [f"{mod}_{col}" for col, mod in tiempos_pivot.columns]
        tiempos_pivot = tiempos_pivot.reset_index()

        # --- 4. CONSOLIDACIÓN DE ACTIVOS Y "MÓDULO INTELIGENTE" ---
        if 'Comentarios METAS' not in df_global.columns:
            df_global['Comentarios METAS'] = ""

        df_activos = df_global[df_global['Disponibles'] == 'Si'][['Nombre_ordenado', 'Región', 'Rol', 'Comentarios METAS', 'Módulo']].copy()
        df_activos.rename(columns={'Módulo': 'Actividad_Asignada'}, inplace=True)
        df_activos = df_activos[~df_activos['Actividad_Asignada'].isin(['Vacaciones', 'Incapacidad'])]

        if region_seleccionada != "Todas":
            df_activos = df_activos[df_activos['Región'] == region_seleccionada]

        folios_modulos = df_filtrado.groupby(['Verificador', 'Módulo']).size().unstack(fill_value=0).reset_index()
        for mod in ['RE', 'BB', 'CT', 'TCH']:
            if mod not in folios_modulos.columns: folios_modulos[mod] = 0
            
        resumen = pd.merge(df_activos, folios_modulos, left_on='Nombre_ordenado', right_on='Verificador', how='left')
        resumen['Verificador'] = resumen['Nombre_ordenado'] 
        
        for mod in ['RE', 'BB', 'CT', 'TCH']:
            resumen[mod] = resumen[mod].fillna(0).astype(int)
            
        resumen = pd.merge(resumen, metricas_tiempo, on='Verificador', how='left')
        resumen = pd.merge(resumen, tiempos_pivot, on='Verificador', how='left')

        resumen['Pausa_Maxima'] = resumen['Pausa_Maxima'].fillna(0).astype(int)
        resumen['Semáforo'] = resumen['Semáforo'].fillna("⚪ Sin Registro")
        resumen['Comentarios METAS'] = resumen['Comentarios METAS'].fillna("")

        for mod in ['RE', 'BB', 'CT', 'TCH']:
            if f"{mod}_In" not in resumen.columns: resumen[f"{mod}_In"] = ""
            if f"{mod}_Out" not in resumen.columns: resumen[f"{mod}_Out"] = ""
            resumen[f"{mod}_In"] = resumen[f"{mod}_In"].fillna("")
            resumen[f"{mod}_Out"] = resumen[f"{mod}_Out"].fillna("")

        def definir_modulo_real(fila):
            asignado = str(fila['Actividad_Asignada']).strip()
            p_re = fila['RE']/meta_re_val if meta_re_val > 0 else 0
            p_bb = fila['BB']/meta_bb_val if meta_bb_val > 0 else 0
            p_ct = fila['CT']/meta_ct_val if meta_ct_val > 0 else 0
            p_tch = fila['TCH']/meta_tch_val if meta_tch_val > 0 else 0
            
            dic_p = {'RE': p_re, 'BB': p_bb, 'CT': p_ct, 'TCH': p_tch}
            max_mod = max(dic_p, key=dic_p.get)
            max_val = dic_p[max_mod]
            
            if max_val == 0: return asignado 
            
            horas_in = []
            for m in ['RE', 'BB', 'CT', 'TCH']:
                if fila[f'{m}_In'] != "":
                    try: horas_in.append(datetime.datetime.strptime(fila[f'{m}_In'], '%H:%M').time())
                    except: pass
            
            if asignado.lower() in ['tarea especial', 'actividad especial', 'apoyo']:
                if horas_in:
                    primera_hora = min(horas_in)
                    if primera_hora >= datetime.time(14, 0): return asignado
                return max_mod 
            
            return max_mod 

        resumen['Actividad_Real'] = resumen.apply(definir_modulo_real, axis=1)

        def calcular_meta(fila):
            porcentaje = 0.0
            if meta_re_val > 0: porcentaje += fila['RE'] / meta_re_val
            if meta_bb_val > 0: porcentaje += fila['BB'] / meta_bb_val
            if meta_ct_val > 0: porcentaje += fila['CT'] / meta_ct_val
            if meta_tch_val > 0: porcentaje += fila['TCH'] / meta_tch_val
            return min(porcentaje * 100, 100.0) 
            
        resumen['Progreso'] = resumen.apply(calcular_meta, axis=1)
        
        def determinar_ritmo(fila):
            rol_lower = str(fila['Rol']).strip().lower()
            # Aquí es donde salvamos a los Jefes
            if rol_lower in ['coordinador', 'back', 'admin', 'administrativo', 'ad']: 
                return "Administrativo/Apoyo"
                
            if str(fila['Actividad_Real']).strip().lower() in ['tarea especial', 'actividad especial', 'apoyo']: 
                return "Actividad Especial"
            
            avance = fila['Progreso'] / 100.0 
            margen = 0.05
            if avance <= 0: return "Sin Inicio"
            if avance < (avance_esperado - margen): return "Ritmo Bajo"
            if avance > (avance_esperado + margen): return "Superando Ritmo"
            return "En Ritmo"
            
        resumen['Status'] = resumen.apply(determinar_ritmo, axis=1)
        
        # --- 5. RENDERIZADO VISUAL GAMIFICADO ---
        st.divider()
        st.markdown(f"### 🚀 Panel de Rendimiento: {region_seleccionada if region_seleccionada != 'Todas' else 'Todas las Regiones'}")
        
        # Filtramos Operativos (excluyendo a los Administrativos para no manchar las métricas)
        df_operativos = resumen[resumen['Status'] != 'Administrativo/Apoyo']
        total_activos = len(df_operativos)
        
        t_especial = len(df_operativos[df_operativos['Status'] == 'Actividad Especial'])
        t_super = len(df_operativos[df_operativos['Status'] == 'Superando Ritmo'])
        t_ritmo = len(df_operativos[df_operativos['Status'] == 'En Ritmo'])
        t_bajo = len(df_operativos[df_operativos['Status'] == 'Ritmo Bajo'])
        t_sin = len(df_operativos[df_operativos['Status'] == 'Sin Inicio'])

        promedio_region = df_operativos[~df_operativos['Status'].isin(['Actividad Especial', 'Sin Inicio'])]['Progreso'].mean() if len(df_operativos[~df_operativos['Status'].isin(['Actividad Especial', 'Sin Inicio'])]) > 0 else 0
        
        col_graf1, col_graf2 = st.columns([1.2, 1])
        
        with col_graf1:
            grafico_velocimetro = dibujar_velocimetro(promedio_region, avance_esperado, "Rendimiento Operativo (%)")
            st.plotly_chart(grafico_velocimetro, use_container_width=True)
            
            with st.expander("📖 ¿Cómo leer este gráfico?"):
                st.markdown(f"- 🎯 **La línea negra** marca la meta esperada a esta hora ({avance_esperado:.0%}).")
                st.markdown(f"- 🚗 **La aguja oscura** muestra el avance real promedio de los verificadores activos.")
                
        with col_graf2:
            st.markdown(f"""
            <div style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e9ecef; padding: 20px; margin-bottom: 20px;">
                <h4 style="margin-top: 0px; margin-bottom: 15px; color: #343a40; font-family: sans-serif;">Resumen del Equipo Operativo</h4>
                <table style="width:100%; text-align:left; border-collapse: collapse; font-family: sans-serif; font-size: 15px;">
                    <tr style="border-bottom: 1px solid #f1f3f5; background-color: #f8f9fa;">
                        <td style="padding: 10px; color: #495057;">🙋‍♀️ <b>Total Operativos</b></td>
                        <td style="padding: 10px; text-align: center; color: #495057;"><b>{total_activos}</b></td>
                        <td style="padding: 10px; text-align: right; color: #495057;"><b>100%</b></td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f3f5;">
                        <td style="padding: 10px; color: #6c757d;">📝 Actividad Especial</td>
                        <td style="padding: 10px; text-align: center; color: #6c757d;">{t_especial}</td>
                        <td style="padding: 10px; text-align: right; color: #6c757d;">{(t_especial/max(1, total_activos))*100:.1f}%</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f3f5; background-color: #fffaf0;">
                        <td style="padding: 10px; color: #a57f2c; font-weight: 600;">🚀 Superando Ritmo</td>
                        <td style="padding: 10px; text-align: center; color: #a57f2c; font-weight: 600;">{t_super}</td>
                        <td style="padding: 10px; text-align: right; color: #a57f2c; font-weight: 600;">{(t_super/max(1, total_activos))*100:.1f}%</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f3f5; background-color: #eef8f6;">
                        <td style="padding: 10px; color: #1e5b4f; font-weight: 600;">✅ En Ritmo</td>
                        <td style="padding: 10px; text-align: center; color: #1e5b4f; font-weight: 600;">{t_ritmo}</td>
                        <td style="padding: 10px; text-align: right; color: #1e5b4f; font-weight: 600;">{(t_ritmo/max(1, total_activos))*100:.1f}%</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #f1f3f5; background-color: #fdf3f5;">
                        <td style="padding: 10px; color: #9b2247; font-weight: 600;">⚠️ Ritmo Bajo</td>
                        <td style="padding: 10px; text-align: center; color: #9b2247; font-weight: 600;">{t_bajo}</td>
                        <td style="padding: 10px; text-align: right; color: #9b2247; font-weight: 600;">{(t_bajo/max(1, total_activos))*100:.1f}%</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; color: #adb5bd; font-style: italic;">💤 Sin Iniciar</td>
                        <td style="padding: 10px; text-align: center; color: #adb5bd; font-style: italic;">{t_sin}</td>
                        <td style="padding: 10px; text-align: right; color: #adb5bd; font-style: italic;">{(t_sin/max(1, total_activos))*100:.1f}%</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)
            
            # --- INTELIGENCIA DE NOTAS AUTOMÁTICAS ---
            total_pendientes_region = 0
            if dict_pendientes and df_catalogo is not None:
                for mod, df_mod in dict_pendientes.items():
                    if region_seleccionada != "Todas":
                        estados_region = df_catalogo[df_catalogo['Región'] == region_seleccionada]['Estado'].unique()
                        df_f = df_mod[df_mod['Estado'].isin(estados_region)]
                    else:
                        df_f = df_mod
                    if not df_f.empty and 'Pendientes' in df_f.columns:
                        total_pendientes_region += df_f['Pendientes'].sum()

            capacidad_requerida = total_activos * 200 # Promedio de meta para medir el agua a los camotes
            mensajes_inteligentes = []
            
            if 0 < total_pendientes_region < capacidad_requerida:
                mensajes_inteligentes.append(f"⚠️ Bajo volumen de pendientes ({total_pendientes_region:,.0f} disponibles vs capacidad operativa).")
            if total_activos > 0 and (t_especial / total_activos) >= 0.3:
                mensajes_inteligentes.append("📝 Actividad especial prioritaria en la región (más del 30% asignados).")
            if total_activos > 0 and (t_bajo / total_activos) >= 0.5:
                mensajes_inteligentes.append("🚨 Posible lentitud en plataforma (el 50% del equipo registra ritmo bajo).")
            
            nota_sugerida = " | ".join(mensajes_inteligentes) if mensajes_inteligentes else ""
            
            # Buscamos si ya habías guardado una nota antes
            clave_nota = f"Nota_Op_{region_seleccionada}_{fecha_seleccionada}"
            nota_guardada = est_guardada.get(clave_nota, nota_sugerida)

            # Cuadro editable
            nota_actual = st.text_area("🤖 Análisis Inteligente / Notas Operativas:", value=nota_guardada, height=90)
            
            # Botón para guardar tu nota manual o la autogenerada
            if st.button("💾 Guardar Nota", key="btn_nota"):
                est_guardada[clave_nota] = nota_actual
                try:
                    with open("estrategia_diaria.json", "w") as f:
                        json.dump(est_guardada, f)
                    st.success("Nota operativa guardada con éxito.")
                except:
                    st.error("Error al guardar la nota.")
            
        if t_bajo > 0 or t_sin > 0:
            nombres_atrasados = resumen[resumen['Status'].isin(['Ritmo Bajo', 'Sin Inicio'])]['Verificador'].tolist()
            st.error(f"🚨 **Atención Coordis:** El siguiente personal tiene ritmo bajo o no ha iniciado: {', '.join(nombres_atrasados)}")
        
        st.markdown("### 📋 Pista de Carreras (Detalle Operativo)")
        
        columnas_ordenadas = [
            'Verificador', 'Región', 'Actividad_Real', 'Semáforo', 'Pausa_Maxima', 
            'CT', 'CT_In', 'CT_Out', 
            'TCH', 'TCH_In', 'TCH_Out', 
            'RE', 'RE_In', 'RE_Out', 
            'BB', 'BB_In', 'BB_Out', 
            'Progreso', 'Status', 'Comentarios METAS'
        ]
        
        def pintar_filas(row):
            color = ""
            status = row['Status']
            if status == "Ritmo Bajo": color = "#9b2247" 
            elif status == "En Ritmo": color = "#1e5b4f" 
            elif status == "Superando Ritmo": color = "#a57f2c" 
            elif status == "Sin Inicio": color = "#D4AFB9" 
            elif status == "Actividad Especial": color = "#B0BEC5" 
            elif status == "Administrativo/Apoyo": color = "#98989A" 
            
            styles = []
            for col in columnas_ordenadas:
                if col == 'Progreso':
                    styles.append('background-color: white; color: black; font-weight: bold')
                elif color:
                    styles.append(f'background-color: {color}; color: white; font-weight: bold; border-bottom: 1px solid #fff')
                else:
                    styles.append('')
            return styles

        df_mostrar = resumen[columnas_ordenadas].sort_values(by='Progreso', ascending=False)
        
        st.dataframe(
            df_mostrar.style.apply(pintar_filas, axis=1),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Actividad_Real": st.column_config.TextColumn("Módulo Actual"),
                "Pausa_Maxima": st.column_config.NumberColumn("Max. Pausa (min)"),
                "CT": st.column_config.NumberColumn("CT Folios"),
                "RE": st.column_config.NumberColumn("RE Folios"),
                "BB": st.column_config.NumberColumn("BB Folios"),
                "TCH": st.column_config.NumberColumn("TCH Folios"),
                "Progreso": st.column_config.ProgressColumn(
                    "Avance Total", 
                    format="%d%%", 
                    min_value=0, 
                    max_value=100
                ),
                # MAGIA AQUI: Hacemos la columna gigante para que el texto luzca.
                "Comentarios METAS": st.column_config.TextColumn(
                    "Notas / Justificación",
                    width="large" 
                )
            }
        )

# ==========================================
# LOS OTROS MÓDULOS
# ==========================================
elif menu == "📈 Tablero de Control":
    st.title("📈 Tablero de Control")
    st.markdown("Visión gerencial de la operación: volumetría global, capacidad y distribución del trabajo de Verificación Digital.")
    st.divider()

    if dict_pendientes is None or df_global.empty:
        st.warning("⚠️ Faltan datos de la nube para calcular las métricas globales.")
    else:
        # --- 1. CÁLCULO DE KPIs GLOBALES ---
        total_pendientes = 0
        desglose_pendientes = {"RE": 0, "BB": 0, "CT": 0, "TCH": 0}
        
        for mod, df_mod in dict_pendientes.items():
            if not df_mod.empty and 'Pendientes' in df_mod.columns:
                suma = int(df_mod['Pendientes'].sum())
                total_pendientes += suma
                if "RE" in mod: desglose_pendientes["RE"] += suma
                elif "BB" in mod: desglose_pendientes["BB"] += suma
                elif mod == "CT": desglose_pendientes["CT"] += suma
                elif mod == "TCH": desglose_pendientes["TCH"] += suma

        # Capacidad operativa (excluyendo administrativos)
        df_activos = df_global[df_global['Disponibles'] == 'Si']
        if 'Rol' in df_activos.columns:
            roles_admin = ['coordinador', 'back', 'admin', 'administrativo', 'ad']
            operativos_totales = len(df_activos[~df_activos['Rol'].astype(str).str.strip().str.lower().isin(roles_admin)])
        else:
            operativos_totales = len(df_activos)
            
        # --- NUEVA LÓGICA: MATEMÁTICA DE TIEMPO Y METAS ---
        metas_min = {"RE": 280, "BB": 280, "CT": 93, "TCH": 104}
        metas_ideal = {"RE": 341, "BB": 341, "CT": 130, "TCH": 130}

        # 1. ¿Cuántas horas le quedan al día según la hora de actualización?
        if fecha_actualizacion and fecha_actualizacion.date() == datetime.date.today():
            hora_act = fecha_actualizacion.time()
        else:
            hora_act = datetime.time(9, 0, 0) # Si es de otro día, simulamos jornada completa

        h_act = hora_act.hour + hora_act.minute / 60.0
        if h_act >= 18: horas_restantes = 0.0
        elif h_act >= 16: horas_restantes = 18.0 - h_act
        elif h_act >= 15: horas_restantes = 2.0 # Si está en comida, le quedan 2 horas (16 a 18)
        elif h_act >= 9: horas_restantes = (15.0 - h_act) + 2.0
        else: horas_restantes = 8.0
            
        # 2. ¿Cuántas Horas-Gente requiere la bandeja actual?
        ph_req_min = sum(desglose_pendientes[m] / (metas_min[m] / 8.0) for m in ["RE", "BB", "CT", "TCH"])
        ph_req_ideal = sum(desglose_pendientes[m] / (metas_ideal[m] / 8.0) for m in ["RE", "BB", "CT", "TCH"])
        
        # 3. ¿Cuántas Horas-Gente tenemos disponibles?
        ph_disp = operativos_totales * horas_restantes
        
        # 4. Proporción ponderada según la mezcla de pendientes
        if total_pendientes > 0:
            cap_restante_ideal = int(ph_disp * (total_pendientes / ph_req_ideal)) if ph_req_ideal > 0 else 0
            cap_restante_min = int(ph_disp * (total_pendientes / ph_req_min)) if ph_req_min > 0 else 0
        else:
            cap_restante_ideal = int(ph_disp * (341/8.0)) # Default a meta RE si no hay pendientes
            cap_restante_min = int(ph_disp * (280/8.0))

        # --- RENDERIZADO DE KPIs DINÁMICOS ---
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            st.metric("📦 Total de Pendientes", f"{total_pendientes:,}")
            if fecha_actualizacion:
                st.caption(f"🕒 Base leída a las: {fecha_actualizacion.strftime('%H:%M')} hrs")
        with col_k2:
            st.metric("🧑‍💻 Fuerza Verificadora", operativos_totales)
            st.caption(f"⏱️ Restan {horas_restantes:.1f} hrs de jornada")
        with col_k3:
            st.metric("⚠️ Capacidad Restante (Mínima)", f"{cap_restante_min:,}")
            dif_min = cap_restante_min - total_pendientes
            st.caption(f"🔴 Faltarían {abs(dif_min):,} folios" if dif_min < 0 else "🟢 Alcanza para vaciar")
        with col_k4:
            st.metric("⚡ Capacidad Restante (Ideal)", f"{cap_restante_ideal:,}")
            dif_id = cap_restante_ideal - total_pendientes
            st.caption(f"🔴 Faltarían {abs(dif_id):,} folios" if dif_id < 0 else "🟢 Alcanza para vaciar")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # --- 2. GRÁFICAS GERENCIALES ---
        
        # --- 2. GRÁFICAS GERENCIALES ---
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("### 📊 Volumetría por Módulo")
            
            df_vol = pd.DataFrame(list(desglose_pendientes.items()), columns=['Módulo', 'Pendientes'])
            df_vol = df_vol[df_vol['Pendientes'] > 0]
            
            colores_modulos = ['#9b2247', '#1e5b4f', '#a57f2c', '#343a40']
            
            fig_vol = go.Figure(data=[go.Pie(
                labels=df_vol['Módulo'], 
                values=df_vol['Pendientes'], 
                hole=.4,
                marker=dict(colors=colores_modulos, line=dict(color='#ffffff', width=2)),
                textinfo='label+value+percent', # Agregamos el "value" para que muestre el número real
                textfont=dict(size=14, color='#ffffff')
            )])
            
            fig_vol.update_layout(
                margin=dict(t=30, b=30, l=10, r=10),
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=350
            )
            st.plotly_chart(fig_vol, use_container_width=True)

        with col_g2:
            st.markdown("### 🗺️ Carga de Trabajo por Región")
            
            if df_catalogo is not None:
                regiones_validas = [r for r in df_global['Región'].dropna().unique() if r not in ["AD", "Apoyo"]]
                modulos_list = ['RE', 'BB', 'CT', 'TCH']
                
                # Creamos un diccionario anidado para llevar la cuenta por región y por módulo
                pendientes_region_mod = {reg: {m: 0 for m in modulos_list} for reg in regiones_validas}
                mapa_geo = df_catalogo[['Estado', 'Región']].drop_duplicates()
                
                for mod, df_mod in dict_pendientes.items():
                    if not df_mod.empty and 'Pendientes' in df_mod.columns and 'Estado' in df_mod.columns:
                        df_merged = pd.merge(df_mod, mapa_geo, on='Estado', how='left')
                        agrupado = df_merged.groupby('Región')['Pendientes'].sum().to_dict()
                        
                        base_mod = "RE" if "RE" in mod else ("BB" if "BB" in mod else mod)
                        
                        for reg, val in agrupado.items():
                            if pd.notna(reg) and reg in pendientes_region_mod:
                                pendientes_region_mod[reg][base_mod] += val
                                
                # Transformamos la data para que Plotly la entienda en modo apilado
                datos_barras = []
                for reg, mods in pendientes_region_mod.items():
                    total_reg = sum(mods.values())
                    if total_reg > 0:
                        datos_barras.append({'Región': reg, 'Total': total_reg, **mods})
                
                df_barras = pd.DataFrame(datos_barras)
                
                if not df_barras.empty:
                    df_barras = df_barras.sort_values('Total', ascending=True)
                    fig_reg = go.Figure()
                    colores_dict = {'RE': '#9b2247', 'BB': '#1e5b4f', 'CT': '#a57f2c', 'TCH': '#343a40'}
                    
                    for m in modulos_list:
                        # Agregamos una capa (trace) por cada módulo
                        fig_reg.add_trace(go.Bar(
                            y=df_barras['Región'],
                            x=df_barras[m],
                            name=m,
                            orientation='h',
                            marker_color=colores_dict[m],
                            text=df_barras[m].replace(0, ''), # Ocultamos los 0 para no saturar
                            textposition='inside',
                            textfont=dict(color='white', size=12, family='sans-serif')
                        ))
                        
                    fig_reg.update_layout(
                        barmode='stack', # Esto es lo que hace que se subdividan en lugar de encimarse
                        margin=dict(t=10, b=10, l=10, r=10),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        height=350,
                        xaxis=dict(showgrid=False, showticklabels=False),
                        yaxis=dict(title="", tickfont=dict(size=14, color='#343a40', family='sans-serif')),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1) # Leyenda arriba
                    )
                    st.plotly_chart(fig_reg, use_container_width=True)
                else:
                    st.success("🎉 ¡No hay pendientes asignados a las regiones!")
            else:
                st.warning("⚠️ No hay catálogo geográfico para cruzar las regiones.")
# --- 3. GAMIFICACIÓN: RANKING DE REGIONES (MURO DE LA FAMA) ---
        st.divider()
        
        # 1. Calculamos la meta esperada (LA VARIABLE QUE FALTABA)
        ahora_rank = datetime.datetime.now().time()
        ini_j = datetime.time(9, 0, 0); ini_c = datetime.time(15, 0, 0)
        fin_c = datetime.time(16, 0, 0); fin_j = datetime.time(18, 0, 0)
        
        if ahora_rank < ini_j: h_trans = 0.0
        elif ahora_rank <= ini_c: h_trans = (datetime.datetime.combine(datetime.date.today(), ahora_rank) - datetime.datetime.combine(datetime.date.today(), ini_j)).total_seconds() / 3600
        elif ahora_rank <= fin_c: h_trans = 6.0
        elif ahora_rank <= fin_j: h_trans = 6.0 + (datetime.datetime.combine(datetime.date.today(), ahora_rank) - datetime.datetime.combine(datetime.date.today(), fin_c)).total_seconds() / 3600
        else: h_trans = 8.0
        avance_esperado_rank = (h_trans / 8.0) * 100
        
        # 2. Imprimimos el Título con la meta "al ladito"
        st.markdown(f"### 🏆 Muro de la Fama <span style='font-size: 18px; color: #6c757d; font-weight: normal;'>| Meta esperada a esta hora: <b>{avance_esperado_rank:.1f}%</b></span>", unsafe_allow_html=True)
        st.caption("Pasa el mouse sobre las tarjetas para revelar la radiografía operativa de cada región. 🔄")
        
        # 3. Inyectamos el CSS para el efecto 3D "Flip Card"
        st.markdown("""
        <style>
        .flip-card {
            background-color: transparent;
            height: 290px;
            perspective: 1000px;
            margin-bottom: 15px;
        }
        .flip-card-inner {
            position: relative;
            width: 100%;
            height: 100%;
            text-align: center;
            transition: transform 0.6s;
            transform-style: preserve-3d;
        }
        .flip-card:hover .flip-card-inner {
            transform: rotateY(180deg);
        }
        .flip-card-front, .flip-card-back {
            position: absolute;
            width: 100%;
            height: 100%;
            -webkit-backface-visibility: hidden;
            backface-visibility: hidden;
            border-radius: 12px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.08);
            border: 1px solid #e9ecef;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .flip-card-front {
            background-color: #ffffff;
            align-items: center;
        }
        .flip-card-back {
            background-color: #f8f9fa;
            color: #161a1d;
            transform: rotateY(180deg);
            text-align: left;
            padding: 15px;
            justify-content: flex-start;
        }
        .back-title { font-weight: bold; color: #9b2247; font-size: 16px; margin-bottom: 8px; border-bottom: 1px solid #dee2e6; padding-bottom: 4px;}
        .back-item { font-size: 15px; margin-bottom: 8px; line-height: 1.3; }
        .back-icon { font-size: 16px; margin-right: 5px; }
        </style>
        """, unsafe_allow_html=True)

        # 4. Llamamos a los cubos desde la memoria caché
        df_cubos_ranking = cargar_cubos(df_global)
        
        if not df_cubos_ranking.empty and not df_activos.empty:
            hoy_ranking = datetime.date.today()
            df_cubos_hoy = df_cubos_ranking[df_cubos_ranking['Fecha'] == hoy_ranking].copy()
            
            df_hist_reg = pd.merge(df_cubos_ranking, df_activos[['Nombre_ordenado', 'Región']], left_on='Verificador', right_on='Nombre_ordenado', how='inner')
            
            if not df_cubos_hoy.empty:
                folios_mod_rank = df_cubos_hoy.groupby(['Verificador', 'Módulo']).size().unstack(fill_value=0).reset_index()
                for m in ['RE', 'BB', 'CT', 'TCH']:
                    if m not in folios_mod_rank.columns: folios_mod_rank[m] = 0
                
                # Filtro Anti-Jefes
                df_rank_bruto = pd.merge(df_activos[['Nombre_ordenado', 'Región', 'Rol']], folios_mod_rank, left_on='Nombre_ordenado', right_on='Verificador', how='inner')
                roles_admin = ['coordinador', 'back', 'admin', 'administrativo', 'ad']
                df_rank = df_rank_bruto[~df_rank_bruto['Rol'].astype(str).str.strip().str.lower().isin(roles_admin)].copy()
                
                def calc_avance_rank(fila):
                    p = (fila['RE']/341.0) + (fila['BB']/341.0) + (fila['CT']/130.0) + (fila['TCH']/130.0)
                    return min(p * 100, 100.0)
                df_rank['Avance'] = df_rank.apply(calc_avance_rank, axis=1)
                
                df_cubos_hoy_reg = pd.merge(df_cubos_hoy, df_activos[['Nombre_ordenado', 'Región']], left_on='Verificador', right_on='Nombre_ordenado', how='inner')
                df_cubos_hoy_reg['Solo_Hora'] = df_cubos_hoy_reg['Hora_HHMM'].str[:2]
                
                ranking = df_rank.groupby('Región')['Avance'].mean().reset_index()
                ranking = ranking.sort_values('Avance', ascending=False).reset_index(drop=True)
                
                cols_rank = st.columns(len(ranking))
                medallas = ["🥇", "🥈", "🥉", "🏃‍♀️", "🐢", "🐌", "🛋️"]
                
                for i, (idx, row) in enumerate(ranking.iterrows()):
                    reg = row['Región']
                    avance = row['Avance']
                    medalla = medallas[i] if i < len(medallas) else "⭐"
                    
                    if i == 0: color_borde = "#a57f2c"; color_texto = "#a57f2c"
                    elif i < 3: color_borde = "#1e5b4f"; color_texto = "#1e5b4f"
                    else: color_borde = "#9b2247"; color_texto = "#9b2247"
                    
                    pend_actuales = sum(pendientes_region_mod.get(reg, {}).values()) if 'pendientes_region_mod' in locals() else 0
                    texto_pendientes = f"{int(pend_actuales):,}" if pend_actuales > 0 else "¡Bandeja vacía! 🎉"
                    
                    df_reg_rank = df_rank[df_rank['Región'] == reg]
                    if not df_reg_rank.empty:
                        nom_estrella = df_reg_rank.loc[df_reg_rank['Avance'].idxmax()]['Nombre_ordenado'].split()
                        nom_empuje = df_reg_rank.loc[df_reg_rank['Avance'].idxmin()]['Nombre_ordenado'].split()
                        estrella = " ".join(nom_estrella[:2]) if len(nom_estrella) > 0 else "N/A"
                        necesita_empuje = " ".join(nom_empuje[:2]) if len(nom_empuje) > 0 else "N/A"
                    else:
                        estrella, necesita_empuje = "N/A", "N/A"
                        
                    df_h_reg = df_cubos_hoy_reg[df_cubos_hoy_reg['Región'] == reg]
                    if not df_h_reg.empty:
                        if not df_h_reg['Solo_Hora'].isna().all():
                            hora_moda = df_h_reg['Solo_Hora'].mode()[0]
                            hora_pico = f"{hora_moda}:00 a {int(hora_moda)+1}:00 hrs"
                        else:
                            hora_pico = "Sin datos"
                            
                        if not df_h_reg['Módulo'].isna().all():
                            mod_top = df_h_reg['Módulo'].value_counts().idxmax()
                        else:
                            mod_top = "N/A"
                    else:
                        hora_pico = "Sin datos"
                        mod_top = "N/A"
                        
                    acum_reg = len(df_hist_reg[df_hist_reg['Región'] == reg])
                    
                    # 5. RENDERIZADO HTML (Sin la etiqueta de Meta en el frente)
                    with cols_rank[i]:
                        tarjeta_html = f"""<div class="flip-card"><div class="flip-card-inner"><div class="flip-card-front" style="border-top: 5px solid {color_borde};"><h1 style="margin:0; font-size: 3rem;">{medalla}</h1><h3 style="margin: 10px 0 5px 0; color: #161a1d; font-family: sans-serif;">{reg}</h3><p style="font-size: 26px; font-weight: 900; color: {color_texto}; margin: 0; font-family: 'Arial Black', sans-serif;">{avance:.1f}%</p></div><div class="flip-card-back" style="border-top: 5px solid {color_borde};"><div class="back-title">Radiografía: {reg}</div><div class="back-item"><span class="back-icon">📦</span> <b>Pendientes:</b> {texto_pendientes}</div><div class="back-item"><span class="back-icon">⭐</span> <b>Líder:</b> {estrella}</div><div class="back-item"><span class="back-icon">🎯</span> <b>Apoyo a:</b> {necesita_empuje}</div><div class="back-item"><span class="back-icon">🔥</span> <b>Módulo Top:</b> {mod_top}</div><div class="back-item"><span class="back-icon">⏱️</span> <b>Hora pico:</b> {hora_pico}</div><div class="back-item" style="margin-top: 6px; color:#1e5b4f;"><span class="back-icon">📈</span> <b>Total procesado:</b> {acum_reg:,} f.</div></div></div></div>"""
                        st.markdown(tarjeta_html, unsafe_allow_html=True)
            else:
                st.info("💤 Aún no hay folios registrados el día de hoy para armar el ranking.")
        else:
            st.warning("⚠️ Faltan datos operativos para generar el ranking.")
# ==========================================
# 🔮 MÓDULO: PROYECCIONES
# ==========================================
elif menu == "🔮 Proyecciones (WIP)":
    st.title("🔮 Calculadora a Largo Plazo")
    st.info("🚧 Módulo en construcción. Aquí integraremos algoritmos para predecir requerimientos de personal a futuro.")
