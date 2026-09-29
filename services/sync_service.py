import sys
import json
import time
import socket
from pathlib import Path
from typing import Optional, Dict, Any

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

class LiveSyncService:
    """
    Servicio de sincronización en tiempo real entre múltiples dispositivos
    (PC con lector de barras NICTOM y Celular del operario/supervisor).
    Persiste en disco para sincronización inter-proceso entre FastAPI y Streamlit.
    """
    _instance = None
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
            SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            if SYNC_FILE.exists():
                try:
                    with open(SYNC_FILE, "r", encoding="utf-8") as f:
                        saved = json.load(f)
                        if isinstance(saved, dict) and "version" in saved:
                            cls._state = saved
                except Exception:
                    pass
        return cls._instance

    @classmethod
    def _save_state(cls):
        try:
            SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SYNC_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._state, f, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        """Obtiene el estado compartido leyendo disco si hubo cambios de otro proceso."""
        if SYNC_FILE.exists():
            try:
                with open(SYNC_FILE, "r", encoding="utf-8") as f:
                    disk_state = json.load(f)
                    if isinstance(disk_state, dict) and disk_state.get("version", 0) > cls._state.get("version", 0):
                        cls._state = disk_state
            except Exception:
                pass
        return cls._state.copy()

    @classmethod
    def broadcast_scan(cls, barcode: str, source: str = "Lector PC") -> int:
        """Emite un evento de escaneo para que todos los dispositivos (celulares/PCs) abran el producto."""
        cls.get_state()  # Asegurar última versión
        cls._state["version"] += 1
        cls._state["action"] = "SCAN"
        cls._state["barcode"] = barcode.strip().upper()
        cls._state["source"] = source
        cls._state["timestamp"] = time.time()
        cls._save_state()
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
        cls._save_state()
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
        cls._save_state()
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
