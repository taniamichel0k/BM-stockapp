import os
import sys
import time
import socket
import subprocess
import signal

def is_port_in_use(port=8501):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def wait_for_port(port=8501, timeout=25):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.3)
    return False

def launch_app_window(url="http://localhost:8501"):
    # Intentar con pywebview para ventana nativa de escritorio pura
    try:
        import webview
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "app_icon.ico"))
        
        window = webview.create_window(
            title="Control de Stock BM",
            url=url,
            width=1380,
            height=860,
            min_size=(1024, 650),
            confirm_close=False
        )
        webview.start(debug=False)
        return True
    except Exception as e:
        print(f"[Aviso] pywebview no pudo inicializar: {e}. Usando modo ventana de aplicación de Windows...")
        
    # Fallback: Modo App de Windows (Edge o Chrome sin barras de direcciones)
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        "msedge.exe"
    ]
    
    launched = False
    for ep in edge_paths:
        if os.path.exists(ep) or ep == "msedge.exe":
            try:
                subprocess.Popen([ep, f"--app={url}", "--window-size=1380,860"])
                launched = True
                break
            except Exception:
                continue
                
    if not launched:
        import webbrowser
        webbrowser.open(url)
    return True

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    server_proc = None
    if not is_port_in_use(8501):
        print("Iniciando servidor interno de Control de Stock BM...")
        # En Windows ocultamos la consola del proceso hijo si es necesario
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW

        server_proc = subprocess.Popen(
            [
                sys.executable,
                "-m", "streamlit", "run", "app.py",
                "--server.port", "8501",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false"
            ],
            cwd=base_dir,
            creationflags=creation_flags
        )
        
        # Esperar a que el servidor esté listo
        ready = wait_for_port(8501, timeout=30)
        if not ready:
            print("Error: El servidor tardó demasiado en responder.")
            if server_proc:
                server_proc.kill()
            sys.exit(1)
    else:
        print("Servidor ya activo en puerto 8501.")

    print("Abriendo ventana de software independiente...")
    try:
        launch_app_window("http://localhost:8501")
    finally:
        # Al cerrar la ventana, si nosotros iniciamos el servidor, lo apagamos limpiamente
        if server_proc:
            print("Cerrando aplicación y liberando recursos...")
            try:
                server_proc.terminate()
                server_proc.wait(timeout=3)
            except Exception:
                server_proc.kill()

if __name__ == "__main__":
    main()
