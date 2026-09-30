import os
import sys
import re
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from config import settings
from models.schemas import StockItem
from services.sheets_service import SheetsService
from services.sync_service import sync_service
from services.telegram_service import TelegramService

logger = logging.getLogger(__name__)

if getattr(sys, 'frozen', False):
    BASE_DATA_DIR = Path(sys.executable).parent / "data"
else:
    BASE_DATA_DIR = Path(__file__).parent.parent / "data"

BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
RECIPES_CACHE_FILE = BASE_DATA_DIR / "recipes_cache.json"
ORDERS_HISTORY_FILE = BASE_DATA_DIR / "orders_history.json"


class RecipeService:
    """
    Servicio de Fichas Técnicas (BOM) y Fabricación de Sillones.
    Gestiona el cálculo de insumos, previsualización de stock, descuento automático
    en Google Sheets y edición de recetas.
    """

    def __init__(self, sheets_service: Optional[SheetsService] = None, telegram_service: Optional[TelegramService] = None):
        self.sheets = sheets_service or SheetsService()
        self.telegram = telegram_service or TelegramService()
        self._recipes_cache: Optional[Dict[str, Any]] = None

    def get_recipes(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Obtiene el catálogo de modelos y recetas desde la pestaña RECETAS de Google Sheets
        o desde la caché local ultrarrápida.
        """
        if not force_refresh and self._recipes_cache:
            return self._recipes_cache

        # Intentar desde archivo local si no se fuerza refresco
        if not force_refresh and RECIPES_CACHE_FILE.exists():
            try:
                with open(RECIPES_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data:
                        clean_data = {}
                        for k, v in data.items():
                            clean_k = self._clean_model_name(k)
                            v["name"] = clean_k
                            clean_data[clean_k] = v
                        self._recipes_cache = clean_data
                        return clean_data
            except Exception as e:
                logger.warning(f"Error leyendo recipes_cache.json: {e}")

        # Cargar desde Google Sheets
        client = self.sheets._get_gspread_client()
        if client:
            try:
                sheet = client.open_by_key(self.sheets.spreadsheet_id)
                ws = sheet.worksheet("RECETAS")
                rows = ws.get_all_values()
                parsed = self._parse_recipes_sheet(rows)
                if parsed:
                    self._recipes_cache = parsed
                    try:
                        with open(RECIPES_CACHE_FILE, "w", encoding="utf-8") as f:
                            json.dump(parsed, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    return parsed
            except Exception as e:
                logger.error(f"Error cargando hoja RECETAS desde Google Sheets: {e}")

        # Fallback a caché local si existe
        if RECIPES_CACHE_FILE.exists():
            try:
                with open(RECIPES_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {}

    def _clean_model_name(self, raw_name: str) -> str:
        """Limpia sufijos de tela para agrupar por modelo puro de sillón."""
        clean = re.sub(r"[\s\-_]+(ALPHA|PANA.*|TUSOR).*", "", raw_name, flags=re.I).strip()
        return clean

    def _parse_recipes_sheet(self, rows: List[List[str]]) -> Dict[str, Any]:
        """Parsea la hoja RECETAS estructurando cada modelo, sus insumos y metros de tela."""
        models: Dict[str, Any] = {}
        current_model_key: Optional[str] = None
        section = "BASE"

        for idx, r in enumerate(rows):
            line = " ".join(r).strip()
            if not line:
                continue

            if "MODELO:" in line:
                m = re.search(r"MODELO:\s*([^(]+)", line)
                if m:
                    raw_name = m.group(1).strip()
                    current_model_key = self._clean_model_name(raw_name)
                    if current_model_key not in models:
                        models[current_model_key] = {
                            "name": current_model_key,
                            "raw_name": raw_name,
                            "header_row": idx + 1,
                            "meters_required": 0.0,
                            "items": []
                        }
                    section = "BASE"
                    continue

            if not current_model_key:
                continue

            if "TELAS DE TAPIZADO" in line or "INSUMO A PEDIDO" in line:
                section = "TELA"
                m_meters = re.search(r"([\d.]+)\s*metros", line)
                if m_meters:
                    models[current_model_key]["meters_required"] = float(m_meters.group(1))
                continue
            elif "MANO DE OBRA" in line or "TIEMPOS ESTIMADOS" in line:
                section = "MO"
                continue
            elif "COSTO TOTAL ESTIMADO" in line or "TOTAL MATERIALES" in line or "SUBTOTAL MATERIALES" in line:
                section = "TOTAL"
                continue

            # Saltar encabezados de tabla
            if len(r) >= 5 and r[1].strip() in ["Código Insumo", "Codigo de Barras", "Código"]:
                continue

            # Insumo de la receta
            if len(r) >= 5 and r[1].strip():
                code = r[1].strip().upper()
                desc = r[2].strip() if len(r) > 2 else ""
                qty_str = r[3].strip() if len(r) > 3 else "0"
                unit = r[4].strip() if len(r) > 4 else ""
                price_str = r[5].strip() if len(r) > 5 else "0"

                try:
                    qty = float(qty_str.replace(",", "."))
                except Exception:
                    qty = 0.0

                try:
                    price = float(price_str.replace("$", "").replace(".", "").replace(",", ".").strip())
                except Exception:
                    price = 0.0

                if code.startswith("TEL-") and code != "TEL-FRI-001":
                    # Si no se detectó metros en el encabezado, usar el de la fila de tela
                    if models[current_model_key]["meters_required"] == 0.0 and qty > 0:
                        models[current_model_key]["meters_required"] = qty
                elif not code.startswith("MO-"):
                    # Solo agregar si el código no está duplicado en este modelo
                    existing_codes = [it["code"] for it in models[current_model_key]["items"]]
                    if code not in existing_codes:
                        models[current_model_key]["items"].append({
                            "code": code,
                            "description": desc,
                            "qty": qty,
                            "unit": unit,
                            "unit_price": price,
                            "subtotal": qty * price,
                            "row_index": idx + 1
                        })

        return models

    def get_available_fabrics(self) -> List[Dict[str, Any]]:
        """Lista oficial de telas de tapizado disponibles en fábrica."""
        return [
            {"code": "TEL-ALP-001", "name": "Tela Alpha", "unit_price": 4666.0},
            {"code": "TEL-PAN-RIF", "name": "Tela Pana Riff", "unit_price": 4115.0},
            {"code": "TEL-PAN-JAG", "name": "Tela Pana Jaguar", "unit_price": 6317.0},
            {"code": "TEL-CTX-001", "name": "Tela Cuerotex", "unit_price": 10000.0},
            {"code": "TEL-ECO-CUE", "name": "Tela Eco Cuero", "unit_price": 5100.0},
            {"code": "TEL-CHE-001", "name": "Tela Chenille", "unit_price": 6681.0},
            {"code": "TEL-RUS-001", "name": "Tela Rustic", "unit_price": 5650.0},
            {"code": "TEL-MER-001", "name": "Tela Mercury", "unit_price": 7363.0},
            {"code": "TEL-VAR-001", "name": "Otras telas", "unit_price": 0.0},
        ]

    def calculate_order_requirements(
        self,
        model_name: str,
        quantity: int,
        fabric_code: str
    ) -> Dict[str, Any]:
        """
        Calcula el desglose total de insumos necesarios para fabricar N unidades del sillón.
        """
        recipes = self.get_recipes()
        model_data = recipes.get(model_name)
        if not model_data:
            return {"items": [], "meters_fabric": 0.0, "fabric_code": fabric_code, "total_cost": 0.0}

        req_items: List[Dict[str, Any]] = []
        total_material_cost = 0.0

        # 1. Insumos base de la receta
        for it in model_data.get("items", []):
            total_qty = it["qty"] * quantity
            unit_price = it.get("unit_price", 0.0)
            subtotal = total_qty * unit_price
            total_material_cost += subtotal
            req_items.append({
                "code": it["code"],
                "description": it["description"],
                "required_qty": total_qty,
                "unit": it["unit"],
                "unit_price": unit_price,
                "subtotal": subtotal,
                "is_fabric": False,
                "row_index": it.get("row_index", 0)
            })

        # 2. Tela de tapizado seleccionada
        meters_per_sofa = model_data.get("meters_required", 0.0)
        total_meters = meters_per_sofa * quantity
        if total_meters > 0 and fabric_code:
            fabrics = self.get_available_fabrics()
            selected_fab = next((f for f in fabrics if f["code"] == fabric_code), None)
            fab_name = selected_fab["name"] if selected_fab else fabric_code
            fab_price = selected_fab["unit_price"] if selected_fab else 0.0
            fab_subtotal = total_meters * fab_price
            total_material_cost += fab_subtotal

            req_items.append({
                "code": fabric_code,
                "description": f"{fab_name} (Tapizado)",
                "required_qty": total_meters,
                "unit": "metro",
                "unit_price": fab_price,
                "subtotal": fab_subtotal,
                "is_fabric": True,
                "row_index": 0
            })

        return {
            "items": req_items,
            "meters_fabric": total_meters,
            "fabric_code": fabric_code,
            "total_cost": total_material_cost,
            "quantity": quantity,
            "model_name": model_name
        }

    def preview_order_stock(
        self,
        requirements: List[Dict[str, Any]],
        current_inventory: List[StockItem]
    ) -> Dict[str, Any]:
        """
        Previsualización Inteligente: Compara los insumos requeridos con el stock real en fábrica
        y genera un semáforo (Verde / Amarillo / Rojo).
        """
        stock_map = {it.barcode.upper(): it for it in current_inventory}
        
        preview_rows = []
        has_critical_shortage = False
        missing_count = 0
        total_cost = 0.0

        for req in requirements:
            code = req["code"]
            req_qty = req["required_qty"]
            unit = req["unit"]
            price = req.get("unit_price", 0.0)
            total_cost += req.get("subtotal", req_qty * price)

            stock_item = stock_map.get(code)
            if stock_item:
                curr_stock = stock_item.current_stock
                min_stock = stock_item.min_stock
                desc = stock_item.description
                if not price and stock_item.unit_price:
                    price = stock_item.unit_price
            else:
                curr_stock = 0.0
                min_stock = 0.0
                desc = req["description"]

            remaining = curr_stock - req_qty
            
            # Semáforo de estado
            if curr_stock >= req_qty:
                if remaining < min_stock:
                    status = "WARNING"
                    status_label = "⚠️ Queda al límite"
                else:
                    status = "OK"
                    status_label = "✅ Stock suficiente"
            else:
                status = "CRITICAL"
                missing = req_qty - curr_stock
                status_label = f"❌ Faltante (-{missing:g} {unit})"
                has_critical_shortage = True
                missing_count += 1

            preview_rows.append({
                "Código": code,
                "Insumo": desc,
                "Requerido": req_qty,
                "Unidad": unit,
                "Stock Actual": curr_stock,
                "Quedará": max(0.0, remaining),
                "Estado": status_label,
                "_status_code": status,
                "Precio Unit.": price,
                "Subtotal": req_qty * price
            })

        return {
            "rows": preview_rows,
            "can_produce": not has_critical_shortage,
            "missing_count": missing_count,
            "total_cost": total_cost,
            "total_items": len(preview_rows)
        }

    def confirm_and_deduct_order(
        self,
        model_name: str,
        quantity: int,
        fabric_code: str,
        current_inventory: List[StockItem],
        tab_name: str,
        stock_service_instance,
        client_note: str = ""
    ) -> Tuple[bool, str, int]:
        """
        Confirma el pedido de fabricación y descuenta automáticamente cada insumo del stock
        en la pestaña semanal activa de Google Sheets.
        """
        requirements_data = self.calculate_order_requirements(model_name, quantity, fabric_code)
        req_items = requirements_data.get("items", [])
        if not req_items:
            return False, "No se encontraron insumos configurados para este modelo.", 0

        req_map = {r["code"]: r["required_qty"] for r in req_items}
        deducted_count = 0
        deducted_details = []

        # Descontar del inventario en memoria
        for it in current_inventory:
            if it.barcode.upper() in req_map:
                qty_to_deduct = req_map[it.barcode.upper()]
                old_cant_inv = it.cant_inventario
                # Descontar de Cant. Inventario (columna física)
                it.cant_inventario = max(0.0, it.cant_inventario - qty_to_deduct)
                it.current_stock = it.cant_inventario + it.compra_semana
                it.subtotal = it.current_stock * it.unit_price
                it.comprar = max(0.0, it.min_stock - it.current_stock)
                it.is_critical = it.current_stock <= it.min_stock
                deducted_count += 1
                deducted_details.append(f"{it.description}: -{qty_to_deduct:g} {it.unit}")

        if deducted_count == 0:
            return False, "Ninguno de los insumos requeridos coincide con los códigos del inventario activo.", 0

        # Guardar en Google Sheets de forma masiva
        try:
            stock_service_instance.save_bulk_from_editor(current_inventory, tab_name=tab_name)
        except Exception as e:
            return False, f"Error al guardar descuentos en Google Sheets: {e}", 0

        # Notificar a la sincronización en vivo para que celulares y PCs vean el nuevo stock
        try:
            sync_service.broadcast_saved(
                barcode="PEDIDO",
                product_name=f"Pedido: {quantity}x {model_name}",
                new_stock=float(deducted_count),
                tab_name=tab_name,
                source="Fabricación PC"
            )
        except Exception:
            pass

        # Registrar en historial local de pedidos
        order_record = {
            "timestamp": time.time(),
            "date_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model_name": model_name,
            "quantity": quantity,
            "fabric_code": fabric_code,
            "tab_name": tab_name,
            "client_note": client_note,
            "deducted_items_count": deducted_count,
            "total_cost": requirements_data.get("total_cost", 0.0),
            "details": deducted_details
        }
        self._record_order_history(order_record)

        # Enviar alerta a Telegram si está configurado
        try:
            if self.telegram.is_configured:
                msg = (
                    f"🏭 <b>Nuevo Pedido de Fabricación Confirmado</b>\n"
                    f"🛋️ <b>Modelo:</b> {quantity}x {model_name}\n"
                    f"🧵 <b>Tela:</b> {fabric_code}\n"
                    f"📅 <b>Pestaña Stock:</b> {tab_name}\n"
                    f"📦 <b>Insumos descontados:</b> {deducted_count} materiales\n"
                    f"💰 <b>Costo Estimado Materiales:</b> ${requirements_data.get('total_cost', 0):,.2f}"
                )
                self.telegram.send_alert(msg)
        except Exception:
            pass

        return True, f"¡Pedido confirmado exitosamente! Se descontaron {deducted_count} insumos del stock de '{tab_name}'.", deducted_count

    def _record_order_history(self, record: Dict[str, Any]):
        """Registra el pedido confirmado en orders_history.json."""
        history = []
        if ORDERS_HISTORY_FILE.exists():
            try:
                with open(ORDERS_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    if not isinstance(history, list):
                        history = []
            except Exception:
                history = []

        history.insert(0, record)
        history = history[:100]  # Guardar últimos 100 pedidos
        try:
            with open(ORDERS_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_orders_history(self) -> List[Dict[str, Any]]:
        """Obtiene el historial de pedidos de fabricación confirmados."""
        if ORDERS_HISTORY_FILE.exists():
            try:
                with open(ORDERS_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    def update_recipe_items(self, model_name: str, updated_items: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Permite editar cantidades requeridas o precios unitarios de un modelo
        y guarda los cambios en la hoja RECETAS de Google Sheets.
        """
        client = self.sheets._get_gspread_client()
        if not client:
            return False, "No se pudo conectar con Google Sheets para guardar los cambios."

        try:
            sheet = client.open_by_key(self.sheets.spreadsheet_id)
            ws = sheet.worksheet("RECETAS")

            updates = []
            for it in updated_items:
                row_idx = it.get("row_index")
                if row_idx and row_idx > 0:
                    new_qty = it.get("qty", 0.0)
                    new_price = it.get("unit_price", 0.0)
                    # Columna D: Cantidad Requerida, Columna F: Precio Unitario
                    updates.append({
                        "range": f"D{row_idx}",
                        "values": [[f"{new_qty:g}"]]
                    })
                    if new_price > 0:
                        updates.append({
                            "range": f"F{row_idx}",
                            "values": [[f"$ {new_price:,.2f}"]]
                        })

            if updates:
                ws.batch_update(updates)
                self.get_recipes(force_refresh=True)
                return True, f"Se actualizaron {len(updates)} valores en la hoja RECETAS exitosamente."
            return True, "No se detectaron modificaciones."
        except Exception as e:
            return False, f"Error actualizando la hoja RECETAS: {e}"

recipe_service = RecipeService()
