import os
import sys
import threading
import time
import io
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
from PIL import Image
import qrcode
import base64

try:
    import zxingcpp
except ImportError:
    zxingcpp = None

from config import settings
from services.stock_service import StockService
from services.sync_service import sync_service, LiveSyncService
from services.tunnel_service import TunnelService
from services.recipe_service import recipe_service
from models.schemas import StockItem

CLOUD_APP_URL = "https://bm-stockapp.streamlit.app"
RECETAS_SHEET_URL = "https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit#gid=1917609246"

# Detección de Plataforma: PC (Escritorio / .exe) vs Celular (Nube / QR)
# Regla estricta del usuario: "Solo agregar eso en la app de pc, no en la de celular"
query_app = str(st.query_params.get("app", "")).lower().strip()
if query_app in ("mobile", "celular"):
    is_pc_app = False
elif query_app == "pc":
    is_pc_app = True
else:
    user_agent = ""
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers") and st.context.headers:
            user_agent = str(st.context.headers.get("user-agent", "")).lower()
    except Exception:
        user_agent = ""

    if any(m in user_agent for m in ("android", "iphone", "ipad", "ipod", "mobile")):
        is_pc_app = False
    else:
        # Por defecto: Si corre en Windows o es ejecutable .exe, es la app de PC.
        # En Streamlit Cloud / Linux, es la app de celular.
        is_pc_app = (os.name == 'nt') or getattr(sys, 'frozen', False)

