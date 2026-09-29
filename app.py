import threading
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
from PIL import Image

try:
    import zxingcpp
except ImportError:
    zxingcpp = None



from config import settings
from services.stock_service import StockService
from services.sync_service import sync_service, LiveSyncService
from services.tunnel_service import TunnelService
from models.schemas import StockItem
import base64

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
    initial_sidebar_state="collapsed",
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

# Sincronización en vivo entre PC y Celulares mediante fragmento nativo (1 segundo de intervalo)
@st.fragment(run_every=1.0)
def live_sync_watcher():
    shared_state = sync_service.get_state()
    server_version = shared_state.get("version", 0)
    if server_version > st.session_state.get("sync_version", 0):
        st.session_state.sync_version = server_version
        action = shared_state.get("action")
        src = shared_state.get("source", "Dispositivo")
        
        # En modo Espejo (por defecto), clonar escaneo de otro dispositivo inmediatamente
        if st.session_state.get("sync_mode", "MIRROR") == "MIRROR":
            if action == "SCAN":
                scanned_code = shared_state.get("barcode", "")
                if scanned_code and scanned_code != st.session_state.get("active_barcode"):
                    st.session_state.active_barcode = scanned_code
                    st.session_state.show_success_msg = None
                    st.rerun()
            elif action == "CLEAR":
                if st.session_state.get("active_barcode"):
                    st.session_state.active_barcode = ""
                    st.rerun()
            elif action == "SAVED":
                p_name = shared_state.get("product_name", "")
                n_stock = shared_state.get("new_stock", 0.0)
                if p_name:
                    st.session_state.show_success_msg = f"🎉 Stock de **{p_name}** actualizado a **{n_stock:g}** ({src}) en Google Sheets."
                st.session_state.active_barcode = ""
                st.rerun()

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

    if tunnel_url:
        st.markdown("**🌐 Acceso Remoto 4G / Cualquier Red:**")
        qr_tunnel_url = f"https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={tunnel_url}"
        st.markdown(f'<div style="text-align: center;"><img src="{qr_tunnel_url}" width="130" style="border-radius: 8px; border: 1px solid #cbd5e1;"><br><a href="{tunnel_url}" target="_blank" style="font-size: 0.82rem; font-weight: bold; color: #0284c7;">{tunnel_url}</a></div>', unsafe_allow_html=True)
        st.caption("✨ Escaneá este QR desde el celular con tus datos móviles (4G/5G).")

    st.markdown("**📶 Red Wi-Fi Local (Mismo Wi-Fi):**")
    local_url = f"http://{local_ip}:8501"
    st.caption(f"`{local_url}`")

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

def render_camera_scanner_component(key_suffix: str = "main"):
    """
    Renderiza el escáner de cámara nativo compatible con celulares Android / iOS.
    Usa la cámara del sistema para leer códigos de barra en alta definición sin bloqueos.
    """
    if "cam_counter" not in st.session_state:
        st.session_state.cam_counter = 0

    st.markdown("""
    <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 10px 14px; margin-bottom: 10px;">
        <p style="margin: 0 0 4px 0; font-size: 0.95rem; font-weight: 700; color: #166534;">
            📱 Modo Cámara de Celular / Tablet:
        </p>
        <p style="margin: 0; font-size: 0.88rem; color: #15803d; line-height: 1.4;">
            Toca el botón para abrir la cámara de tu teléfono. Al detectar el código, se cargará automáticamente y se limpiará para que puedas escanear el siguiente sin demoras.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    cam_key = f"file_cam_{key_suffix}_{st.session_state.cam_counter}"
    file_pic = st.file_uploader(
        "📸 SACAR FOTO CON LA CÁMARA DEL CELULAR:",
        type=["jpg", "jpeg", "png", "webp"],
        key=cam_key,
        help="Abre la cámara de tu teléfono con autofoco para leer el código de barras."
    )
    
    if file_pic:
        try:
            img = Image.open(file_pic)
            decoded = zxingcpp.read_barcode(img) if zxingcpp else None

            if decoded and decoded.text:
                detected_raw = decoded.text.strip()
                clean_code = detected_raw.replace('"', '-').replace("'", '-').replace('/', '-').replace('_', '-').replace('?', '-')
                st.session_state.active_barcode = clean_code
                st.session_state.show_success_msg = None
                # Se incrementa cam_counter para resetear el uploader y descartar la foto procesada de inmediato
                st.session_state.cam_counter += 1
                if st.session_state.get("sync_mode") == "MIRROR":
                    new_ver = sync_service.broadcast_scan(clean_code, source="Cámara Celular")
                    st.session_state.sync_version = new_ver
                st.toast(f"✅ ¡Código detectado: {detected_raw}!", icon="🎯")
                st.rerun()
            else:
                st.warning("🔍 No se detectó un código legible en la foto. Asegúrate de enfocar bien las barras y con buena iluminación.")
        except Exception as err:
            st.error(f"Error procesando imagen de la cámara: {err}")

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

with st.expander("📷 **Escanear con Cámara del Celular / Tablet**", expanded=False):
    render_camera_scanner_component(key_suffix="top_panel")

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

# Panel de Enlace en Vivo PC ⇄ Celular (Modo Dúo)
with st.expander("📱 **Modo Dúo: Enlazar Celular en Vivo con el Escáner de la PC (Ver QR / Link)**", expanded=False):
    col_qr1, col_qr2 = st.columns([2, 5])
    with col_qr1:
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=http://{local_ip}:8501"
        st.markdown(f'<img src="{qr_api_url}" alt="QR Celular" style="border-radius: 8px; border: 1px solid #cbd5e1; width: 140px; height: 140px;">', unsafe_allow_html=True)
    with col_qr2:
        st.markdown(f"""
        **¿Cómo usarlo en el celular?**
        1. Conecta tu celular a la misma red **Wi-Fi** que esta computadora.
        2. Abre la cámara del celular y escanea el código QR, o escribe en el navegador:
           👉 **`{mobile_url}`**
        3. **¡Listo!** Cuando dispares con el lector NICTOM en la PC, **el producto aparecerá arriba de todo en tu celular**. Podrás cargar el conteo físico, compras, stock mínimo o notas y guardarlo directamente en Google Sheets.
        """)

# --- 4. HISTORIAL DE ESCANEOS RECIENTES ---
if st.session_state.scan_history:
    with st.expander(f"🕒 Historial de escaneos de hoy ({len(st.session_state.scan_history)})", expanded=False):
        st.dataframe(pd.DataFrame(st.session_state.scan_history), use_container_width=True, hide_index=True)

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
