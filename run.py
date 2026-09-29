import sys
import subprocess
from config import settings

def run_streamlit():
    print("🚀 Iniciando aplicación web Streamlit...")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(settings.STREAMLIT_PORT),
        "--server.address", settings.API_HOST
    ])

def run_api():
    print("⚡ Iniciando API FastAPI en http://localhost:8000 ...")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "api.main:app",
        "--host", settings.API_HOST,
        "--port", str(settings.API_PORT),
        "--reload"
    ])

if __name__ == "__main__":
    choice = sys.argv[1].lower() if len(sys.argv) > 1 else "streamlit"
    
    if choice == "streamlit":
        run_streamlit()
    elif choice == "api":
        run_api()
    else:
        print("Uso:")
        print("  python run.py streamlit   -> Iniciar Dashboard interactivo en Streamlit")
        print("  python run.py api         -> Iniciar servidor backend FastAPI")
