from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.schemas import StockItem, StockMovement, AlertResponse
from services.stock_service import StockService
from services.sheets_service import SheetsService
from services.telegram_service import TelegramService

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API REST para control de stock en fábrica de sillones, Google Sheets y Alertas por Telegram",
    version=settings.VERSION,
)

# CORS habilitado para interactuar con frontends o clientes externos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stock_service = StockService()
from services.sync_service import sync_service

@app.get("/api/sync_state")
def get_sync_state():
    """Devuelve el estado de escaneo en tiempo real para sincronizar PC y Celulares."""
    return sync_service.get_state()

@app.post("/api/sync_scan")
def post_sync_scan(data: dict):
    """Emite un escaneo a todos los dispositivos conectados."""
    barcode = data.get("barcode", "")
    source = data.get("source", "Lector")
    ver = sync_service.broadcast_scan(barcode, source=source)
    return {"status": "ok", "version": ver, "barcode": barcode}

@app.post("/api/sync_clear")
def post_sync_clear():
    """Limpia el producto activo en todos los dispositivos."""
    ver = sync_service.broadcast_clear()
    return {"status": "ok", "version": ver}

@app.get("/")
def root():
    return {
        "status": "online",
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "spreadsheet_id": settings.SPREADSHEET_ID,
        "telegram_configured": stock_service.telegram.is_configured,
        "docs_url": "/docs",
    }

@app.get("/api/inventory", response_model=List[StockItem])
def get_inventory(
    category: Optional[str] = Query(None, description="Filtrar por categoría (Madera, Telas, Poliéster, etc.)"),
    search: Optional[str] = Query(None, description="Búsqueda por código o descripción"),
):
    """Devuelve el inventario completo o filtrado desde Google Sheets."""
    try:
        return stock_service.get_inventory(category=category, search_query=search)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo inventario: {str(e)}")

@app.get("/api/inventory/critical", response_model=List[StockItem])
def get_critical_inventory():
    """Devuelve los insumos que están en nivel crítico o por debajo del stock mínimo."""
    try:
        return stock_service.get_critical_items()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo insumos críticos: {str(e)}")

@app.get("/api/kpis")
def get_kpis():
    """Retorna métricas clave del inventario (valuación total, insumos críticos, distribución)."""
    try:
        return stock_service.get_kpis()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculando KPIs: {str(e)}")

@app.post("/api/movements")
def register_movement(movement: StockMovement):
    """
    Registra un ingreso o egreso de insumos (telas, maderas, tornillos, gomaespuma).
    Actualiza el stock y notifica por Telegram.
    """
    try:
        result = stock_service.register_movement(movement)
        return {
            "status": "success",
            "movement": movement,
            "result": result,
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registrando movimiento: {str(e)}")

@app.post("/api/alerts/telegram", response_model=AlertResponse)
def trigger_telegram_alert():
    """Dispara inmediatamente el reporte de materiales con stock crítico a Telegram."""
    try:
        res = stock_service.trigger_batch_telegram_alerts()
        msg = f"Se procesaron {res['count']} insumos críticos."
        if not res["sent"] and not stock_service.telegram.is_configured:
            msg += " (Modo simulación: configure TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env para envío real)"
        
        return AlertResponse(
            status="ok",
            sent_to_telegram=res["sent"],
            total_critical_items=res["count"],
            critical_items=res["critical_items"],
            message=msg,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error enviando alerta: {str(e)}")

@app.post("/api/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Webhook opcional para responder a comandos desde Telegram (/start, /stock, /criticos).
    """
    data = await request.json()
    message = data.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not chat_id or not text:
        return {"ok": True}

    reply_service = TelegramService(chat_id=str(chat_id))

    if text.startswith("/start") or text.startswith("/ayuda"):
        welcome_msg = (
            "👋 <b>Bot de Control de Stock - Fábrica de Sillones</b>\n\n"
            "Comandos disponibles:\n"
            "• <code>/criticos</code> - Ver insumos por debajo del stock mínimo\n"
            "• <code>/resumen</code> - Métricas generales del inventario\n"
            "• <code>/buscar [palabra]</code> - Buscar insumos por nombre o código\n"
        )
        await reply_service.send_message(welcome_msg)
    elif text.startswith("/criticos"):
        critical = stock_service.get_critical_items()
        reply_service.send_critical_stock_alert(critical)
    elif text.startswith("/resumen"):
        kpis = stock_service.get_kpis()
        resumen_msg = (
            "📊 <b>Resumen de Stock</b>\n\n"
            f"• <b>Total de Insumos:</b> {kpis['total_items']}\n"
            f"• <b>En estado crítico:</b> ⚠️ {kpis['critical_count']}\n"
            f"• <b>En nivel óptimo:</b> ✅ {kpis['normal_count']}\n"
            f"• <b>Valuación Inventario:</b> ${kpis['total_valuation']:,.2f}\n"
        )
        await reply_service.send_message(resumen_msg)
    
    return {"ok": True}
