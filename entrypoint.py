import os
import sys
import socket
import subprocess
import threading
import time
import multiprocessing

# En Windows y PyInstaller, freeze_support es obligatorio
multiprocessing.freeze_support()

log_path = os.path.join(os.environ.get("TEMP", "."), "app_stock_debug.log")
try:
    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None or getattr(sys, 'frozen', False):
        sys.stdout = log_file
    if sys.stderr is None or getattr(sys, 'frozen', False):
        sys.stderr = log_file
except Exception:
    pass

# Importar explícitamente todas las dependencias del proyecto
try:
    import pydantic
    import pydantic_core
    import pydantic_settings
    import gspread
    import google.auth
    import google.oauth2
    import google_auth_oauthlib
    import httpx
    import fastapi
    import uvicorn
    import openpyxl
    import pandas
    from PIL import Image
    import zxingcpp
    import dotenv
    
    # Módulos internos
    import config
    import models.schemas
    import services.stock_service
    import services.sheets_service
    import services.telegram_service
    import services.sync_service
    import api.main
except Exception as e:
    pass

def kill_zombies_on_port(port=8501):
    """Cierra cualquier proceso huérfano de una sesión previa que haya dejado el puerto ocupado."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"[BOOT] Port {port} is occupied. Cleaning zombie processes...")
                current_pid = os.getpid()
                cmd = f'powershell -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Where-Object {{ $_.OwningProcess -ne {current_pid} }} | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'
                creationflags = 0x08000000 if sys.platform == "win32" else 0
                subprocess.run(cmd, shell=True, capture_output=True, timeout=5, creationflags=creationflags)
                time.sleep(0.5)
    except Exception as e:
        print(f"[BOOT] kill_zombies_on_port warning: {e}")

def wait_for_server(port=8501, timeout=45):
    """Espera activamente a que el servidor Streamlit esté escuchando en el puerto antes de abrir la ventana."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    print(f"[BOOT] Server ready on port {port} in {time.time() - start:.1f}s")
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    print(f"[BOOT] Server timeout waiting for port {port}")
    return False

def open_app_window():
    ready = wait_for_server(port=8501, timeout=45)
    
    # Cerrar splash screen pase lo que pase
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass

    if not ready:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "El servidor de Control de Stock demoró más de lo esperado en iniciar.\nRevisa el archivo de registro en %TEMP%\\app_stock_debug.log.",
                "Control de Stock BM",
                0x30
            )
        except Exception:
            pass
        return
    
    time.sleep(0.5)
    
    url = "http://localhost:8501"
    profile_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.environ.get("TEMP", ".")), "ControlStockBM_Profile")
    try:
        os.makedirs(profile_dir, exist_ok=True)
    except Exception:
        profile_dir = os.path.join(os.environ.get("TEMP", "."), "ControlStockBM_Profile")

    browser_candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        "msedge.exe",
        "chrome.exe"
    ]
    
    opened = False
    for b in browser_candidates:
        if os.path.exists(b) or b in ("msedge.exe", "chrome.exe"):
            try:
                print(f"[BOOT] Launching browser window: {b}")
                cmd = [
                    b,
                    f"--app={url}",
                    f"--user-data-dir={profile_dir}",
                    "--window-size=1380,860",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
                subprocess.Popen(cmd)
                opened = True
                break
            except Exception as e:
                print(f"[BOOT] Failed with browser {b}: {e}")
                continue
                
    if not opened:
        try:
            print("[BOOT] Fallback to default webbrowser")
            import webbrowser
            webbrowser.open(url, new=1)
        except Exception as e:
            print(f"[BOOT] Fallback error: {e}")
            os.system(f'start "" "{url}"')

def main():
    try:
        if getattr(sys, 'frozen', False):
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"[BOOT] Starting Control de Stock BM. base_dir={base_dir}")
        os.chdir(base_dir)
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)

        # Limpiar cualquier proceso zombi previo en puerto 8501
        kill_zombies_on_port(8501)

        # Iniciar hilo que vigila y abre la ventana cuando el servidor esté listo
        threading.Thread(target=open_app_window, daemon=True).start()

        # Iniciar túnel de Cloudflare para celular (4G / fuera del taller)
        try:
            from services.tunnel_service import TunnelService
            TunnelService.start_tunnel_in_background(port=8501)
        except Exception as e:
            print(f"[BOOT] Error iniciando túnel: {e}")

        from streamlit.web import cli as stcli
        app_path = os.path.join(base_dir, "app.py")
        print(f"[BOOT] app_path={app_path}, exists={os.path.exists(app_path)}")

        sys.argv = [
            "streamlit",
            "run",
            app_path,
            "--global.developmentMode=false",
            "--server.port=8501",
            "--server.headless=true",
            "--browser.gatherUsageStats=false"
        ]
        
        sys.exit(stcli.main())
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Error al iniciar Control de Stock BM:\n\n{e}", "Error de Inicio", 0x10)
        except Exception:
            pass

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
