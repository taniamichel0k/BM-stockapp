import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Cargar variables desde el archivo .env si existe (junto al exe o en el paquete)
if getattr(sys, 'frozen', False):
    exe_env = Path(sys.executable).parent / ".env"
    if exe_env.exists():
        load_dotenv(exe_env)
load_dotenv(BASE_DIR / ".env")

def _get_val(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)

class Settings:
    PROJECT_NAME: str = "Control de Stock - Fábrica de Sillones"
    VERSION: str = "1.0.0"
    
    # Google Sheets
    @property
    def SPREADSHEET_ID(self) -> str:
        return _get_val("SPREADSHEET_ID", "10xjwh5YEcfRlVSAahAU5lEgNUTvimTq19JKN3gHeIb4")
    
    @property
    def SHEET_GID(self) -> str:
        return _get_val("SHEET_GID", "499396743")
    
    @property
    def GOOGLE_SERVICE_ACCOUNT_FILE(self) -> str:
        env_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        if env_file and Path(env_file).exists():
            return env_file
        if getattr(sys, 'frozen', False):
            exe_creds = Path(sys.executable).parent / "credentials"
            if exe_creds.exists():
                for f in exe_creds.glob("*.json"):
                    if "example" not in f.name.lower():
                        return str(f)
        creds_dir = BASE_DIR / "credentials"
        if creds_dir.exists():
            for f in creds_dir.glob("*.json"):
                if "example" not in f.name.lower():
                    return str(f)
        return str(creds_dir / "service_account.json")
    
    # Telegram Bot
    @property
    def TELEGRAM_BOT_TOKEN(self) -> str:
        return _get_val("TELEGRAM_BOT_TOKEN", "")

    @property
    def TELEGRAM_CHAT_ID(self) -> str:
        return _get_val("TELEGRAM_CHAT_ID", "")

    # Stock
    @property
    def STOCK_MINIMO_DEFAULT(self) -> float:
        return float(_get_val("STOCK_MINIMO_DEFAULT", "5"))

    # Server config
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    STREAMLIT_PORT: int = int(os.getenv("STREAMLIT_PORT", "8501"))

settings = Settings()

