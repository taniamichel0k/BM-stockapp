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
    Persiste en disco para sincronización inter-proceso local y transmite mediante
    retransmisor en la nube ultrarrápido (ntfy.sh) para sincronización en tiempo real
    entre la app de escritorio y la app de celular en la nube (Streamlit Cloud / 4G / Wi-Fi).
    """
    _instance = None
    _listener_started = False
    _last_poll_time = 0.0
    _state: Dict[str, Any] = {
        "version": 0,
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
            except Exception:
                pass
            
            # Iniciar hilo de escucha en tiempo real
            if not cls._listener_started:
                cls._listener_started = True
                t = threading.Thread(target=cls._run_cloud_listener, daemon=True)
                t.start()
        return cls._instance

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
                if latest_data:
                    cls._state = latest_data
                    cls._save_disk_only()
        except Exception:
            pass

    @classmethod
    def _run_cloud_listener(cls):
        """Hilo demonio permanente: lee eventos de la nube en tiempo real."""
        cls._poll_cloud()
        while True:
            try:
                with httpx.stream("GET", f"{CLOUD_URL}/json", timeout=60.0) as resp:
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
                                            if ver > cls._state.get("version", 0):
                                                cls._state = data
                                                cls._save_disk_only()
                            except Exception:
                                pass
            except Exception:
                time.sleep(2.0)
                cls._poll_cloud()

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        """Obtiene el estado compartido leyendo disco y verificando la nube."""
        # 1. Verificar cambios en disco local (inter-proceso)
        if SYNC_FILE.exists():
            try:
                with open(SYNC_FILE, "r", encoding="utf-8") as f:
                    disk_state = json.load(f)
                    if isinstance(disk_state, dict) and disk_state.get("version", 0) > cls._state.get("version", 0):
                        cls._state = disk_state
            except Exception:
                pass

        # 2. Polling de respaldo en segundo plano si pasaron más de 2 segundos
        now = time.time()
        if now - cls._last_poll_time > 2.0:
            cls._last_poll_time = now
            threading.Thread(target=cls._poll_cloud, daemon=True).start()

        return cls._state.copy()

    @classmethod
    def broadcast_scan(cls, barcode: str, source: str = "Lector PC") -> int:
        """Emite un evento de escaneo para que todos los dispositivos (celulares/PCs) abran el producto."""
        cls.get_state()
        cls._state["version"] += 1
        cls._state["action"] = "SCAN"
        cls._state["barcode"] = barcode.strip().upper()
        cls._state["source"] = source
        cls._state["timestamp"] = time.time()
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return cls._state["version"]

    @classmethod
    def broadcast_clear(cls, source: str = "Usuario") -> int:
        """Emite evento de limpieza de escaneo."""
        cls.get_state()
        cls._state["version"] += 1
        cls._state["action"] = "CLEAR"
        cls._state["barcode"] = ""
        cls._state["source"] = source
        cls._state["timestamp"] = time.time()
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return cls._state["version"]

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
        cls.get_state()
        cls._state["version"] += 1
        cls._state["action"] = "SAVED"
        cls._state["barcode"] = barcode.strip().upper()
        cls._state["product_name"] = product_name
        cls._state["new_stock"] = new_stock
        cls._state["tab_name"] = tab_name
        cls._state["source"] = source
        cls._state["timestamp"] = time.time()
        cls._save_disk_only()
        cls._broadcast_cloud(cls._state.copy())
        return cls._state["version"]

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