def generate_qr_base64(data_url: str, box_size: int = 6) -> str:
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=2,
        )
        qr.add_data(data_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""

def _load_base64_asset(filepath: str) -> str:
    try:
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

bm_icon_b64 = _load_base64_asset("assets/icon_bm_192.png") or _load_base64_asset("assets/icon_bm_square.png")

st.set_page_config(
    page_title="Control de Stock BM",
    page_icon="assets/icon_bm_square.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Asegurar que la API de sincronización en tiempo real esté activa en puerto 8000
def _ensure_api_running():
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        res = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        if res != 0:
            from uvicorn import Config, Server
            from api.main import app as fastapi_app
            config = Config(app=fastapi_app, host="0.0.0.0", port=8000, log_level="error")
            server = Server(config)
            t = threading.Thread(target=server.run, daemon=True)
            t.start()
    except Exception:
        pass

_ensure_api_running()

# Estilos CSS adaptados para Celular y PC (Mobile-First y Alto Impacto)
st.markdown("""
<style>
    @keyframes pulse {
        0% { transform: scale(0.98); opacity: 0.85; }
        50% { transform: scale(1.02); opacity: 1; }
        100% { transform: scale(0.98); opacity: 0.85; }
    }
    .scanner-live-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #ecfdf5;
        border: 1px solid #10b981;
        color: #065f46;
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 700;
        animation: pulse 2.5s infinite;
    }
    .scanner-live-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
    }
    .stButton>button {
        border-radius: 10px;
        font-weight: bold;
        min-height: 48px;
    }
    .sheets-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
        color: white;
        padding: 0.7rem 1.1rem;
        border-radius: 10px;
        margin-bottom: 0.8rem;
    }
    .sheet-title {
        font-size: 1.3rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .sheet-subtitle {
        font-size: 0.8rem;
        color: #94a3b8;
        margin-top: 0.15rem;
    }
    .scanner-hero-box {
        background: #eff6ff;
        border: 2px solid #3b82f6;
        border-radius: 12px;
        padding: 1.1rem;
        margin-bottom: 1rem;
    }
    .product-hero-card {
        background: #ffffff;
        border: 2.5px solid #2563eb;
        border-radius: 14px;
        padding: 1.2rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    }
    .product-hero-title {
        font-size: 1.6rem;
        font-weight: 900;
        color: #1e293b;
        margin: 0 0 6px 0;
        line-height: 1.2;
    }
    .badge-critical {
        background-color: #fee2e2;
        border: 1px solid #f87171;
        color: #991b1b;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.9rem;
        display: inline-block;
    }
    .badge-ok {
        background-color: #dcfce7;
        border: 1px solid #4ade80;
        color: #166534;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 0.9rem;
        display: inline-block;
    }
    .calc-preview-bar {
        background: #f0fdf4;
        border: 1px solid #86efac;
        color: #166534;
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.95rem;
        margin-top: 10px;
        margin-bottom: 12px;
    }
    .tab-badge {
        background: #e0f2fe;
        color: #0369a1;
        padding: 5px 12px;
        border-radius: 16px;
        font-weight: 700;
        font-size: 0.85rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# Instancia del servicio de stock y túnel remoto
service = StockService()
TunnelService.start_tunnel_in_background(port=8501)
local_ip = LiveSyncService.get_local_ip()
tunnel_url = TunnelService.get_saved_url()
mobile_url = tunnel_url or f"http://{local_ip}:8501"

# Despertar automáticamente en segundo plano la app en la nube (Streamlit Cloud)
def _wake_cloud_app_silent():
    try:
        import httpx
        httpx.get(f"{CLOUD_APP_URL}/?app=mobile", timeout=4.0)
    except Exception:
        pass

if is_pc_app and "cloud_app_woken" not in st.session_state:
    st.session_state.cloud_app_woken = True
    threading.Thread(target=_wake_cloud_app_silent, daemon=True).start()

# Inicialización de estado de sesión
if "sync_version" not in st.session_state:
    st.session_state.sync_version = 0
if "sync_mode" not in st.session_state:
    st.session_state.sync_mode = "MIRROR"  # Por defecto ESPEJO EN TIEMPO REAL: el escaneo en PC se ve inmediatamente en el celular
if "active_barcode" not in st.session_state:
    st.session_state.active_barcode = ""
if "scan_history" not in st.session_state:
    st.session_state.scan_history = []
if "show_success_msg" not in st.session_state:
    st.session_state.show_success_msg = None
if "cam_counter" not in st.session_state:
    st.session_state.cam_counter = 0

# Sincronización en vivo entre PC y Celulares mediante fragmento nativo (0.5 segundos de intervalo)
@st.fragment(run_every=0.5)
def live_sync_watcher():
    shared_state = sync_service.get_state()
    server_version = shared_state.get("version", 0)
    prev_ver = st.session_state.get("sync_version", 0)
    
    if server_version > prev_ver:
        st.session_state.sync_version = server_version
        action = shared_state.get("action")
        src = shared_state.get("source", "Dispositivo")
        ts = shared_state.get("timestamp", 0)
        
        # En modo Espejo (por defecto), clonar escaneo de otro dispositivo inmediatamente
        if st.session_state.get("sync_mode", "MIRROR") == "MIRROR":
            if action == "SCAN":
                scanned_code = shared_state.get("barcode", "")
                if scanned_code:
                    # Sincronizar si es un escaneo nuevo o reciente (<5 min)
                    if prev_ver > 0 or (time.time() - ts < 300):
                        if st.session_state.get("active_barcode") != scanned_code:
                            st.session_state.active_barcode = scanned_code
                            st.session_state.show_success_msg = None
                            st.rerun(scope="app")
            elif action == "CLEAR":
                if st.session_state.get("active_barcode"):
                    st.session_state.active_barcode = ""
                    st.rerun(scope="app")
            elif action == "SAVED":
                p_name = shared_state.get("product_name", "")
                n_stock = shared_state.get("new_stock", 0.0)
                if p_name:
                    st.session_state.show_success_msg = f"🎉 Stock de **{p_name}** actualizado a **{n_stock:g}** ({src}) en Google Sheets."
                st.session_state.active_barcode = ""
                st.rerun(scope="app")

        # En modo Independiente, solo notificar guardados sin cambiar la pantalla activa
        elif action == "SAVED":
            p_name = shared_state.get("product_name", "")
            n_stock = shared_state.get("new_stock", 0.0)
            if p_name:
                st.toast(f"⚡ Stock de **{p_name}** actualizado a **{n_stock:g}** ({src}) en Google Sheets", icon="📊")

live_sync_watcher()

# Pestaña semanal automática (Calculada con la fecha del lunes de la semana actual)
current_week_tab = service.get_current_week_tab_name()
available_tabs = service.get_available_tabs()
if current_week_tab not in available_tabs:
    available_tabs.insert(0, current_week_tab)

if "active_tab" not in st.session_state or not st.session_state.active_tab:
    st.session_state.active_tab = current_week_tab

# Cargar inventario de la pestaña activa con recuperación segura
try:
    items = service.get_inventory(tab_name=st.session_state.active_tab)
except Exception as e:
    st.warning(f"Aviso al cargar stock de la pestaña {st.session_state.active_tab}: {e}")
    items = []

# Mapeo de insumos para selector
item_map = {f"[{i.barcode}] {i.description} (Stock: {i.current_stock:g} {i.unit})": i.barcode for i in items}

# --- BARRA LATERAL (SIDEBAR) PARA ACCESO RÁPIDO EN PC Y CELULAR ---
with st.sidebar:
    st.image("assets/logo_bm.png", width=180)
    st.markdown("### **Control de Stock BM**")
    st.caption("Fábrica de Sillones • Buena Madera")
    st.divider()

    # Selector de Módulo (ÚNICAMENTE EN LA APP DE PC)
    if is_pc_app:
        st.markdown("#### 📌 **Módulo de Trabajo**")
        app_module = st.radio(
            "Seleccionar módulo:",
            ["📦 Control de Stock & Escáner", "🏭 Pedidos de Fabricación & Recetas"],
            key="sb_pc_module_choice",
            label_visibility="collapsed"
        )
        st.divider()
    else:
        app_module = "📦 Control de Stock & Escáner"
    
    st.markdown("#### 📅 **Pestaña Semanal**")
    tab_sb_idx = available_tabs.index(st.session_state.active_tab) if st.session_state.active_tab in available_tabs else 0
    sb_tab_choice = st.selectbox(
        "Pestaña activa:",
        available_tabs,
        index=tab_sb_idx,
        key="sb_tab_selector_nav",
        help="Selecciona qué pestaña semanal ver o editar."
    )
    if sb_tab_choice != st.session_state.active_tab:
        st.session_state.active_tab = sb_tab_choice
        st.rerun()
        
    st.markdown("""
    <a href="https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit" target="_blank" style="display: block; text-align: center; background-color: #0284c7; color: white; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.85rem; margin: 8px 0;">
        📊 Abrir Google Sheets ↗
    </a>
    """, unsafe_allow_html=True)
    
    if st.button("🔄 Refrescar Planilla", use_container_width=True, key="sb_btn_refresh"):
        items = service.get_inventory(tab_name=st.session_state.active_tab, force_refresh=True)
        available_tabs = service.get_available_tabs(force_refresh=True)
        st.toast("Datos sincronizados con Google Sheets", icon="🔄")
        st.rerun()
        
    if is_pc_app:
        st.divider()
        st.markdown("#### 📱 **Conexión Celular (4G / Wi-Fi)**")
        
        # Selector de modo de sincronización
        mode_options = ["Espejo en Tiempo Real (Recomendado)", "Independiente (Sin clonar pantalla)"]
        cur_mode_idx = 0 if st.session_state.get("sync_mode") == "MIRROR" else 1
        selected_mode = st.radio(
            "Modo de trabajo:",
            mode_options,
            index=cur_mode_idx,
            key="sb_sync_mode_radio",
            help="En modo Espejo, cuando el lector NICTOM escanea en la PC, el producto y sus datos aparecen inmediatamente en el celular en tiempo real."
        )
        st.session_state.sync_mode = "MIRROR" if selected_mode == "Espejo en Tiempo Real (Recomendado)" else "INDEPENDENT"

        # Conexión Directa en el Taller (Wi-Fi Local o Túnel) - NO duerme y refleja al instante
        active_tunnel = TunnelService.get_saved_url()
        base_live = active_tunnel or f"http://{local_ip}:8501"
        live_mirror_url = base_live + ("&app=mobile" if "?" in base_live else "/?app=mobile")
        qr_live_b64 = generate_qr_base64(live_mirror_url, box_size=6)

        st.markdown("**⚡ Conectar Celular al Escáner:**")
        if qr_live_b64:
            st.markdown(f'''
            <div style="text-align: center; margin: 6px 0; background: white; padding: 8px; border-radius: 10px; border: 1.5px solid #16a34a; box-shadow: 0 2px 6px rgba(0,0,0,0.06);">
                <img src="data:image/png;base64,{qr_live_b64}" width="145" style="border-radius: 6px; display: block; margin: 0 auto;"><br>
                <a href="{live_mirror_url}" target="_blank" style="font-size: 0.80rem; font-weight: bold; color: #166534; text-decoration: none;">
                    {live_mirror_url} ↗
                </a>
            </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown(f"👉 [{live_mirror_url}]({live_mirror_url})")
        st.caption("✨ **Recomendado en el taller:** Refleja el lector NICTOM al instante y **nunca se va a dormir**.")

        with st.expander("🌐 App Permanente en la Nube (PC apagada)"):
            mobile_cloud_url = f"{CLOUD_APP_URL}/?app=mobile"
            qr_cloud_b64 = generate_qr_base64(mobile_cloud_url, box_size=5)
            if qr_cloud_b64:
                st.markdown(f'''
                <div style="text-align: center; margin: 4px 0; background: white; padding: 6px; border-radius: 8px; border: 1px solid #0284c7;">
                    <img src="data:image/png;base64,{qr_cloud_b64}" width="125" style="border-radius: 6px; display: block; margin: 0 auto;"><br>
                    <a href="{mobile_cloud_url}" target="_blank" style="font-size: 0.78rem; font-weight: bold; color: #0284c7; text-decoration: none;">
                        {CLOUD_APP_URL} ↗
                    </a>
                </div>
                ''', unsafe_allow_html=True)
            st.caption("📱 Para consultar stock fuera del taller con la PC apagada. Si Streamlit dice que se durmió, toca el botón azul para reactivarla.")


def render_manufacturing_module(items, available_tabs, stock_service_instance):
    """
    Módulo exclusivo para la PC:
    - Carga de nuevos pedidos de fabricación según modelo y tipo de tela.
    - Previsualización inteligente del stock y semáforo de faltantes.
    - Botón 'Confirmar pedido' que descuenta automáticamente del stock en Google Sheets.
    - Historial de pedidos confirmados.
    - Edición y consulta interactiva de la hoja RECETAS de Google Sheets.
    """
    st.markdown(f"""
    <div class="sheets-header">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 14px;">
                <img src="data:image/png;base64,{bm_icon_b64}" width="42" height="42" style="border-radius: 9px; vertical-align: middle; box-shadow: 0 2px 6px rgba(0,0,0,0.35); border: 1.5px solid rgba(255,255,255,0.35);">
                <div>
                    <h1 class="sheet-title">🏭 Pedidos de Fabricación & Recetas</h1>
                    <p class="sheet-subtitle">Buena Madera • Descuento automático de stock en: <b>{st.session_state.active_tab}</b></p>
                </div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <a href="{RECETAS_SHEET_URL}" target="_blank" style="background-color: #0284c7; color: white; padding: 7px 14px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 0.85rem;">
                    📊 Abrir Hoja RECETAS en Google Sheets ↗
                </a>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Mensaje de confirmación reciente si existe
    if st.session_state.get("show_success_msg"):
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #dcfce7, #bbf7d0); border: 2px solid #22c55e; border-radius: 12px; padding: 14px 18px; margin: 10px 0 16px 0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div style="font-size: 1.05rem; font-weight: 700; color: #15803d;">
                    {st.session_state.show_success_msg}
                </div>
                <a href="https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit" target="_blank" style="background-color: #15803d; color: white; padding: 7px 12px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 0.85rem;">
                    📊 Ver Stock Actualizado en Sheets ↗
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Selector de Pestaña Semanal de Destino
    col_t_top1, col_t_top2 = st.columns([6, 4])
    with col_t_top1:
        tab_idx = available_tabs.index(st.session_state.active_tab) if st.session_state.active_tab in available_tabs else 0
        sel_tab = st.selectbox(
            "📅 Pestaña Activa de Stock (Donde se descontarán los insumos):",
            available_tabs,
            index=tab_idx,
            key="mfg_tab_selector",
            help="Al confirmar el pedido, las cantidades se restarán de la columna 'Cant. Inventario' de esta semana."
        )
        if sel_tab != st.session_state.active_tab:
            st.session_state.active_tab = sel_tab
            st.rerun()

    with col_t_top2:
        st.write("")
        st.write("")
        col_t_b1, col_t_b2 = st.columns(2)
        with col_t_b1:
            if st.button("🔄 Refrescar Stock", use_container_width=True, key="mfg_btn_refresh_stock"):
                stock_service_instance.get_inventory(tab_name=st.session_state.active_tab, force_refresh=True)
                st.toast("Stock sincronizado con Google Sheets", icon="🔄")
                st.rerun()
        with col_t_b2:
            st.markdown("""
            <a href="https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit" target="_blank" style="display: block; text-align: center; background-color: #0284c7; color: white; padding: 7px 10px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 0.85rem; margin-top: 1px;">
                📊 Ver Sheets ↗
            </a>
            """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

    tab_order, tab_history, tab_recipes = st.tabs([
        "➕ Nuevo Pedido de Fabricación",
        "📋 Historial de Pedidos de Fabricación",
        "📝 Fichas Técnicas & Editar RECETAS"
    ])

    recipes_catalog = recipe_service.get_recipes()
    model_names = sorted(list(recipes_catalog.keys()))
    available_fabrics = recipe_service.get_available_fabrics()

    # --- TAB 1: NUEVO PEDIDO DE FABRICACIÓN ---
    with tab_order:
        st.markdown("### 🛋️ Cargar Nuevo Pedido de Producción")
        st.caption("Selecciona el modelo de sillón, tipo de tela y cantidad. El sistema calculará la explosión de materiales y descontará automáticamente del stock semanal.")

        col_m1, col_m2, col_m3 = st.columns([5, 2, 4])
        with col_m1:
            selected_model = st.selectbox(
                "Modelo del Sillón:",
                model_names,
                index=0 if model_names else None,
                key="order_model_select",
                help="Elige el modelo del catálogo oficial de recetas."
            )
        with col_m2:
            order_qty = st.number_input(
                "Cantidad a Fabricar:",
                min_value=1,
                max_value=100,
                value=1,
                step=1,
                key="order_qty_input",
                help="Cantidad de unidades del mismo modelo a producir."
            )
        with col_m3:
            fabric_options = {f"{f['name']} (${f['unit_price']:,.0f}/m)": f["code"] for f in available_fabrics}
            sel_fab_label = st.selectbox(
                "Tipo de Tela (Tapizado):",
                list(fabric_options.keys()),
                key="order_fabric_select",
                help="Determina los metros requeridos de la receta. El color no influye en la receta ni en el cálculo de stock."
            )
            selected_fabric_code = fabric_options[sel_fab_label]

        order_note = st.text_input(
            "Cliente / Nota de Producción (Opcional):",
            placeholder="Ej: Pedido Gómez - Salón Principal",
            key="order_client_note"
        )

        st.caption("💡 *Nota: Como se especificó en el taller, el tipo de tela determina los metros y costo del modelo. El color no influye en la receta ni en el cálculo de stock.*")

        st.divider()

        # Cálculo de Requerimientos y Previsualización Inteligente
        if selected_model:
            req_data = recipe_service.calculate_order_requirements(
                model_name=selected_model,
                quantity=order_qty,
                fabric_code=selected_fabric_code
            )
            preview = recipe_service.preview_order_stock(
                requirements=req_data["items"],
                current_inventory=items
            )

            # Tarjetas de Métricas Resumen
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            with col_k1:
                st.metric("🛋️ Pedido", f"{order_qty}x {selected_model}")
            with col_k2:
                st.metric("🧵 Tela Requerida", f"{req_data['meters_fabric']:g} metros")
            with col_k3:
                st.metric("📦 Insumos Distintos", f"{preview['total_items']} materiales")
            with col_k4:
                st.metric("💰 Costo Materiales", f"${preview['total_cost']:,.2f}")

            st.write("")

            # Semáforo de Disponibilidad de Fábrica
            if preview["can_produce"]:
                st.markdown("""
                <div style="background: #f0fdf4; border: 1.5px solid #22c55e; border-radius: 10px; padding: 10px 16px; margin: 8px 0; color: #166534; font-weight: 700;">
                    🟢 <b>Stock Disponible:</b> Hay insumos suficientes en fábrica para fabricar este pedido completo.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #fef2f2; border: 1.5px solid #ef4444; border-radius: 10px; padding: 10px 16px; margin: 8px 0; color: #991b1b; font-weight: 700;">
                    ⚠️ <b>Faltante de Insumos:</b> Hay {preview['missing_count']} material(es) que no alcanzan en el stock actual para fabricar las {order_qty} unidad(es). Puedes confirmar si vas a reponerlos o ingresar la compra en breve.
                </div>
                """, unsafe_allow_html=True)

            # Tabla de Previsualización Inteligente
            st.markdown("#### 🔍 **Previsualización Inteligente de Insumos:**")
            
            df_preview = pd.DataFrame(preview["rows"])
            if not df_preview.empty:
                display_cols = ["Código", "Insumo", "Requerido", "Unidad", "Stock Actual", "Quedará", "Estado", "Precio Unit.", "Subtotal"]
                st.dataframe(
                    df_preview[display_cols],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Código": st.column_config.TextColumn("Código", width="small"),
                        "Insumo": st.column_config.TextColumn("Insumo / Material", width="large"),
                        "Requerido": st.column_config.NumberColumn("Requerido", format="%.2f"),
                        "Unidad": st.column_config.TextColumn("Unidad", width="small"),
                        "Stock Actual": st.column_config.NumberColumn("Stock Fábrica", format="%.2f"),
                        "Quedará": st.column_config.NumberColumn("Quedará", format="%.2f"),
                        "Estado": st.column_config.TextColumn("Estado Stock", width="medium"),
                        "Precio Unit.": st.column_config.NumberColumn("Precio Ref.", format="$ %.2f"),
                        "Subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.2f"),
                    }
                )

            st.write("")
            col_b1, col_b2 = st.columns([3, 7])
            with col_b1:
                # Botón estrictamente con la leyenda pedida: "Confirmar pedido"
                btn_confirm = st.button("Confirmar pedido", type="primary", use_container_width=True, key="btn_confirm_prod_order")
            with col_b2:
                st.caption(f"Al hacer clic, los insumos se descontarán automáticamente del conteo de stock en la pestaña **{st.session_state.active_tab}** de Google Sheets.")

            if btn_confirm:
                with st.spinner("Descontando insumos y sincronizando con Google Sheets..."):
                    success, msg, count = recipe_service.confirm_and_deduct_order(
                        model_name=selected_model,
                        quantity=order_qty,
                        fabric_code=selected_fabric_code,
                        current_inventory=items,
                        tab_name=st.session_state.active_tab,
                        stock_service_instance=stock_service_instance,
                        client_note=order_note
                    )
                if success:
                    st.session_state.show_success_msg = f"🎉 ¡Pedido confirmado con éxito! Se descontaron **{count}** insumos para fabricar **{order_qty}x {selected_model}** en la pestaña **{st.session_state.active_tab}**."
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"Error al confirmar pedido: {msg}")

    # --- TAB 2: HISTORIAL DE PEDIDOS CONFIRMADOS ---
    with tab_history:
        st.markdown("### 📋 Historial de Pedidos de Fabricación Confirmados")
        st.caption("Registro de todos los pedidos confirmados desde esta PC y descontados del inventario.")

        orders_hist = recipe_service.get_orders_history()
        if orders_hist:
            df_hist_rows = []
            for o in orders_hist:
                df_hist_rows.append({
                    "Fecha y Hora": o.get("date_str", "N/A"),
                    "Modelo": o.get("model_name", "N/A"),
                    "Cantidad": o.get("quantity", 1),
                    "Tela": o.get("fabric_code", "N/A"),
                    "Insumos Descontados": f"{o.get('deducted_items_count', 0)} insumos",
                    "Costo Materiales": float(o.get("total_cost", 0.0)),
                    "Pestaña Stock": o.get("tab_name", "N/A"),
                    "Cliente / Nota": o.get("client_note", ""),
                })
            
            st.dataframe(
                pd.DataFrame(df_hist_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Costo Materiales": st.column_config.NumberColumn("Costo Materiales", format="$ %.2f")
                }
            )

            with st.expander("🔍 Ver detalle de insumos descontados por pedido", expanded=False):
                for idx, o in enumerate(orders_hist[:10]):
                    st.markdown(f"**#{idx+1} - {o.get('date_str')}: {o.get('quantity')}x {o.get('model_name')}** ({o.get('fabric_code')})")
                    if o.get("details"):
                        st.write(" • " + " • ".join(o["details"][:15]))
                    st.divider()
        else:
            st.info("Aún no se han confirmado pedidos de fabricación en esta PC.")

    # --- TAB 3: FICHAS TÉCNICAS & EDITAR HOJA RECETAS ---
    with tab_recipes:
        st.markdown("### 📝 Fichas Técnicas de Sillones & Modificar Hoja RECETAS")
        st.caption("Permite consultar o editar las cantidades de insumos y precios unitarios de cada modelo de sillón, o abrir directamente la planilla.")

        col_r_btn1, col_r_btn2 = st.columns([3, 2])
        with col_r_btn1:
            st.markdown(f"""
            <a href="{RECETAS_SHEET_URL}" target="_blank" style="display: block; text-align: center; background-color: #0284c7; color: white; padding: 10px 14px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.95rem; margin-bottom: 12px;">
                📊 Abrir Hoja 'RECETAS' en Google Sheets ↗
            </a>
            """, unsafe_allow_html=True)
        with col_r_btn2:
            if st.button("🔄 Recargar Fichas desde Sheets", use_container_width=True, key="btn_refresh_recetas_data"):
                recipe_service.get_recipes(force_refresh=True)
                st.toast("Fichas técnicas actualizadas desde Google Sheets", icon="🔄")
                st.rerun()

        st.divider()

        inspect_model = st.selectbox(
            "Seleccionar modelo para ver o editar su receta:",
            model_names,
            key="inspect_recipe_model_sel"
        )

        if inspect_model and inspect_model in recipes_catalog:
            m_data = recipes_catalog[inspect_model]
            meters = m_data.get("meters_required", 0.0)
            items_list = m_data.get("items", [])

            col_sub1, col_sub2 = st.columns(2)
            with col_sub1:
                st.markdown(f"**Metros de Tela Requeridos por Sillón:** `{meters:g} metros`")
            with col_sub2:
                base_cost = sum(it.get("subtotal", 0.0) for it in items_list)
                st.markdown(f"**Costo Base Insumos (sin tela):** `${base_cost:,.2f}`")

            st.write("")
            st.markdown("**Lista de Materiales Base (BOM):**")
            
            recipe_table_rows = []
            for it in items_list:
                recipe_table_rows.append({
                    "Código": it["code"],
                    "Descripción": it["description"],
                    "Cantidad Requerida": float(it["qty"]),
                    "Unidad": it["unit"],
                    "Precio Unitario": float(it.get("unit_price", 0.0)),
                    "Subtotal": float(it.get("subtotal", 0.0)),
                    "_row_index": it.get("row_index", 0)
                })

            df_edit_recipe = pd.DataFrame(recipe_table_rows)

            edited_recipe_df = st.data_editor(
                df_edit_recipe,
                use_container_width=True,
                height=320,
                disabled=["Código", "Descripción", "Unidad", "Subtotal"],
                column_config={
                    "Código": st.column_config.TextColumn("Código Insumo", width="small"),
                    "Descripción": st.column_config.TextColumn("Material", width="large"),
                    "Cantidad Requerida": st.column_config.NumberColumn("Cantidad", min_value=0.0, format="%.2f"),
                    "Unidad": st.column_config.TextColumn("Unidad", width="small"),
                    "Precio Unitario": st.column_config.NumberColumn("Precio Unitario ($)", min_value=0.0, format="$ %.2f"),
                    "Subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.2f"),
                },
                hide_index=True,
                key=f"data_editor_recipe_{inspect_model}"
            )

            if st.button("💾 Guardar Cambios en Hoja RECETAS", type="primary", key=f"btn_save_recipe_{inspect_model}"):
                updated_items_payload = []
                for _, row in edited_recipe_df.iterrows():
                    updated_items_payload.append({
                        "row_index": row["_row_index"],
                        "qty": float(row["Cantidad Requerida"]),
                        "unit_price": float(row["Precio Unitario"])
                    })

                with st.spinner("Guardando en la pestaña RECETAS de Google Sheets..."):
                    ok_up, msg_up = recipe_service.update_recipe_items(inspect_model, updated_items_payload)
                if ok_up:
                    st.success(f"¡{msg_up}!")
                    st.rerun()
                else:
                    st.error(f"Error: {msg_up}")


