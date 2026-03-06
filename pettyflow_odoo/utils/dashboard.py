import streamlit as st
import pandas as pd
import json
import os
import requests
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="APROBABOT Dashboard", page_icon="🤖", layout="wide")

# Rutas de datos
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SOLICITUDES_PATH = os.path.join(BASE_DIR, '.agent', 'data', 'solicitudes.json')
DISCORD_API_URL = "http://localhost:5000/aprobar"

def load_data():
    if os.path.exists(SOLICITUDES_PATH):
        try:
            with open(SOLICITUDES_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

# Sidebar para seguridad
st.sidebar.title("🔐 Acceso Administrativo")
user_email = st.sidebar.text_input("Ingresa tu correo corporativo:", type="default")
is_admin = user_email.lower() == "estefaniao@solenium.co"

if not is_admin:
    st.sidebar.warning("Acceso de solo lectura. Solo estefaniao@solenium.co puede aprobar.")

st.title("🤖 APROBABOT - Dashboard Administrativo")
st.markdown("---")

# Cargar y mostrar datos
data = load_data()
if not data:
    st.info("No hay solicitudes registradas por el momento.")
else:
    df = pd.DataFrame(data)
    
    # Formateo de tabla
    def color_status(status):
        if status == "Pendiente": return "background-color: #ffffcc; color: black;" # Amarillo
        if status == "Aprobado": return "background-color: #cce5ff; color: black;" # Azul
        if status == "Recargado": return "background-color: #d4edda; color: black;" # Verde
        return ""

    # Mostrar métricas rápidas
    c1, c2, c3 = st.columns(3)
    c1.metric("Pendientes", len(df[df['estado'] == 'Pendiente']))
    c2.metric("Aprobados", len(df[df['estado'] == 'Aprobado']))
    c3.metric("Recargados", len(df[df['estado'] == 'Recargado']))

    st.subheader("📋 Historial de Solicitudes")
    
    # Renderizar tabla con estilos
    df_display = df[['id', 'usuario', 'correo', 'monto', 'fecha', 'estado']].copy()
    st.dataframe(df_display.style.applymap(color_status, subset=['estado']), use_container_width=True)

    # Sección de Acciones
    if is_admin:
        st.subheader("⚡ Acciones de Control")
        pendientes = df[df['estado'] == 'Pendiente']
        if not pendientes.empty:
            selected_id = st.selectbox("Selecciona ID para APROBAR:", pendientes['id'])
            if st.button("✅ APROBAR SOLICITUD"):
                row = pendientes[pendientes['id'] == selected_id].iloc[0]
                try:
                    payload = {
                        "usuario": row['usuario'],
                        "monto": int(row['monto']),
                        "admin_email": user_email
                    }
                    resp = requests.post(DISCORD_API_URL, json=payload, timeout=5)
                    if resp.status_code == 200:
                        st.success(f"¡Solicitud {selected_id} aprobada! El bot ha enviado la notificación.")
                        # Recargar datos localmente para mostrar cambios inmediatos
                        st.rerun()
                    else:
                        st.error(f"Error al comunicar con el Bot: {resp.text}")
                except Exception as e:
                    st.error(f"El Bot no está respondiendo. Asegúrate de que discord_bot.py esté corriendo. ({e})")
        else:
            st.write("No hay solicitudes pendientes de aprobación.")
    else:
        st.info("💡 Inicia sesión como administrador para habilitar los botones de aprobación.")

# Footer
st.markdown("---")
st.caption("APROBABOT Dashboard v1.0 | Solenium")
