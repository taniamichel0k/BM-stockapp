import logging
from typing import List, Optional
import httpx

from config import settings
from models.schemas import StockItem

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and "tu_token" not in self.bot_token)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Envía un mensaje de texto formateado al chat o grupo configurado."""
        if not self.is_configured:
            logger.info(f"[TELEGRAM SIMULADO - Sin token configurado]:\n{text}")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Error enviando mensaje a Telegram: {e}")
            return False

    def send_message_sync(self, text: str, parse_mode: str = "HTML") -> bool:
        """Versión síncrona para usar en Streamlit u otros scripts."""
        if not self.is_configured:
            logger.info(f"[TELEGRAM SIMULADO - Sin token configurado]:\n{text}")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Error enviando mensaje a Telegram (sync): {e}")
            return False

    def send_critical_stock_alert(self, items: List[StockItem]) -> bool:
        """Envía un informe de alerta con todos los insumos críticos o faltantes en la fábrica."""
        if not items:
            return True

        header = (
            "🚨 <b>ALERTA DE STOCK CRÍTICO</b> 🚨\n"
            "🏭 <i>Fábrica de Sillones - Control de Materiales</i>\n\n"
            f"Se detectaron <b>{len(items)}</b> insumos con stock por debajo del nivel mínimo:\n\n"
        )

        messages = []
        current_chunk = header
        footer = "\n👉 <i>Por favor coordinar compras con los proveedores correspondientes.</i>"

        for idx, it in enumerate(items, start=1):
            item_text = (
                f"<b>{idx}. [{it.barcode}] {it.description}</b>\n"
                f"   • Stock actual: <b>{it.current_stock:g} {it.unit}</b> (Mínimo: {it.min_stock:g})\n"
                f"   • Categoría: {it.category}\n"
            )
            if it.notes:
                item_text += f"   • Obs: <i>{it.notes}</i>\n"
            item_text += "\n"

            # Si el mensaje actual supera los 3500 caracteres, enviamos este bloque e iniciamos otro
            if len(current_chunk) + len(item_text) > 3500:
                messages.append(current_chunk)
                current_chunk = item_text
            else:
                current_chunk += item_text

        current_chunk += footer
        messages.append(current_chunk)

        success = True
        for msg in messages:
            if not self.send_message_sync(msg):
                success = False

        return success

    def send_critical_item_alert(self, item: StockItem, responsible: str = "Operario") -> bool:
        """Notifica exclusivamente cuando un insumo entra en nivel crítico de reposición."""
        text = (
            "🚨 <b>ALERTA: STOCK CRÍTICO DETECTADO</b> 🚨\n"
            "🏭 <i>Control de Materiales - Fábrica de Sillones</i>\n\n"
            f"• <b>Insumo:</b> [{item.barcode}] {item.description}\n"
            f"• <b>Stock Actual:</b> <b>{item.current_stock:g} {item.unit}</b>\n"
            f"• <b>Stock Mínimo:</b> {item.min_stock:g} {item.unit}\n"
            f"• <b>A Comprar:</b> <b>{item.comprar:g} {item.unit}</b>\n"
            f"• <b>Registrado por:</b> {responsible}\n\n"
            "👉 <i>Se requiere coordinar compra o reposición urgente.</i>"
        )
        return self.send_message_sync(text)

    def send_movement_alert(self, item: StockItem, movement_type: str, qty: float, responsible: str, reason: str = "") -> bool:
        """Notifica el registro de una entrada o salida importante de material."""
        emoji = "📦 🟢" if movement_type == "INGRESO" else "📤 🔴"
        text = (
            f"{emoji} <b>MOVIMIENTO DE STOCK: {movement_type}</b>\n"
            f"🏭 <i>Fábrica de Sillones</i>\n\n"
            f"• <b>Insumo:</b> [{item.barcode}] {item.description}\n"
            f"• <b>Cantidad:</b> {qty:g} {item.unit}\n"
            f"• <b>Nuevo Stock:</b> {item.current_stock:g} {item.unit}\n"
            f"• <b>Responsable:</b> {responsible}\n"
        )
        if reason:
            text += f"• <b>Motivo:</b> {reason}\n"

        if item.is_critical:
            text += "\n⚠️ <b>¡ATENCIÓN!</b> Este insumo quedó en estado crítico de reposición."

        return self.send_message_sync(text)
