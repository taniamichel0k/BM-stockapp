import os
import sys
import re
import time
import subprocess
import threading
from pathlib import Path
from typing import Optional

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
    meipass_dir = Path(getattr(sys, '_MEIPASS', BASE_DIR))
else:
    BASE_DIR = Path(__file__).parent.parent
    meipass_dir = BASE_DIR

TUNNEL_URL_FILE = BASE_DIR / "data" / "tunnel_url.txt"
try:
    TUNNEL_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    TUNNEL_URL_FILE = Path(os.environ.get("TEMP", ".")) / "StockBM_data" / "tunnel_url.txt"
    TUNNEL_URL_FILE.parent.mkdir(parents=True, exist_ok=True)

# Buscar cloudflared.exe en:
# 1) Junto al .exe en la carpeta actual
# 2) Empaquetado dentro del bundle de PyInstaller (_MEIPASS)
# 3) En la carpeta raíz del proyecto
CLOUDFLARED_EXE = BASE_DIR / "cloudflared.exe"
if not CLOUDFLARED_EXE.exists():
    if (meipass_dir / "cloudflared.exe").exists():
        CLOUDFLARED_EXE = meipass_dir / "cloudflared.exe"
    elif (Path(__file__).parent.parent / "cloudflared.exe").exists():
        CLOUDFLARED_EXE = Path(__file__).parent.parent / "cloudflared.exe"

class TunnelService:
    _process: Optional[subprocess.Popen] = None
    _url: Optional[str] = None
    _lock = threading.Lock()

    @classmethod
    def get_saved_url(cls) -> Optional[str]:
        # Si el proceso del túnel murió, limpiar
        if cls._process and cls._process.poll() is not None:
            cls._url = None
            cls._process = None

        if cls._url:
            return cls._url

        if TUNNEL_URL_FILE.exists():
            # Solo confiar si cloudflared está realmente en ejecución
            if not cls.is_cloudflared_running():
                try:
                    TUNNEL_URL_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                return None
            try:
                # Comprobar edad del archivo (si tiene más de 3 horas, descartar)
                mtime = os.path.getmtime(TUNNEL_URL_FILE)
                if time.time() - mtime > 10800:
                    TUNNEL_URL_FILE.unlink(missing_ok=True)
                    return None
                url = TUNNEL_URL_FILE.read_text(encoding="utf-8").strip()
                if url.startswith("https://") and "trycloudflare.com" in url:
                    # Validar rápidamente que la URL responda
                    try:
                        import httpx
                        r = httpx.get(url, timeout=1.5)
                        if r.status_code == 200:
                            cls._url = url
                            return url
                        else:
                            TUNNEL_URL_FILE.unlink(missing_ok=True)
                            return None
                    except Exception:
                        TUNNEL_URL_FILE.unlink(missing_ok=True)
                        return None
            except Exception:
                pass
        return None

    @classmethod
    def is_cloudflared_running(cls) -> bool:
        """Verifica si cloudflared.exe ya está en ejecución en el sistema."""
        try:
            cmd = 'tasklist /FI "IMAGENAME eq cloudflared.exe" /NH'
            out = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
            return "cloudflared.exe" in out.lower()
        except Exception:
            return False

    @classmethod
    def start_tunnel_in_background(cls, port: int = 8501) -> None:
        """Inicia el túnel de Cloudflare en segundo plano si cloudflared.exe está disponible."""
        with cls._lock:
            # Si ya tenemos un proceso activo y una URL válida, no reiniciar
            if cls._process and cls._process.poll() is None and cls._url:
                return

            if not CLOUDFLARED_EXE.exists():
                return

            # Terminar instancias huérfanas de cloudflared para no acumular procesos ni URLs vencidas
            if cls.is_cloudflared_running() and not cls._process:
                try:
                    subprocess.run('taskkill /F /IM "cloudflared.exe"', shell=True, capture_output=True)
                except Exception:
                    pass
                cls._url = None
                try:
                    TUNNEL_URL_FILE.unlink(missing_ok=True)
                except Exception:
                    pass

            def _run():
                try:
                    creationflags = 0x08000000 if sys.platform == "win32" else 0
                    cmd = [
                        str(CLOUDFLARED_EXE),
                        "tunnel",
                        "--url",
                        f"http://localhost:{port}"
                    ]
                    cls._process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=creationflags
                    )
                    
                    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
                    # Consumir el stream continuamente para evitar deadlocks de buffer en Windows
                    for line in cls._process.stdout:
                        if not cls._url:
                            match = url_pattern.search(line)
                            if match:
                                found_url = match.group(0)
                                cls._url = found_url
                                try:
                                    TUNNEL_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
                                    TUNNEL_URL_FILE.write_text(found_url, encoding="utf-8")
                                except Exception:
                                    pass
                                print(f"[TUNNEL] Cloudflare Tunnel activo: {found_url}")
                except Exception as e:
                    print(f"[TUNNEL] Error en Cloudflare Tunnel: {e}")

            t = threading.Thread(target=_run, daemon=True)
            t.start()

    @classmethod
    def stop_tunnel(cls):
        with cls._lock:
            if cls._process and cls._process.poll() is None:
                try:
                    cls._process.terminate()
                except Exception:
                    pass
            cls._process = None
            cls._url = None
            try:
                TUNNEL_URL_FILE.unlink(missing_ok=True)
            except Exception:
                pass
