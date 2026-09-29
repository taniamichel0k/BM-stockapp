import logging
import re
import threading
from typing import List, Optional, Dict, Any
from models.schemas import StockItem, StockMovement, MovementType
from services.sheets_service import SheetsService
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

class StockService:
    def __init__(self, sheets_service: Optional[SheetsService] = None, telegram_service: Optional[TelegramService] = None):
        self.sheets = sheets_service or SheetsService()
        self.telegram = telegram_service or TelegramService()

    def get_available_tabs(self, force_refresh: bool = False) -> List[str]:
        """Devuelve la lista de pestañas de semanas y base."""
        return self.sheets.get_available_tabs(force_refresh=force_refresh)

    def get_current_week_tab_name(self) -> str:
        """Devuelve el nombre de la pestaña correspondiente a la semana actual."""
        return self.sheets.get_current_week_tab_name()

    def create_new_weekly_tab(self, tab_name: Optional[str] = None) -> str:
        """Crea una nueva pestaña semanal limpia en Google Sheets."""
        return self.sheets.create_new_weekly_tab(tab_name=tab_name)

    def get_inventory(self, category: Optional[str] = None, search_query: Optional[str] = None, tab_name: Optional[str] = None, force_refresh: bool = False) -> List[StockItem]:
        """Obtiene la lista de insumos de la pestaña seleccionada (o de la semana actual por defecto) con caché rápido."""
        items = self.sheets.load_from_google_sheets(tab_name=tab_name, force_refresh=force_refresh)
        
        if category and category != "Todas":
            items = [item for item in items if item.category.lower() == category.lower()]

        if search_query:
            q = search_query.strip().lower()
            items = [
                item for item in items
                if q in item.barcode.lower() or q in item.description.lower() or (item.notes and q in item.notes.lower())
            ]

        return items

    def find_by_barcode(self, barcode: str, items: Optional[List[StockItem]] = None, tab_name: Optional[str] = None) -> Optional[StockItem]:
        """Busca un ítem por código de barras exacto, alias registrado, tokens, números clave o descripción."""
        if not barcode:
            return None
        
        # Normalizar caracteres que los escáneres Nictom alteran por layout de teclado (US vs Español)
        raw_str = str(barcode).strip().upper()
        normalized_code = (
            raw_str.replace('"', '-')
            .replace("'", '-')
            .replace('/', '-')
            .replace('_', '-')
            .replace('?', '-')
            .replace(' ', '-')
        )
        
        code_alpha = "".join(c for c in raw_str if c.isalnum())

        # 1. Comprobar en alias registrados (códigos de barra de fabricantes asociados)
        aliases = self.sheets.get_aliases()
        if raw_str in aliases:
            raw_str = aliases[raw_str]
        elif normalized_code in aliases:
            normalized_code = aliases[normalized_code]
        elif code_alpha in aliases:
            code_alpha = aliases[code_alpha]

        catalog = items if items is not None else self.sheets.load_from_google_sheets(tab_name=tab_name)
        if not catalog:
            return None
        
        # 2. Coincidencia exacta o normalizada directa
        for it in catalog:
            b_clean = it.barcode.strip().upper()
            if b_clean == raw_str or b_clean == normalized_code:
                return it

        # 3. Coincidencia alfanumérica directa (ej: POL02CM001 == POL-02CM-001, INSGRA9040 == INS-GRA-9040)
        if code_alpha:
            for it in catalog:
                b_alpha = "".join(c for c in it.barcode.strip().upper() if c.isalnum())
                if b_alpha and b_alpha == code_alpha:
                    return it

        # 4. Coincidencia por estructura de tokens (ej: TOR-FIX-75 coincide con TOR-FIX-075)
        tokens = [t for t in re.split(r'[^A-Za-z0-9]+', raw_str) if t]
        if len(tokens) >= 2:
            for it in catalog:
                it_tokens = [t for t in re.split(r'[^A-Za-z0-9]+', it.barcode.upper()) if t]
                if len(tokens) == len(it_tokens):
                    match = True
                    for t1, t2 in zip(tokens, it_tokens):
                        if t1.lstrip('0') != t2.lstrip('0') and t1 != t2:
                            match = False
                            break
                    if match:
                        return it

        # 5. Coincidencia por descripción (ej: 'terciado', 'terceado', 'fana', 'cinta')
        raw_low = raw_str.lower()
        for it in catalog:
            d_low = it.description.strip().lower()
            if len(raw_low) >= 4 and (raw_low in d_low or d_low in raw_low):
                return it
            if "terc" in raw_low and "terc" in d_low:
                return it

        # 6. Coincidencia por número identificador de modelo (ej: 9040, 8411, 045, 075, 025, 516)
        # Nota de seguridad: Solo se aceptan números significativos (>= 2 dígitos no ceros o >= 3 caracteres),
        # jamás dígitos simples como '1' o '2' para evitar mezclar productos.
        digits = [d for d in re.findall(r'\d+', raw_str) if len(d.lstrip('0')) >= 2 or len(d) >= 3]
        for d in digits:
            d_u = d.lstrip('0')
            for it in catalog:
                it_digits = [x.lstrip('0') for x in re.findall(r'\d+', it.barcode) if len(x.lstrip('0')) >= 2 or len(x) >= 3]
                if d_u in it_digits:
                    return it

        return None

    def link_barcode(self, scanned_code: str, target_barcode: str) -> bool:
        """Asocia un código físico al catálogo de insumos."""
        self.sheets.link_barcode_alias(scanned_code, target_barcode)
        return True

    def get_critical_items(self, items: Optional[List[StockItem]] = None, tab_name: Optional[str] = None) -> List[StockItem]:
        """Obtiene únicamente los insumos que requieren reposición urgente."""
        catalog = items if items is not None else self.sheets.load_from_google_sheets(tab_name=tab_name)
        return [item for item in catalog if item.is_critical]

    def get_kpis(self, items: Optional[List[StockItem]] = None, tab_name: Optional[str] = None) -> Dict[str, Any]:
        """Calcula métricas clave del inventario de la fábrica."""
        catalog = items if items is not None else self.sheets.load_from_google_sheets(tab_name=tab_name)
        total_items = len(catalog)
        critical_items = [it for it in catalog if it.is_critical]
        total_valuation = sum(it.subtotal for it in catalog)
        
        categories_count = {}
        for it in catalog:
            categories_count[it.category] = categories_count.get(it.category, 0) + 1

        return {
            "total_items": total_items,
            "critical_count": len(critical_items),
            "normal_count": total_items - len(critical_items),
            "total_valuation": total_valuation,
            "categories_distribution": categories_count,
        }

    def update_stock_manual(
        self,
        barcode: str,
        quantity: float,
        mode: str = "SET",
        notes: Optional[str] = None,
        operator: str = "Operario Lector Nictom",
        tab_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Carga manual rápida de stock."""
        updated_item = self.sheets.update_single_item_stock(
            barcode=barcode,
            new_quantity=quantity,
            mode=mode,
            notes=notes,
            tab_name=tab_name,
        )

        if not updated_item:
            raise ValueError(f"No se encontró ningún insumo con código '{barcode}'")

        if updated_item.is_critical:
            def _send_tg_manual():
                try:
                    self.telegram.send_critical_item_alert(
                        item=updated_item,
                        responsible=operator,
                    )
                except Exception:
                    pass
            threading.Thread(target=_send_tg_manual, daemon=True).start()

        return {
            "item": updated_item,
            "new_stock": updated_item.current_stock,
            "is_critical": updated_item.is_critical,
            "telegram_sent": updated_item.is_critical,
        }

    def update_product_sheets_fields(
        self,
        barcode: str,
        cant_inventario: float,
        compra_semana: float,
        min_stock: float,
        unit_price: float,
        notes: Optional[str] = None,
        operator: str = "Operario Móvil/PC",
        tab_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Carga manual de todos los campos exactos de Google Sheets."""
        updated_item = self.sheets.update_item_full_fields(
            barcode=barcode,
            cant_inventario=cant_inventario,
            compra_semana=compra_semana,
            min_stock=min_stock,
            unit_price=unit_price,
            notes=notes,
            tab_name=tab_name,
            description=description,
        )

        if not updated_item:
            raise ValueError(f"No se encontró ningún insumo con código '{barcode}'")

        # El mensaje de Telegram solo se envía si el producto quedó en stock crítico
        if updated_item.is_critical:
            def _send_tg_full():
                try:
                    self.telegram.send_critical_item_alert(
                        item=updated_item,
                        responsible=operator,
                    )
                except Exception:
                    pass
            threading.Thread(target=_send_tg_full, daemon=True).start()

        return {
            "item": updated_item,
            "new_stock": updated_item.current_stock,
            "is_critical": updated_item.is_critical,
            "telegram_sent": updated_item.is_critical,
        }

    def save_bulk_from_editor(self, items: List[StockItem], tab_name: Optional[str] = None) -> None:
        """Guarda la lista completa cuando el usuario edita celdas directamente en la grilla tipo Sheets."""
        self.sheets.save_local_inventory(items, tab_name=tab_name)
        self.sheets.update_bulk_in_sheet(items, tab_name=tab_name)

    def register_movement(self, movement: StockMovement, tab_name: Optional[str] = None) -> Dict[str, Any]:
        """Registra un movimiento y solo notifica a Telegram si el producto queda en stock crítico."""
        mode_map = {
            MovementType.INGRESO: "ADD",
            MovementType.EGRESO: "SUB",
            MovementType.AJUSTE: "SET",
        }
        mode = mode_map.get(movement.movement_type, "SET")
        return self.update_stock_manual(
            barcode=movement.barcode,
            quantity=movement.quantity,
            mode=mode,
            notes=movement.reason,
            operator=movement.responsible or "Operario",
            tab_name=tab_name,
        )

    def trigger_batch_telegram_alerts(self, items: Optional[List[StockItem]] = None, tab_name: Optional[str] = None) -> Dict[str, Any]:
        """Dispara la alerta a Telegram con todos los insumos críticos actuales."""
        critical = self.get_critical_items(items=items, tab_name=tab_name)
        sent = self.telegram.send_critical_stock_alert(critical)
        return {
            "sent": sent,
            "count": len(critical),
            "critical_items": critical,
        }
