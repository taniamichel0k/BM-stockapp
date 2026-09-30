import sys
import json
import time
import socket
import threading
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).parent
    try:
        SYNC_FILE = exe_dir / "data" / "live_sync_state.json"
        SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        SYNC_FILE = Path(getattr(sys, '_MEIPASS', exe_dir)) / "data" / "live_sync_state.json"
        SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
else:
    SYNC_FILE = Path(__file__).parent.parent / "data" / "live_sync_state.json"

CLOUD_TOPIC = "bm_stock_sync_buenamadera_76f1483e"
CLOUD_URL = f"https://ntfy.sh/{CLOUD_TOPIC}"

class LiveSyncService:
    """
    Servicio de sincronización en tiempo real entre múltiples dispositivos
    (PC con lector de barras NICTOM y Celular del operario/supervisor).
    Utiliza versionado monótono por milisegundos reales (timestamp epoch ms) para evitar
    desincronizaciones y colisiones de estado tras limpiar la pantalla o reiniciar procesos.
    """
    _instance = None
    _listener_started = False
    _last_poll_time = 0.0
    _lock = threading.Lock()
    _last_version: int = int(time.time() * 1000)
    _state: Dict[str, Any] = {
        "version": int(time.time() * 1000),
        "action": "INIT",
        "barcode": "",
        "source": "SERVER",
        "timestamp": time.time(),
        "product_name": "",
        "new_stock": 0.0,
        "tab_name": "",
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LiveSyncService, cls).__new__(cls)
            try:
                SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
                if SYNC_FILE.exists():
                    with open(SYNC_FILE, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, dict) and "version" in saved:
                            cls._state = saved
                            cls._last_version = max(cls._last_version, int(saved.get("version", 0)))
            except Exception:
                pass
            
            # Iniciar hilo de escucha en tiempo real
            if not cls._listener_started:
                cls._listener_started = True
                t = threading.Thread(target=cls._run_cloud_listener, daemon=True)
                t.start()
        return cls._instance

    @classmethod
    def _next_version(cls) -> int:
        """Genera un número de versión estrictamente creciente basado en milisegundos epoch."""
        with cls._lock:
            now_ms = int(time.time() * 1000)
            if now_ms <= cls._last_version:
                cls._last_version += 1
            else:
                cls._last_version = now_ms
            return cls._last_version

    @classmethod
    def _save_disk_only(cls):
        """Guarda en disco local sin retransmitir a la nube."""
        try:
            SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SYNC_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._state, f, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def _save_state(cls):
        cls._save_disk_only()

    @classmethod
    def _broadcast_cloud(cls, payload: Dict[str, Any]):
        """Envía el evento a la nube en un hilo demonio ultrarrápido y no bloqueante."""
        def _post():
            try:
                httpx.post(
                    CLOUD_URL,
                    content=json.dumps(payload),
                    headers={"Title": "Sync", "Priority": "high"},
                    timeout=3.0,
                )
            except Exception:
                pass
        threading.Thread(target=_post, daemon=True).start()

    @classmethod
    def _poll_cloud(cls):
        """Consulta eventos recientes en la nube de forma segura."""
        try:
            r = httpx.get(f"{CLOUD_URL}/json?poll=1", timeout=1.5)
            if r.status_code == 200:
                with cls._lock:
                    max_ver = cls._state.get("version", 0)
                    latest_data = None
                    for line in r.text.strip().split("\n"):
                        if line.strip():
                            try:
                                item = json.loads(line)
                                if item.get("event") == "message":
                                    msg_raw = item.get("message")
                                    if msg_raw:
                                        data = json.loads(msg_raw) if isinstance(msg_raw, str) else msg_raw
                                        if isinstance(data, dict):
                                            ver = data.get("version", 0)
                                            if ver > max_ver:
                                                max_ver = ver
                                                latest_data = data
                            except Exception:
                                pass
                    if latest_data and max_ver > cls._state.get("version", 0):
                        cls._state = latest_data
                        cls._last_version = max(cls._last_version, max_ver)
                        cls._save_disk_only()
        except Exception:
            pass

    @classmethod
    def _run_cloud_listener(cls):
        """Hilo demonio permanente: lee eventos de la nube en tiempo real sin timeouts de inactividad."""
        cls._poll_cloud()
        # Timeout sin límite de lectura para que no aborte la conexión durante silencios normales
        stream_timeout = httpx.Timeout(connect=8.0, read=None, write=8.0, pool=None)
        while True:
            try:
                with httpx.stream("GET", f"{CLOUD_URL}/json", timeout=stream_timeout) as resp:
                    for line in resp.iter_lines():
                        if line.strip():
                            try:
                                item = json.loads(line)
                                if item.get("event") == "message":
                                    msg_raw = item.get("message")
                                    if msg_raw:
                                        data = json.loads(msg_raw) if isinstance(msg_raw, str) else msg_raw
                                        if isinstance(data, dict):
                                            ver = data.get("version", 0)
                                            with cls._lock:
                                                if ver > cls._state.get("version", 0):
                                                    cls._state = data
                                                    cls._last_version = max(cls._last_version, ver)
                                                    cls._save_disk_only()
                            except Exception:
                                pass
            except Exception:
                time.sleep(0.5)
                cls._poll_cloud()

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        """Obtiene el estado compartido leyendo disco y verificando la nube."""
        # 1. Verificar cambios en disco local (inter-proceso)
        if SYNC_FILE.exists():
            try:
                with open(SYNC_FILE, "r", encoding="utf-8") as f:
                    disk_state = json.load(f)
                    if isinstance(disk_state, dict):
                        d_ver = disk_state.get("version", 0)
                        with cls._lock:
                            if d_ver > cls._state.get("version", 0):
                                cls._state = disk_state
                                cls._last_version = max(cls._last_version, d_ver)
            except Exception:
                pass

        # 2. Polling de respaldo en segundo plano si pasaron más de 0.8 segundos
        now = time.time()
        if now - cls._last_poll_time > 0.8:
            cls._last_poll_time = now
            threading.Thread(target=cls._poll_cloud, daemon=True).start()

        with cls._lock:
            return cls._state.copy()

    @classmethod
    def broadcast_scan(cls, barcode: str, source: str = "Lector PC") -> int:
        """Emite un evento de escaneo para que todos los dispositivos (celulares/PCs) abran el producto."""
        clean_barcode = str(barcode).replace('"', '-').replace("'", '-').replace('/', '-').replace('_', '-').replace('?', '-').strip().upper()
        now = time.time()

        # Evitar doble disparo inmediato idéntico (ej: evento JS + evento input Streamlit)
        with cls._lock:
            if (
                cls._state.get("action") == "SCAN"
                and cls._state.get("barcode") == clean_barcode
                and (now - cls._state.get("timestamp", 0)) < 0.6
            ):
                return cls._state.get("version", 0)

        new_ver = cls._next_version()
        with cls._lock:
            cls._state = {
                "version": new_ver,
                "action": "SCAN",
                "barcode": clean_barcode,
                "source": source,
                "timestamp": now,
                "product_name": cls._state.get("product_name", ""),
                "new_stock": cls._state.get("new_stock", 0.0),
                "tab_name": cls._state.get("tab_name", ""),
            }
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return new_ver

    @classmethod
    def broadcast_clear(cls, source: str = "Usuario") -> int:
        """Emite evento de limpieza de escaneo."""
        new_ver = cls._next_version()
        now = time.time()
        with cls._lock:
            cls._state = {
                "version": new_ver,
                "action": "CLEAR",
                "barcode": "",
                "source": source,
                "timestamp": now,
                "product_name": "",
                "new_stock": 0.0,
                "tab_name": cls._state.get("tab_name", ""),
            }
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return new_ver

    @classmethod
    def broadcast_saved(
        cls,
        barcode: str,
        product_name: str,
        new_stock: float,
        tab_name: str,
        source: str = "Dispositivo",
    ) -> int:
        """Emite notificación de stock guardado exitosamente."""
        new_ver = cls._next_version()
        clean_barcode = str(barcode).replace('"', '-').replace("'", '-').replace('/', '-').replace('_', '-').replace('?', '-').strip().upper()
        now = time.time()
        with cls._lock:
            cls._state = {
                "version": new_ver,
                "action": "SAVED",
                "barcode": clean_barcode,
                "product_name": product_name,
                "new_stock": new_stock,
                "tab_name": tab_name,
                "source": source,
                "timestamp": now,
            }
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return new_ver

    @staticmethod
    def get_local_ip() -> str:
        """Detecta la IP local de la máquina en la red Wi-Fi para que el celular se conecte."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

sync_service = LiveSyncService()