# Si estamos en la PC y se seleccionó el módulo de fabricación, renderizar y detener ejecución del escáner
if is_pc_app and app_module == "🏭 Pedidos de Fabricación & Recetas":
    render_manufacturing_module(items, available_tabs, service)
    st.stop()


# --- 1. ENCABEZADO COMPACTO DE LA APP ---
st.markdown(f"""
<div class="sheets-header">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: center; gap: 14px;">
            <img src="data:image/png;base64,{bm_icon_b64}" width="42" height="42" style="border-radius: 9px; vertical-align: middle; box-shadow: 0 2px 6px rgba(0,0,0,0.35); border: 1.5px solid rgba(255,255,255,0.35);">
            <div>
                <h1 class="sheet-title">Control de Stock BM</h1>
                <p class="sheet-subtitle">Buena Madera • Pestaña activa: <b>{st.session_state.active_tab}</b></p>
            </div>
        </div>
        <div>
            <span class="scanner-live-badge"><span class="scanner-live-dot"></span>⚡ Enlace PC ⇄ Celular Activo</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- 1.1 BARRA DE CONTROL DE PESTAÑA SEMANAL & GOOGLE SHEETS (ARRIBA DE TODO) ---
col_tab_top1, col_tab_top2 = st.columns([6, 4])
with col_tab_top1:
    tab_idx = available_tabs.index(st.session_state.active_tab) if st.session_state.active_tab in available_tabs else 0
    sel_tab = st.selectbox(
        "📅 Pestaña Activa en Google Sheets (Conteo semanal):",
        available_tabs,
        index=tab_idx,
        key="top_tab_selector",
        help="Los escaneos y cargas de stock se registran en la tabla de la izquierda de esta pestaña."
    )
    if sel_tab != st.session_state.active_tab:
        st.session_state.active_tab = sel_tab
        st.rerun()

with col_tab_top2:
    st.write("")
    st.write("")
    col_t_btn1, col_t_btn2 = st.columns(2)
    with col_t_btn1:
        if st.button("🔄 Refrescar", use_container_width=True, key="top_refresh_btn"):
            items = service.get_inventory(tab_name=st.session_state.active_tab, force_refresh=True)
            available_tabs = service.get_available_tabs(force_refresh=True)
            st.toast("Planilla sincronizada con Google Sheets", icon="🔄")
            st.rerun()
    with col_t_btn2:
        st.markdown("""
        <a href="https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit" target="_blank" style="display: block; text-align: center; background-color: #0284c7; color: white; padding: 7px 10px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 0.85rem; margin-top: 1px;">
            📊 Abrir Sheets ↗
        </a>
        """, unsafe_allow_html=True)


pwa_js_template = """
    <script>
    (function() {
        const pDoc = window.parent.document;
        const pWin = window.parent;
        const hostname = window.location.hostname || 'localhost';

        // Inyectar soporte PWA / App Standalone para Celulares con Logo Oficial de Buena Madera
        try {
            const head = pDoc.head;
            const bmIconUrl = "data:image/png;base64,%%BM_ICON_B64%%";

            if (head) {
                if (!pDoc.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
                    const m1 = pDoc.createElement('meta'); m1.name = 'apple-mobile-web-app-capable'; m1.content = 'yes'; head.appendChild(m1);
                    const m2 = pDoc.createElement('meta'); m2.name = 'mobile-web-app-capable'; m2.content = 'yes'; head.appendChild(m2);
                    const m3 = pDoc.createElement('meta'); m3.name = 'apple-mobile-web-app-title'; m3.content = 'Control Stock BM'; head.appendChild(m3);
                    const m4 = pDoc.createElement('meta'); m4.name = 'theme-color'; m4.content = '#1e3a5f'; head.appendChild(m4);
                }

                // Icono para iPhone / Safari ("Agregar a inicio")
                let appleIcon = pDoc.querySelector('link[rel="apple-touch-icon"]');
                if (!appleIcon) {
                    appleIcon = pDoc.createElement('link');
                    appleIcon.rel = 'apple-touch-icon';
                    head.appendChild(appleIcon);
                }
                appleIcon.href = bmIconUrl;

                // Icono para Android / Chrome (Favicon y Manifest)
                let fav = pDoc.querySelector('link[rel*="icon"]');
                if (fav) { fav.href = bmIconUrl; }

                if (!pDoc.querySelector('link[rel="manifest"]')) {
                    const manifestObj = {
                        name: "Control de Stock BM",
                        short_name: "Stock BM",
                        start_url: window.location.href,
                        display: "standalone",
                        background_color: "#ffffff",
                        theme_color: "#1e3a5f",
                        icons: [
                            { src: bmIconUrl, sizes: "192x192", type: "image/png", purpose: "any maskable" },
                            { src: bmIconUrl, sizes: "512x512", type: "image/png", purpose: "any maskable" }
                        ]
                    };
                    const blob = new Blob([JSON.stringify(manifestObj)], { type: "application/json" });
                    const mLink = pDoc.createElement('link');
                    mLink.rel = 'manifest';
                    mLink.href = URL.createObjectURL(blob);
                    head.appendChild(mLink);
                }
            }
        } catch(e) {}

        function getScannerInput() {
            return pDoc.querySelector('input[placeholder*="Apunta"]')
                || pDoc.querySelector('input[aria-label*="NICTOM"]')
                || pDoc.querySelector('div[data-testid="stTextInput"] input')
                || pDoc.querySelector('input[type="text"]');
        }

        function focusScannerInput() {
            if (/Mobi|Android|iPhone/i.test(navigator.userAgent)) return;
            const active = pDoc.activeElement;
            if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return;
            const input = getScannerInput();
            if (input && active !== input) {
                input.focus();
            }
        }

        setTimeout(focusScannerInput, 200);
        setInterval(focusScannerInput, 1500);

        function triggerInputReact(input, val) {
            if (!input) return;
            try {
                const valueSetter = Object.getOwnPropertyDescriptor(input, 'value')?.set;
                const proto = Object.getPrototypeOf(input);
                const protoSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (protoSetter && valueSetter !== protoSetter) {
                    protoSetter.call(input, val);
                } else if (valueSetter) {
                    valueSetter.call(input, val);
                } else {
                    input.value = val;
                }
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            } catch(e) {}
        }

        if (!pWin.__nictom_attached) {
            pWin.__nictom_attached = true;
            let buffer = "";
            let lastKeyTime = Date.now();

            pWin.addEventListener('keydown', function(e) {
                const now = Date.now();
                if (now - lastKeyTime > 300) {
                    buffer = "";
                }
                lastKeyTime = now;

                if (e.key === 'Enter') {
                    if (buffer.length >= 2) {
                        const code = buffer.trim();
                        buffer = "";
                        
                        // 1. Inyectar en el input si existe en pantalla
                        const input = getScannerInput();
                        if (input) {
                            triggerInputReact(input, code);
                        }
                        
                        // 2. Enviar a la API de sincronización en puerto 8000
                        try {
                            fetch('http://' + hostname + ':8000/api/sync_scan', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ barcode: code, source: 'Lector NICTOM (PC)' })
                            });
                        } catch(err) {}
                    }
                    buffer = "";
                    return;
                }

                if (e.key && e.key.length === 1) {
                    buffer += e.key;
                }
            }, true);
        }

        if (!pWin.__sse_sync_attached) {
            pWin.__sse_sync_attached = true;
            try {
                const sse = new EventSource('https://ntfy.sh/bm_stock_sync_buenamadera_76f1483e/sse');
                sse.onmessage = function(ev) {
                    try {
                        const parsed = JSON.parse(ev.data);
                        if (parsed && parsed.event === 'message' && parsed.message) {
                            const msg = typeof parsed.message === 'string' ? JSON.parse(parsed.message) : parsed.message;
                            if (msg && msg.action === 'SCAN' && msg.barcode) {
                                const input = getScannerInput();
                                if (input && input.value !== msg.barcode) {
                                    triggerInputReact(input, msg.barcode);
                                }
                            }
                        }
                    } catch(e) {}
                };
            } catch(e) {}
        }
    })();
    </script>
    """
pwa_js = pwa_js_template.replace("%%BM_ICON_B64%%", bm_icon_b64)
components.html(pwa_js, height=0)

def reset_scanner(keep_msg: bool = False):
    st.session_state.active_barcode = ""
    if not keep_msg:
        st.session_state.show_success_msg = None
    if st.session_state.get("sync_mode") == "MIRROR":
        new_ver = sync_service.broadcast_clear()
        st.session_state.sync_version = new_ver

def handle_scan_submit():
    val = st.session_state.get("scanner_input_box", "").strip()
    if val:
        clean_code = val.replace('"', '-').replace("'", '-').replace('/', '-').replace('_', '-').replace('?', '-')
        st.session_state.active_barcode = clean_code
        st.session_state.show_success_msg = None
        if st.session_state.get("sync_mode") == "MIRROR":
            new_ver = sync_service.broadcast_scan(clean_code, source="Lector NICTOM / Teclado")
            st.session_state.sync_version = new_ver
        st.session_state.scanner_input_box = ""

def on_dropdown_select():
    val = st.session_state.get("selector_dropdown", "")
    if val and val != "-- Seleccionar material de la lista --":
        chosen = item_map[val]
        st.session_state.active_barcode = chosen
        st.session_state.show_success_msg = None
        if st.session_state.get("sync_mode") == "MIRROR":
            new_ver = sync_service.broadcast_scan(chosen, source="Selector de Lista")
            st.session_state.sync_version = new_ver

def render_phone_linking_card(key_suffix: str = "main", expanded: bool = True):
    """
    Componente para vincular la aplicación de celular con la app de escritorio mediante código QR.
    Ofrece Modo Espejo en tiempo real (PC ⇄ Celular - Recomendado para escaneo) y Modo Nube para consulta remota.
    """
    with st.expander("📱 **Vincular Celular a la App de Escritorio (Escanear Código QR)**", expanded=expanded):
        tab_sync, tab_cloud = st.tabs([
            "⚡ Modo Espejo en Vivo (PC ⇄ Celular - Recomendado)",
            "🌐 App Celular en la Nube (Para usar sin la PC)"
        ])

        with tab_sync:
            col_s_qr, col_s_info = st.columns([1, 2])
            active_tunnel = TunnelService.get_saved_url()
            base_live = active_tunnel or f"http://{local_ip}:8501"
            live_mirror_url = base_live + ("&app=mobile" if "?" in base_live else "/?app=mobile")
            qr_live_b64 = generate_qr_base64(live_mirror_url, box_size=7)
            with col_s_qr:
                if qr_live_b64:
                    st.markdown(f'''
                    <div style="text-align: center; padding: 10px; background: white; border-radius: 12px; border: 2px solid #16a34a; box-shadow: 0 4px 12px rgba(22, 163, 74, 0.15); display: inline-block;">
                        <img src="data:image/png;base64,{qr_live_b64}" width="165" style="display: block; margin: 0 auto; border-radius: 8px;"><br>
                        <span style="font-size: 0.8rem; font-weight: 700; color: #166534;">⚡ Escanear para Modo Espejo</span>
                    </div>
                    ''', unsafe_allow_html=True)
                else:
                    st.info(f"👉 Enlace en vivo: {live_mirror_url}")

            with col_s_info:
                st.markdown(f"""
                #### ⚡ **Modo Espejo en Tiempo Real (PC ⇄ Celular):**
                Al escanear este código QR con tu celular, se conecta **directamente a este programa en la computadora**:
                1. **Disparas con el lector NICTOM en la PC.**
                2. **El producto aparece al instante en la pantalla de tu celular** en tiempo real.
                3. Puedes ingresar conteos físicos, compras, stock mínimo o notas desde el celular y guardar directamente en Google Sheets.
                
                👉 Enlace de conexión directa: **[{live_mirror_url}]({live_mirror_url})**
                
                ✨ **100% Estable:** No depende de servidores en la nube externos ni se va a dormir. Mientras este programa esté abierto en la PC, la conexión es continua, privada e instantánea.
                """)
                if active_tunnel:
                    st.caption("🌐 Conectado mediante túnel activo de Cloudflare.")
                else:
                    st.caption(f"📶 Requiere que tu celular esté conectado al mismo Wi-Fi del taller (`{local_ip}`).")

        with tab_cloud:
            col_c_qr, col_c_info = st.columns([1, 2])
            mobile_cloud_url = f"{CLOUD_APP_URL}/?app=mobile"
            qr_cloud_b64 = generate_qr_base64(mobile_cloud_url, box_size=7)
            with col_c_qr:
                if qr_cloud_b64:
                    st.markdown(f'''
                    <div style="text-align: center; padding: 10px; background: white; border-radius: 12px; border: 2px solid #0284c7; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.15); display: inline-block;">
                        <img src="data:image/png;base64,{qr_cloud_b64}" width="165" style="display: block; margin: 0 auto; border-radius: 8px;"><br>
                        <span style="font-size: 0.8rem; font-weight: 700; color: #0369a1;">🌐 Escanear para App Celular</span>
                    </div>
                    ''', unsafe_allow_html=True)
            with col_c_info:
                st.markdown(f"""
                #### 🌐 **App en la Nube (Para cuando la PC esté apagada):**
                Esta versión funciona permanentemente en internet para consultar stock cuando no estás en el taller:
                - Podés consultar stock, buscar insumos y cargar compras o recuentos desde cualquier lugar con 4G o Wi-Fi.
                - Todos los cambios se guardan directamente en la misma planilla de Google Sheets.
                
                👉 Enlace permanente: **[{CLOUD_APP_URL}]({mobile_cloud_url})**
                
                ℹ️ **¿Por qué Streamlit dice 'This app has gone to sleep'?**
                Streamlit Cloud es un servicio gratuito que suspende automáticamente servidores inactivos tras varios días sin uso:
                - **No tienes que usarla todos los días.**
                - Si al entrar ves ese cartel, simplemente haz clic en el botón azul **'Yes, get this app back up!'** y en 1 minuto estará funcionando.
                
                💡 **Para guardarla en tu celular:** Abre el enlace en Safari o Chrome, toca el botón de compartir o los 3 puntitos y elige **"Agregar a la pantalla de inicio"**.
                """)

# Mensaje de confirmación cuando se acaba de guardar un stock o crear pestaña
if st.session_state.get("show_success_msg"):
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #dcfce7, #bbf7d0); border: 2px solid #22c55e; border-radius: 12px; padding: 14px 18px; margin: 10px 0 16px 0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
            <div style="font-size: 1.05rem; font-weight: 700; color: #15803d;">
                {st.session_state.show_success_msg}
            </div>
            <a href="https://docs.google.com/spreadsheets/d/10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4/edit" target="_blank" style="background-color: #15803d; color: white; padding: 7px 12px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 0.85rem;">
                📊 Ver en Google Sheets ↗
            </a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================================================
# --- 2. CONTROL DE ESCANEO RÁPIDO & RESULTADO (ARRIBA DE TODO, JUSTO ABAJO DE ABRIR SHEETS) ---
# =========================================================================================
st.markdown("""
<div style="margin: 4px 0 10px 0; display: flex; align-items: center; justify-content: flex-start;">
    <span class="scanner-live-badge"><span class="scanner-live-dot"></span> Lector Listo</span>
</div>
""", unsafe_allow_html=True)

# --- A. FICHA DEL PRODUCTO ESCANEADO (ARRIBA DE TODO, JUSTO ABAJO DE ABRIR SHEETS) ---
current_code = (st.session_state.get("active_barcode") or "").strip()

if current_code:
    # SI HAY UN PRODUCTO ESCANEADO/SELECCIONADO: MOSTRAR FICHA Y FORMULARIO INMEDIATAMENTE
    product = service.find_by_barcode(current_code, items=items)

    if product:
        st.markdown('<div class="product-hero-card">', unsafe_allow_html=True)
        
        # --- DESCRIPCIÓN DEL PRODUCTO ---
        col_desc1, col_desc2 = st.columns([7, 3])
        with col_desc1:
            st.markdown(f'<h2 class="product-hero-title">🛋️ {product.description.upper()}</h2>', unsafe_allow_html=True)
            st.markdown(f"**Código de Insumo:** `{product.barcode}` • **Categoría:** `{product.category}` • **Unidad:** `{product.unit}`")
            if product.cant_x_caja and product.cant_x_caja != "N/A":
                st.caption(f"📦 **Presentación / Cant. por caja:** {product.cant_x_caja}")

        with col_desc2:
            estado_badge = '<span class="badge-critical">⚠️ REPOSICIÓN URGENTE</span>' if product.is_critical else '<span class="badge-ok">✅ STOCK EN REGLA</span>'
            st.markdown(f'<div style="text-align: right; margin-top: 4px;">{estado_badge}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="text-align: right; font-size: 1.25rem; font-weight: 800; color: #0284c7; margin-top: 6px;">Total actual: {product.current_stock:g} {product.unit}</div>', unsafe_allow_html=True)

        st.divider()

        # --- FORMULARIO DE CARGA MANUAL (CAMPOS EXACTOS DE GOOGLE SHEETS) ---
        st.markdown("### 📝 Carga Manual de Insumo (Columnas de Google Sheets):")
        st.caption(f"Editando valores para la pestaña activa: **`{st.session_state.active_tab}`**")

        with st.form(key=f"form_full_sheets_{product.barcode}"):
            # Fila 1: Cant. Inventario (G) y Compra Semana (H)
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                input_cant_inv = st.number_input(
                    "📦 Cant. Inventario [Col. G] (Conteo físico en fábrica/pañol):",
                    min_value=0.0,
                    value=float(product.cant_inventario),
                    step=1.0,
                    format="%.2f",
                    help="Cantidad real física que tienes contada o pesada.",
                )
            with col_f2:
                input_compra_sem = st.number_input(
                    "📥 Compra Semana [Col. H] (Ingresos recibidos esta semana):",
                    min_value=0.0,
                    value=float(product.compra_semana),
                    step=1.0,
                    format="%.2f",
                    help="Cantidad comprada o ingresada que se suma al inventario.",
                )

            # Fila 2: Stock Mínimo (O) y $ x Unidad (Q)
            col_f3, col_f4 = st.columns(2)
            with col_f3:
                input_min_stock = st.number_input(
                    "⚠️ Stock Mínimo [Col. O] (Nivel de alerta para reposición):",
                    min_value=0.0,
                    value=float(product.min_stock),
                    step=1.0,
                    format="%.2f",
                    help="Si el TOTAL INVENTARIO es menor o igual a este valor, se dispara la alerta a Telegram.",
                )
            with col_f4:
                input_unit_price = st.number_input(
                    "💲 $ x Unidad [Col. Q] (Precio Unitario):",
                    min_value=0.0,
                    value=float(product.unit_price),
                    step=10.0,
                    format="%.2f",
                    help="Precio por unidad o kg para calcular el subtotal valuado.",
                )

            # Fila 3: Observaciones (S)
            input_notes = st.text_input(
                "📝 Observaciones [Col. S] (Notas, lote, balde o responsable):",
                value=product.notes or "",
                placeholder="Ej: Balde pesado 205grs, Lote 4, etc.",
            )

            # Cálculo en tiempo real de lo que impactará en Google Sheets
            calc_total = input_cant_inv + input_compra_sem
            calc_subtotal = calc_total * input_unit_price
            calc_comprar = max(0.0, input_min_stock - calc_total)

            st.markdown(f"""
            <div class="calc-preview-bar">
                📊 <b>TOTAL INVENTARIO [Col. I]:</b> {calc_total:g} {product.unit} &nbsp;|&nbsp; 
                💰 <b>SubTotal [Col. R]:</b> ${calc_subtotal:,.2f} &nbsp;|&nbsp; 
                🛒 <b>A Comprar [Col. P]:</b> {calc_comprar:g} {product.unit}
            </div>
            """, unsafe_allow_html=True)

            col_btn_save, col_btn_close = st.columns([5, 2])
            with col_btn_save:
                btn_guardar = st.form_submit_button("💾 GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True)
            with col_btn_close:
                btn_cerrar = st.form_submit_button("✖️ Limpiar Ficha", use_container_width=True)

            if btn_cerrar:
                reset_scanner()
                st.rerun()

            if btn_guardar:
                try:
                    resultado = service.update_product_sheets_fields(
                        barcode=product.barcode,
                        cant_inventario=input_cant_inv,
                        compra_semana=input_compra_sem,
                        min_stock=input_min_stock,
                        unit_price=input_unit_price,
                        notes=input_notes,
                        tab_name=st.session_state.active_tab,
                        description=product.description,
                    )
                    st.session_state.show_success_msg = f"🎉 ¡Guardado con éxito en Google Sheets! Se actualizó **{product.description}** a **{resultado['new_stock']:g} {product.unit}** en la pestaña **{st.session_state.active_tab}** (Conteo físico en tabla izquierda: **{input_cant_inv:g} {product.unit}**)."
                    st.session_state.scan_history.insert(0, {
                        "Hora": datetime.now().strftime("%H:%M:%S"),
                        "Pestaña": st.session_state.active_tab,
                        "Código": product.barcode,
                        "Producto": product.description,
                        "Cant. Inv": input_cant_inv,
                        "Compra Sem": input_compra_sem,
                        "Total": resultado['new_stock'],
                        "Stock Min": input_min_stock,
                    })
                    new_ver = sync_service.broadcast_saved(
                        barcode=product.barcode,
                        product_name=product.description,
                        new_stock=resultado['new_stock'],
                        tab_name=st.session_state.active_tab,
                        source="Celular / PC",
                    )
                    st.session_state.sync_version = new_ver
                    st.toast("✅ Guardado en Google Sheets", icon="💾")
                    reset_scanner(keep_msg=True)
                    st.rerun()
                except Exception as err:
                    st.error(f"Error guardando en Google Sheets: {err}")

        st.markdown('</div>', unsafe_allow_html=True)

    else:
        # CÓDIGO NO VINCULADO -> PERMITIR ASOCIARLO A UN INSUMO
        st.warning(f"🔍 Se leyó el código: **`{current_code}`**, pero no existe directamente en la planilla.")
        st.info("💡 Si este código viene impreso en la caja o balde del proveedor, puedes **vincularlo a un insumo** para que el lector lo reconozca automáticamente siempre:")
        
        with st.container():
            col_v1, col_v2 = st.columns([4, 2])
            with col_v1:
                target_choice = st.selectbox(
                    "¿A qué producto de la fábrica pertenece este código de barras?",
                    list(item_map.keys()),
                    key="link_selector_box_auto"
                )
            with col_v2:
                st.write("")
                st.write("")
                col_v_b1, col_v_b2 = st.columns([3, 2])
                with col_v_b1:
                    if st.button("🔗 Vincular Código", type="primary", use_container_width=True):
                        chosen_barcode = item_map[target_choice]
                        service.link_barcode(current_code, chosen_barcode)
                        st.success(f"¡Código `{current_code}` vinculado exitosamente a `{chosen_barcode}`!")
                        st.session_state.active_barcode = chosen_barcode
                        new_ver = sync_service.broadcast_scan(chosen_barcode, source="Vinculación")
                        st.session_state.sync_version = new_ver
                        st.rerun()
                with col_v_b2:
                    if st.button("Cerrar ✖️", use_container_width=True, key="btn_cancel_link"):
                        reset_scanner()
                        st.rerun()

# --- B. CONTROLES DEL ESCÁNER Y SELECTORES ---
col_in1, col_in2, col_in3 = st.columns([6, 2, 2])
with col_in1:
    st.text_input(
        "Entrada del Lector NICTOM (Apunta y dispara):",
        key="scanner_input_box",
        placeholder="Apunta con el lector o escribe (ej: POL/02CM/001, INS-GRA-8411) y presiona Enter...",
        on_change=handle_scan_submit,
        label_visibility="collapsed",
    )
with col_in2:
    if st.button("Buscar 🔍", use_container_width=True, on_click=handle_scan_submit):
        st.rerun()
with col_in3:
    if st.button("✖️ Limpiar", use_container_width=True, help="Limpia la pantalla para escanear de cero"):
        reset_scanner()
        st.rerun()

# Menú desplegable alternativo y botones rápidos
col_opt1, col_opt2 = st.columns([5, 5])
with col_opt1:
    st.selectbox(
        "O buscar directamente por nombre en el catálogo:",
        ["-- Seleccionar material de la lista --"] + list(item_map.keys()),
        key="selector_dropdown",
        on_change=on_dropdown_select,
        label_visibility="collapsed",
    )
with col_opt2:
    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        if st.button("Poliester 2cm", use_container_width=True, key="quick_pol"):
            st.session_state.active_barcode = "POL-02CM-001"
            st.session_state.show_success_msg = None
            if st.session_state.get("sync_mode") == "MIRROR":
                new_ver = sync_service.broadcast_scan("POL-02CM-001", source="Botón Rápido")
                st.session_state.sync_version = new_ver
            st.rerun()
    with col_t2:
        if st.button("Grampas", use_container_width=True, key="quick_gra"):
            st.session_state.active_barcode = "INS-GRA-8411"
            st.session_state.show_success_msg = None
            if st.session_state.get("sync_mode") == "MIRROR":
                new_ver = sync_service.broadcast_scan("INS-GRA-8411", source="Botón Rápido")
                st.session_state.sync_version = new_ver
            st.rerun()
    with col_t3:
        if st.button("Tornillos", use_container_width=True, key="quick_tor"):
            st.session_state.active_barcode = "TOR-FIX-075"
            st.session_state.show_success_msg = None
            if st.session_state.get("sync_mode") == "MIRROR":
                new_ver = sync_service.broadcast_scan("TOR-FIX-075", source="Botón Rápido")
                st.session_state.sync_version = new_ver
            st.rerun()

if is_pc_app:
    render_phone_linking_card(key_suffix="main_panel", expanded=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
    st.divider()

    # =========================================================================================
    # --- 3. CONTROLES DE PESTAÑA SEMANAL & KPIS (DEBAJO DEL ESCÁNER) ---
    # =========================================================================================
    st.markdown("### 📊 Control Semanal & Métricas de Fábrica")

    col_tab1, col_tab2 = st.columns([5, 5])
    with col_tab1:
        tab_index = available_tabs.index(st.session_state.active_tab) if st.session_state.active_tab in available_tabs else 0
        selected_tab_choice = st.selectbox(
            "📅 Pestaña de Recuento Semanal Activa en Google Sheets:",
            available_tabs,
            index=tab_index,
            help="Selecciona en qué pestaña de la planilla de Google Sheets impactan los escaneos y recuentos.",
            key="weekly_tab_picker",
        )
        if selected_tab_choice != st.session_state.active_tab:
            st.session_state.active_tab = selected_tab_choice
            st.rerun()

    with col_tab2:
        st.write("")
        is_current = (st.session_state.active_tab == current_week_tab)
        badge_label = f"🟢 Pestaña Activa ({st.session_state.active_tab})" if is_current else f"📁 Histórico ({st.session_state.active_tab})"
        st.markdown(f'<div style="margin-top: 4px;"><span class="tab-badge">{badge_label}</span> <span style="font-size: 0.85rem; color: #64748b;">(Todo escaneo impacta en la tabla izquierda de esta pestaña)</span></div>', unsafe_allow_html=True)
        
        with st.expander("➕ **Abrir / Crear Nueva Pestaña Semanal en Google Sheets**", expanded=False):
            st.caption("Crea una nueva pestaña en Google Sheets duplicando la estructura base, con las fórmulas y catálogos pero con la tabla de la izquierda vacía para el nuevo recuento.")
            next_monday = datetime.now() + timedelta(days=(7 - datetime.now().weekday()) % 7 or 7)
            suggested_tab = f"STOCK_{next_monday.strftime('%d.%m.%y')}"
            col_nt1, col_nt2 = st.columns([3, 2])
            with col_nt1:
                new_tab_name_input = st.text_input("Nombre de la nueva pestaña:", value=suggested_tab, key="new_tab_input_name")
            with col_nt2:
                st.write("")
                st.write("")
                if st.button("🚀 Crear Pestaña", type="primary", use_container_width=True):
                    try:
                        created_title = service.create_new_weekly_tab(new_tab_name_input.strip())
                        st.session_state.active_tab = created_title
                        available_tabs = service.get_available_tabs(force_refresh=True)
                        st.success(f"¡Pestaña '{created_title}' creada con éxito en Google Sheets con la tabla izquierda vacía!")
                        st.rerun()
                    except Exception as e_new_tab:
                        st.error(f"Error creando pestaña en Google Sheets: {e_new_tab}")

    # KPIs de inventario
    try:
        kpis = service.get_kpis(items=items)
    except Exception:
        kpis = {"total_items": len(items), "critical_count": 0, "normal_count": len(items), "total_valuation": 0.0}

    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_sync = st.columns([2, 2, 2, 3, 3])
    with col_kpi1:
        st.metric("Total Insumos", kpis["total_items"])
    with col_kpi2:
        st.metric("⚠️ A Reponer", kpis["critical_count"], delta=-kpis["critical_count"] if kpis["critical_count"] > 0 else 0, delta_color="inverse")
    with col_kpi3:
        st.metric("✅ Stock Óptimo", kpis["normal_count"])
    with col_kpi4:
        st.metric("Valuación Total", f"${kpis['total_valuation']:,.2f}")
    with col_sync:
        st.write("")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("🔄 Refrescar", use_container_width=True):
                items = service.get_inventory(tab_name=st.session_state.active_tab, force_refresh=True)
                available_tabs = service.get_available_tabs(force_refresh=True)
                st.toast("Datos sincronizados con Google Sheets", icon="🔄")
                st.rerun()
        with col_s2:
            if st.button("📲 Telegram", use_container_width=True):
                res = service.trigger_batch_telegram_alerts(items=items)
                if res["sent"]:
                    st.toast("Alerta enviada a Telegram", icon="✅")
                else:
                    st.toast("Alerta simulada (ver .env)", icon="ℹ️")



# --- 4. HISTORIAL DE ESCANEOS RECIENTES ---
if st.session_state.scan_history:
    with st.expander(f"🕒 Historial de escaneos de hoy ({len(st.session_state.scan_history)})", expanded=False):
        st.dataframe(pd.DataFrame(st.session_state.scan_history), use_container_width=True, hide_index=True)

if is_pc_app:
    st.divider()

    # =========================================================================================
    # --- 5. PLANILLA GENERAL "STOCK BUENA MADERA" (ESTILO GOOGLE SHEETS) ---
    # =========================================================================================
    st.markdown(f"### 📋 Planilla General: {st.session_state.active_tab} (Estilo Google Sheets)")
    st.caption(f"Visualizando y editando la pestaña **{st.session_state.active_tab}** de Google Sheets.")

    col_t1, col_t2, col_t3 = st.columns([2, 3, 2])
    with col_t1:
        todas_cats = ["Todas"] + sorted(list(set(i.category for i in items)))
        filtro_cat = st.selectbox("Categoría:", todas_cats)
    with col_t2:
        filtro_busqueda = st.text_input("Filtrar planilla por texto:", placeholder="Buscar por código, madera, tela, tornillo...")
    with col_t3:
        st.write("")
        solo_criticos = st.checkbox("Solo insumos a reponer (Críticos)", value=False)

    display_items = [i for i in items]
    if filtro_cat != "Todas":
        display_items = [i for i in display_items if i.category.lower() == filtro_cat.lower()]
    if filtro_busqueda:
        q = filtro_busqueda.strip().lower()
        display_items = [
            i for i in display_items
            if q in i.barcode.lower() or q in i.description.lower() or (i.notes and q in i.notes.lower())
        ]
    if solo_criticos:
        display_items = [i for i in display_items if i.is_critical]

    df_rows = []
    for it in display_items:
        df_rows.append({
            "Alerta": "⚠️ Comprar" if it.is_critical else "✅ OK",
            "Codigo de Barras": it.barcode,
            "Descipción de Producto": it.description,
            "TOTAL INVENTARIO": float(it.current_stock),
            "Cant. Inventario": float(it.cant_inventario),
            "Compra Semana": float(it.compra_semana),
            "Cant x Caja": str(it.cant_x_caja or "N/A"),
            "Unidad": it.unit,
            "Stock Mínimo": float(it.min_stock),
            "$ x Unidad": float(it.unit_price),
            "$ SubTotal": float(it.subtotal),
            "Observaciones": str(it.notes or ""),
        })

    df_sheet = pd.DataFrame(df_rows)

    if not df_sheet.empty:
        edited_df = st.data_editor(
            df_sheet,
            use_container_width=True,
            height=450,
            disabled=["Alerta", "Codigo de Barras", "Descipción de Producto", "$ SubTotal", "Unidad"],
            column_config={
                "Alerta": st.column_config.TextColumn("Alerta", width="small"),
                "Codigo de Barras": st.column_config.TextColumn("Codigo de Barras", width="medium"),
                "Descipción de Producto": st.column_config.TextColumn("Descipción de Producto", width="large"),
                "TOTAL INVENTARIO": st.column_config.NumberColumn("TOTAL INVENTARIO", min_value=0.0, format="%.2f"),
                "Cant. Inventario": st.column_config.NumberColumn("Cant. Inventario", format="%.2f"),
                "Compra Semana": st.column_config.NumberColumn("Compra Semana", format="%.2f"),
                "Stock Mínimo": st.column_config.NumberColumn("Stock Mínimo", min_value=0.0, format="%.2f"),
                "$ x Unidad": st.column_config.NumberColumn("$ x Unidad", format="$ %.2f"),
                "$ SubTotal": st.column_config.NumberColumn("$ SubTotal", format="$ %.2f"),
                "Observaciones": st.column_config.TextColumn("Observaciones", width="large"),
            },
            hide_index=True,
            key="sheets_data_editor_main",
        )

        if st.button("💾 Guardar Cambios Directos de la Planilla", type="primary"):
            updated_count = 0
            for _, row in edited_df.iterrows():
                b_code = row["Codigo de Barras"]
                new_tot = float(row["TOTAL INVENTARIO"])
                new_cant_inv = float(row["Cant. Inventario"])
                new_compra_sem = float(row["Compra Semana"])
                new_min = float(row["Stock Mínimo"])
                new_price = float(row["$ x Unidad"])
                new_notes = str(row["Observaciones"]).strip() if row["Observaciones"] else None

                for it in items:
                    if it.barcode == b_code:
                        if (
                            it.current_stock != new_tot
                            or it.cant_inventario != new_cant_inv
                            or it.compra_semana != new_compra_sem
                            or it.min_stock != new_min
                            or it.unit_price != new_price
                            or (it.notes or "") != (new_notes or "")
                        ):
                            it.cant_inventario = new_cant_inv
                            it.compra_semana = new_compra_sem
                            it.current_stock = new_cant_inv + new_compra_sem if (new_cant_inv != it.cant_inventario or new_compra_sem != it.compra_semana) else new_tot
                            it.min_stock = new_min
                            it.unit_price = new_price
                            it.subtotal = it.current_stock * new_price
                            it.comprar = max(0.0, new_min - it.current_stock)
                            it.notes = new_notes
                            it.is_critical = it.current_stock <= new_min
                            updated_count += 1
                        break
            
            if updated_count > 0:
                service.save_bulk_from_editor(items, tab_name=st.session_state.active_tab)
                st.success(f"¡Se guardaron los cambios en {updated_count} productos en la pestaña '{st.session_state.active_tab}' exitosamente!")
                st.rerun()
            else:
                st.info("No se detectaron modificaciones pendientes de guardar.")
    else:
        st.info("No se encontraron materiales que coincidan con los filtros de búsqueda.")
