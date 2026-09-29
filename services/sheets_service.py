import io
import csv
import json
import time
import logging
import sys
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from config import settings
from models.schemas import StockItem, CategoryEnum

logger = logging.getLogger(__name__)

if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).parent
    try:
        LOCAL_DATA_DIR = exe_dir / "data"
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        LOCAL_DATA_DIR = Path(getattr(sys, '_MEIPASS', exe_dir)) / "data"
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
    meipass_data = Path(getattr(sys, '_MEIPASS', '')) / "data"
    if meipass_data.exists():
        for f in meipass_data.glob("*.json"):
            dest = LOCAL_DATA_DIR / f.name
            if not dest.exists():
                try:
                    shutil.copy2(f, dest)
                except Exception:
                    pass
else:
    LOCAL_DATA_DIR = Path(settings.GOOGLE_SERVICE_ACCOUNT_FILE).parent.parent / "data"

LOCAL_INVENTORY_FILE = LOCAL_DATA_DIR / "inventory.json"
LOCAL_ALIASES_FILE = LOCAL_DATA_DIR / "barcode_aliases.json"

# Caché global compartido a nivel de módulo entre ejecuciones de Streamlit
_GLOBAL_MEMORY_CACHE: Dict[str, List[StockItem]] = {}
_GLOBAL_AVAILABLE_TABS: List[str] = []
_GLOBAL_TABS_TIMESTAMP: float = 0.0
_GLOBAL_GSPREAD_CLIENT = None


class SheetsService:
    def __init__(self):
        self.spreadsheet_id = settings.SPREADSHEET_ID
        self.sheet_gid = settings.SHEET_GID
        self.service_account_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
        LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    def get_aliases(self) -> dict:
        """Devuelve diccionario de códigos de barra físicos mapeados a códigos de insumo."""
        if not LOCAL_ALIASES_FILE.exists():
            return {}
        try:
            with open(LOCAL_ALIASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def link_barcode_alias(self, scanned_code: str, target_barcode: str) -> None:
        """Asocia un código físico escaneado con un insumo de la planilla."""
        aliases = self.get_aliases()
        aliases[scanned_code.strip().upper()] = target_barcode.strip().upper()
        try:
            with open(LOCAL_ALIASES_FILE, "w", encoding="utf-8") as f:
                json.dump(aliases, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando alias de código de barras: {e}")

    def _get_gspread_client(self):
        """Inicializa el cliente de gspread reutilizando la instancia singleton."""
        global _GLOBAL_GSPREAD_CLIENT
        if _GLOBAL_GSPREAD_CLIENT is not None:
            return _GLOBAL_GSPREAD_CLIENT

        # 1. Intentar desde st.secrets (para Streamlit Community Cloud)
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                import gspread
                creds_dict = dict(st.secrets["gcp_service_account"])
                _GLOBAL_GSPREAD_CLIENT = gspread.service_account_from_dict(creds_dict)
                return _GLOBAL_GSPREAD_CLIENT
        except Exception as e:
            logger.warning(f"No se pudo inicializar gspread desde st.secrets: {e}")

        # 2. Intentar desde archivo local
        creds_path = Path(self.service_account_file)
        if creds_path.exists():
            try:
                import gspread
                _GLOBAL_GSPREAD_CLIENT = gspread.service_account(filename=str(creds_path))
                return _GLOBAL_GSPREAD_CLIENT
            except Exception as e:
                logger.warning(f"No se pudo inicializar gspread con Service Account: {e}")
        return None

    def _clean_number(self, value) -> float:
        """Limpia cadenas como '$ 1,980,683' o '190,000' para convertirlas en float."""
        if value is None:
            return 0.0
        val_str = str(value).strip().replace("$", "").replace(" ", "")
        if not val_str or val_str in ("#N/A", "N/A", "?", "-", "#DIV/0!", "None"):
            return 0.0
        try:
            if "," in val_str and "." in val_str:
                val_str = val_str.replace(",", "")
            elif "," in val_str:
                parts = val_str.split(",")
                if len(parts) == 2 and len(parts[1]) == 3 and int(parts[0]) > 0:
                    val_str = val_str.replace(",", "")
                else:
                    val_str = val_str.replace(",", ".")
            return float(val_str)
        except ValueError:
            return 0.0

    def categorize(self, barcode: str, description: str) -> str:
        """Determina la categoría del material según su código o descripción."""
        b = (barcode or "").upper()
        d = (description or "").upper()
        
        if b.startswith("MAD-") or "MADERA" in d or "TABLON" in d or "LISTON" in d:
            return CategoryEnum.MADERA.value
        elif b.startswith("TEL-") or "TELA" in d or "PANA" in d or "FRISELINA" in d or "CUERO" in d or "CHENILLE" in d:
            return CategoryEnum.TELAS.value
        elif b.startswith("POL-") or "POLIESTER" in d or "ESPUMA" in d or "BLOCK" in d:
            return CategoryEnum.POLIESTER.value
        elif b.startswith("REL-") or "GUATA" in d or "VELLON" in d or "COPOS" in d:
            return CategoryEnum.RELLENOS.value
        elif b.startswith("QUI-") or "FANA" in d or "PEGAMENTO" in d or "COLA" in d or "TINTA" in d:
            return CategoryEnum.QUIMICOS.value
        elif b.startswith("EMB-") or "STRECH" in d or "CINTA" in d or "CARTON" in d:
            return CategoryEnum.EMBALAJE.value
        elif b.startswith("COS-") or "HILO" in d or "ETIQUETA" in d or "CIERRE" in d:
            return CategoryEnum.COSTURA.value
        elif b.startswith("INS-") or b.startswith("TOR-") or "GRAMPA" in d or "TORNILLO" in d or "PATA" in d:
            return CategoryEnum.HERRAJES_INSUMOS.value
        return CategoryEnum.OTROS.value

    def get_category(self, barcode: str = "", description: str = "") -> str:
        """Alias compatible para categorize."""
        return self.categorize(barcode=barcode, description=description)

    def get_current_week_tab_name(self, date: Optional[datetime] = None) -> str:
        """Calcula el nombre de la pestaña semanal correspondiente al lunes de la semana (ej: STOCK_07.09.26)."""
        d = date or datetime.now()
        monday = d - timedelta(days=d.weekday())
        return f"STOCK_{monday.strftime('%d.%m.%y')}"

    def get_available_tabs(self, force_refresh: bool = False) -> List[str]:
        """Obtiene la lista de pestañas de stock disponibles con caché en memoria."""
        global _GLOBAL_AVAILABLE_TABS, _GLOBAL_TABS_TIMESTAMP
        current_tab = self.get_current_week_tab_name()
        now = time.time()

        # Cache de pestañas por 5 minutos para evitar consultas recurrentes
        if not force_refresh and _GLOBAL_AVAILABLE_TABS and (now - _GLOBAL_TABS_TIMESTAMP < 300):
            if current_tab not in _GLOBAL_AVAILABLE_TABS:
                _GLOBAL_AVAILABLE_TABS.insert(0, current_tab)
            return _GLOBAL_AVAILABLE_TABS

        client = self._get_gspread_client()
        if not client:
            _GLOBAL_AVAILABLE_TABS = [current_tab, "BASE"]
            return _GLOBAL_AVAILABLE_TABS

        try:
            sheet = client.open_by_key(self.spreadsheet_id)
            titles = [w.title for w in sheet.worksheets()]
            stock_tabs = [t for t in titles if t.startswith("STOCK_") or t == "BASE"]
            result = stock_tabs if stock_tabs else titles
            if current_tab not in result:
                result.insert(0, current_tab)
            _GLOBAL_AVAILABLE_TABS = result
            _GLOBAL_TABS_TIMESTAMP = now
            return _GLOBAL_AVAILABLE_TABS
        except Exception as e:
            logger.warning(f"Aviso consultando pestañas en Google Sheets: {e}")
            if _GLOBAL_AVAILABLE_TABS:
                return _GLOBAL_AVAILABLE_TABS
            return [current_tab, "BASE"]

    def get_or_create_weekly_worksheet(self, tab_name: Optional[str] = None):
        """
        Obtiene la pestaña semanal o la crea automáticamente duplicando 'BASE',
        limpiando la tabla de la izquierda (A4:B...) y reseteando las compras de la semana.
        """
        client = self._get_gspread_client()
        if not client:
            return None

        target_tab = tab_name or self.get_current_week_tab_name()
        
        try:
            sheet = client.open_by_key(self.spreadsheet_id)
            existing_tabs = {w.title: w for w in sheet.worksheets()}
            
            if target_tab in existing_tabs:
                return existing_tabs[target_tab]

            # Si no existe la pestaña de la nueva semana, la creamos duplicando 'BASE'
            base_ws = existing_tabs.get("BASE") or sheet.get_worksheet(0)
            logger.info(f"Creando nueva pestaña semanal para la nueva semana: {target_tab}")
            new_ws = sheet.duplicate_sheet(source_sheet_id=base_ws.id, new_sheet_name=target_tab)
            
            # Limpiar tabla de la izquierda (A4:B75) y Compra Semana (H4:H75), Observaciones (S4:S75)
            try:
                all_rows = new_ws.get_all_values()
                num_rows = len(all_rows)
                if num_rows >= 4:
                    empty_ab = [["", ""] for _ in range(4, num_rows + 1)]
                    new_ws.update(range_name=f"A4:B{num_rows}", values=empty_ab)
                    empty_h = [[""] for _ in range(4, num_rows + 1)]
                    new_ws.update(range_name=f"H4:H{num_rows}", values=empty_h)
                    empty_s = [[""] for _ in range(4, num_rows + 1)]
                    new_ws.update(range_name=f"S4:S{num_rows}", values=empty_s)
            except Exception as clean_err:
                logger.warning(f"Aviso limpiando tabla inicial de nueva pestaña: {clean_err}")

            global _GLOBAL_AVAILABLE_TABS
            if target_tab not in _GLOBAL_AVAILABLE_TABS:
                _GLOBAL_AVAILABLE_TABS.insert(0, target_tab)

            return new_ws
        except Exception as e:
            logger.error(f"Error obteniendo o creando pestaña semanal {target_tab}: {e}")
            return None

    def load_from_google_sheets(self, tab_name: Optional[str] = None, force_refresh: bool = False) -> List[StockItem]:
        """
        Descarga y parsea la planilla de la semana con memoria persistente ultra-rápida.
        Previene errores 429 de Google Sheets y 401 de endpoints no autenticados.
        """
        global _GLOBAL_MEMORY_CACHE
        target_tab = tab_name or self.get_current_week_tab_name()
        
        # 1. Si está en caché de memoria y no se fuerza refresco, devolver inmediatamente (0 llamadas a Google)
        if not force_refresh and target_tab in _GLOBAL_MEMORY_CACHE and _GLOBAL_MEMORY_CACHE[target_tab]:
            return _GLOBAL_MEMORY_CACHE[target_tab]

        # 2. Si no se fuerza refresco, intentar leer el archivo local JSON
        if not force_refresh:
            cached_local = self.load_local_inventory(tab_name=target_tab)
            if cached_local:
                _GLOBAL_MEMORY_CACHE[target_tab] = cached_local
                return cached_local

        client = self._get_gspread_client()
        rows = None

        if client:
            try:
                worksheet = self.get_or_create_weekly_worksheet(target_tab)
                if worksheet:
                    rows = worksheet.get_all_values()
            except Exception as e:
                logger.warning(f"Aviso en carga de Google Sheets ({target_tab}): {e}")

        # Si falló la consulta en vivo (por cuota o internet), recurrir al caché previo
        if not rows:
            if target_tab in _GLOBAL_MEMORY_CACHE and _GLOBAL_MEMORY_CACHE[target_tab]:
                return _GLOBAL_MEMORY_CACHE[target_tab]
            cached_local = self.load_local_inventory(tab_name=target_tab)
            if cached_local:
                _GLOBAL_MEMORY_CACHE[target_tab] = cached_local
                return cached_local
            cached_default = self.load_local_inventory()
            if cached_default:
                _GLOBAL_MEMORY_CACHE[target_tab] = cached_default
                return cached_default
            return []

        items: List[StockItem] = []
        if len(rows) < 4:
            if target_tab in _GLOBAL_MEMORY_CACHE:
                return _GLOBAL_MEMORY_CACHE[target_tab]
            return items

        # Inicia desde la fila 4 (índice 3), debajo de la fila de encabezados
        for row in rows[3:]:
            if len(row) < 6:
                continue

            barcode = row[4].strip() if len(row) > 4 else ""
            desc = row[5].strip() if len(row) > 5 else ""

            if not barcode or not desc or barcode == "#N/A" or barcode == "Codigo de Barras":
                continue

            cant_inv = self._clean_number(row[6] if len(row) > 6 else 0)
            compra_sem = self._clean_number(row[7] if len(row) > 7 else 0)
            
            # TOTAL INVENTARIO está en col 8 (índice 8)
            tot_inv = self._clean_number(row[8] if len(row) > 8 and row[8] != "" else cant_inv + compra_sem)
            cant_caja = row[9].strip() if len(row) > 9 and row[9] else "N/A"
            unit = row[13].strip() if len(row) > 13 and row[13] else "unidad"
            min_stock = self._clean_number(row[14] if len(row) > 14 and row[14] != "" else 0)
            if min_stock <= 0:
                min_stock = settings.STOCK_MINIMO_DEFAULT

            comprar = self._clean_number(row[15] if len(row) > 15 else 0)
            unit_price = self._clean_number(row[16] if len(row) > 16 else 0)
            subtotal = self._clean_number(row[17] if len(row) > 17 else (tot_inv * unit_price))
            notes = row[18].strip() if len(row) > 18 and row[18] else None

            is_critical = tot_inv <= min_stock

            items.append(
                StockItem(
                    barcode=barcode,
                    description=desc,
                    category=self.get_category(barcode=barcode, description=desc),
                    cant_inventario=cant_inv,
                    compra_semana=compra_sem,
                    current_stock=tot_inv,
                    cant_x_caja=cant_caja,
                    unit=unit,
                    min_stock=min_stock,
                    comprar=comprar,
                    unit_price=unit_price,
                    subtotal=subtotal,
                    notes=notes,
                    is_critical=is_critical,
                )
            )

        if items:
            _GLOBAL_MEMORY_CACHE[target_tab] = items
            self.save_local_inventory(items, tab_name=target_tab)

        return items

    def save_local_inventory(self, items: List[StockItem], tab_name: Optional[str] = None) -> None:
        """Guarda la lista de inventario en el archivo local JSON."""
        try:
            data = [item.model_dump() for item in items]
            file_to_save = LOCAL_DATA_DIR / f"inventory_{tab_name}.json" if tab_name else LOCAL_INVENTORY_FILE
            with open(file_to_save, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # Guardar también en el archivo default
            if tab_name:
                with open(LOCAL_INVENTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando inventario local: {e}")

    def load_local_inventory(self, tab_name: Optional[str] = None) -> Optional[List[StockItem]]:
        """Carga el inventario desde el archivo local si existe."""
        target_file = LOCAL_DATA_DIR / f"inventory_{tab_name}.json" if tab_name else LOCAL_INVENTORY_FILE
        if not target_file.exists():
            target_file = LOCAL_INVENTORY_FILE
        if not target_file.exists():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [StockItem(**item) for item in data]
        except Exception as e:
            logger.error(f"Error cargando inventario local: {e}")
            return None

    def get_all_items(self, force_refresh: bool = False, tab_name: Optional[str] = None) -> List[StockItem]:
        """Retorna la lista de ítems de la pestaña especificada o actual."""
        return self.load_from_google_sheets(tab_name=tab_name, force_refresh=force_refresh)

    def update_item_full_fields(
        self,
        barcode: str,
        cant_inventario: float,
        compra_semana: float,
        min_stock: float,
        unit_price: float,
        notes: Optional[str] = None,
        tab_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[StockItem]:
        """
        Actualiza todos los campos de Google Sheets de un insumo:
        - Cant. Inventario (G)
        - Compra Semana (H)
        - TOTAL INVENTARIO (I = G + H)
        - Stock Mínimo (O)
        - Comprar (P = max(0, O - I))
        - $ x Unidad (Q)
        - $ SubTotal (R = I * Q)
        - Observaciones (S)
        """
        global _GLOBAL_MEMORY_CACHE
        target_tab = tab_name or self.get_current_week_tab_name()
        items = self.load_from_google_sheets(tab_name=target_tab)
        
        b_clean = barcode.strip().upper()
        b_norm = b_clean.replace('/', '-').replace('_', '-').replace("'", '-').replace('"', '-').replace(' ', '-')
        b_alpha = "".join(c for c in b_clean if c.isalnum())
        desc_clean = (description or "").strip().lower()

        target = None
        # 1. Búsqueda exacta o normalizada
        for it in items:
            it_b = it.barcode.strip().upper()
            it_norm = it_b.replace('/', '-').replace('_', '-').replace("'", '-').replace('"', '-').replace(' ', '-')
            it_alpha = "".join(c for c in it_b if c.isalnum())
            if it_b == b_clean or it_norm == b_norm or (b_alpha and it_alpha == b_alpha):
                target = it
                break

        # 2. Búsqueda por descripción
        if not target and desc_clean:
            for it in items:
                if it.description.strip().lower() == desc_clean:
                    target = it
                    break

        # 3. Búsqueda por subcadena de código
        if not target:
            for it in items:
                if len(b_norm) >= 3 and (b_norm in it.barcode.upper() or it.barcode.upper() in b_norm):
                    target = it
                    break

        if not target:
            logger.warning(f"No se encontró target en memoria para barcode: {barcode}")
            return None

        total_inv = float(cant_inventario) + float(compra_semana)
        comprar = max(0.0, float(min_stock) - total_inv)
        subtotal = total_inv * float(unit_price)
        is_crit = total_inv <= float(min_stock)

        target.cant_inventario = float(cant_inventario)
        target.compra_semana = float(compra_semana)
        target.current_stock = total_inv
        target.min_stock = float(min_stock)
        target.comprar = comprar
        target.unit_price = float(unit_price)
        target.subtotal = subtotal
        target.notes = str(notes).strip() if notes else None
        target.is_critical = is_crit

        # Guardar de inmediato en memoria y disco local
        _GLOBAL_MEMORY_CACHE[target_tab] = items
        self.save_local_inventory(items, tab_name=target_tab)

        # Actualizar en Google Sheets en vivo
        self.update_full_fields_in_sheet(
            barcode=target.barcode,
            cant_inv=target.cant_inventario,
            compra_sem=target.compra_semana,
            tot_inv=total_inv,
            min_stock=target.min_stock,
            comprar=comprar,
            unit_price=target.unit_price,
            subtotal=subtotal,
            notes=target.notes,
            tab_name=target_tab,
            description=target.description,
        )

        return target

    def create_new_weekly_tab(self, tab_name: Optional[str] = None) -> str:
        """Crea explícitamente una nueva pestaña semanal limpia en Google Sheets."""
        global _GLOBAL_MEMORY_CACHE
        target_tab = tab_name or self.get_current_week_tab_name()
        ws = self.get_or_create_weekly_worksheet(target_tab)
        if target_tab in _GLOBAL_MEMORY_CACHE:
            del _GLOBAL_MEMORY_CACHE[target_tab]
        self.get_available_tabs(force_refresh=True)
        self.load_from_google_sheets(tab_name=target_tab, force_refresh=True)
        return ws.title if ws else target_tab

    def update_full_fields_in_sheet(
        self,
        barcode: str,
        cant_inv: float,
        compra_sem: float,
        tot_inv: float,
        min_stock: float,
        comprar: float,
        unit_price: float,
        subtotal: float,
        notes: Optional[str] = None,
        tab_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """
        Guarda el stock en la TABLA DE LA IZQUIERDA (Col A y B) y actualiza
        los campos en la TABLA DE LA DERECHA (Col E a S) en Google Sheets.
        """
        try:
            worksheet = self.get_or_create_weekly_worksheet(tab_name)
            if not worksheet:
                logger.error(f"No se pudo acceder a la pestaña '{tab_name}' en Google Sheets.")
                return False

            all_rows = worksheet.get_all_values()
            
            b_clean = str(barcode).strip().upper()
            b_norm = b_clean.replace('/', '-').replace('_', '-').replace("'", '-').replace('"', '-').replace(' ', '-')
            b_alpha = "".join(c for c in b_clean if c.isalnum())
            desc_clean = (description or "").strip().lower()

            # --- 1. LOCALIZAR FILA DEL PRODUCTO EN LA TABLA MAESTRA (DERECHA, Col E a S) ---
            target_right_row = None
            for idx, row in enumerate(all_rows, start=1):
                if len(row) > 4 and idx >= 4:
                    row_b = row[4].strip().upper()
                    row_b_norm = row_b.replace('/', '-').replace('_', '-').replace("'", '-').replace('"', '-').replace(' ', '-')
                    row_b_alpha = "".join(c for c in row_b if c.isalnum())
                    
                    if row_b and (row_b == b_clean or row_b_norm == b_norm or (b_alpha and row_b_alpha == b_alpha)):
                        target_right_row = idx
                        b_clean = row_b  # Usar el formato exacto de la planilla
                        break
                    
                    if desc_clean and len(row) > 5:
                        row_desc = row[5].strip().lower()
                        if row_desc and (row_desc == desc_clean or desc_clean in row_desc or row_desc in desc_clean):
                            target_right_row = idx
                            b_clean = row_b if row_b else b_clean
                            break

            # --- 2. REGISTRAR EL RECUENTO EN LA TABLA DE LA IZQUIERDA (Col A, B, C) ---
            left_row_idx = None
            first_empty_left_row = None

            for idx, row in enumerate(all_rows, start=1):
                if idx >= 4:
                    col_a = (row[0] if len(row) > 0 else "").strip().upper()
                    col_a_norm = col_a.replace('/', '-').replace('_', '-').replace("'", '-').replace('"', '-').replace(' ', '-')
                    col_a_alpha = "".join(c for c in col_a if c.isalnum())

                    if col_a and (col_a == b_clean or col_a_norm == b_norm or (b_alpha and col_a_alpha == b_alpha)):
                        left_row_idx = idx
                        break
                    
                    if not col_a and first_empty_left_row is None:
                        first_empty_left_row = idx

            # Obtener descripción legible del producto
            prod_desc = description
            if not prod_desc and target_right_row and target_right_row <= len(all_rows):
                prod_desc = all_rows[target_right_row - 1][5] if len(all_rows[target_right_row - 1]) > 5 else ""

            target_left_row = left_row_idx or first_empty_left_row or (len(all_rows) + 1)
            
            try:
                # Escribir en la tabla izquierda: Col A (Código), Col B (Cantidad contada), Col C (Fórmula VLOOKUP)
                c_formula = f'=IF(A{target_left_row}="","",IFERROR(VLOOKUP(A{target_left_row},E:F,2,FALSE),"No encontrado"))'
                worksheet.update(
                    range_name=f"A{target_left_row}:C{target_left_row}",
                    values=[[b_clean, cant_inv, c_formula]],
                    value_input_option="USER_ENTERED"
                )
            except Exception as e_left:
                logger.warning(f"Aviso actualizando tabla izquierda A{target_left_row}: {e_left}")

            # --- 3. ACTUALIZAR CAMPOS EN LA TABLA DE LA DERECHA (Col H, O, P, Q, R, S) ---
            if target_right_row:
                r = target_right_row
                try:
                    # Actualizar Compra Semana (H), Stock Min (O), $ Unit (Q), Notas (S)
                    worksheet.update(range_name=f"H{r}", values=[[compra_sem if compra_sem > 0 else ""]])
                    worksheet.update(range_name=f"O{r}", values=[[min_stock]])
                    worksheet.update(range_name=f"Q{r}", values=[[unit_price]])
                    worksheet.update(range_name=f"S{r}", values=[[notes or ""]])
                    
                    # Si Col G no tiene fórmula SUMIF, restaurarla automáticamente
                    row_vals = all_rows[r - 1] if r <= len(all_rows) else []
                    col_g_val = row_vals[6] if len(row_vals) > 6 else ""
                    if not str(col_g_val).startswith("="):
                        worksheet.update(range_name=f"G{r}", values=[[f"=SUMIF(A:A,E{r},B:B)"]], value_input_option="USER_ENTERED")
                except Exception as e_right:
                    logger.warning(f"Aviso actualizando tabla derecha fila {r}: {e_right}")

            logger.info(f"Google Sheets ({worksheet.title}) actualizado: Izquierda fila {target_left_row}, Derecha fila {target_right_row}.")
            return True
        except Exception as e:
            logger.error(f"Error actualizando campos en Google Sheets: {e}")
            raise e

    def update_single_item_stock(
        self,
        barcode: str,
        new_quantity: float,
        mode: str = "SET",
        notes: Optional[str] = None,
        tab_name: Optional[str] = None,
    ) -> Optional[StockItem]:
        """Actualiza el stock rápido de un producto escaneado."""
        target_tab = tab_name or self.get_current_week_tab_name()
        items = self.load_from_google_sheets(tab_name=target_tab)
        b_clean = barcode.strip().upper()
        
        target = None
        for it in items:
            if it.barcode.strip().upper() == b_clean:
                target = it
                break

        if not target:
            return None

        if mode == "ADD":
            cant_inv = target.cant_inventario
            compra_sem = target.compra_semana + new_quantity
        elif mode == "SUB":
            cant_inv = max(0.0, target.cant_inventario - new_quantity)
            compra_sem = target.compra_semana
        else:  # SET
            cant_inv = max(0.0, new_quantity)
            compra_sem = target.compra_semana

        return self.update_item_full_fields(
            barcode=barcode,
            cant_inventario=cant_inv,
            compra_semana=compra_sem,
            min_stock=target.min_stock,
            unit_price=target.unit_price,
            notes=notes if notes else target.notes,
            tab_name=tab_name,
        )

    def update_bulk_in_sheet(self, items: List[StockItem], tab_name: Optional[str] = None) -> bool:
        """Actualiza múltiples productos en lote en la pestaña semanal en Google Sheets."""
        try:
            worksheet = self.get_or_create_weekly_worksheet(tab_name)
            if not worksheet:
                return False
            
            # Mapear códigos a filas
            all_col5 = worksheet.col_values(5)
            code_to_row = {}
            for row_idx, val in enumerate(all_col5, start=1):
                clean_val = val.strip().upper()
                if clean_val:
                    code_to_row[clean_val] = row_idx

            for it in items:
                b_code = it.barcode.strip().upper()
                if b_code in code_to_row:
                    r = code_to_row[b_code]
                    worksheet.update_cell(r, 7, it.cant_inventario)
                    worksheet.update_cell(r, 8, it.compra_semana)
                    worksheet.update_cell(r, 9, it.current_stock)
                    worksheet.update_cell(r, 15, it.min_stock)
                    worksheet.update_cell(r, 16, it.comprar)
                    worksheet.update_cell(r, 17, it.unit_price)
                    worksheet.update_cell(r, 18, it.subtotal)
                    if it.notes:
                        worksheet.update_cell(r, 19, it.notes)
            return True
        except Exception as e:
            logger.error(f"Error en sincronización en lote a Google Sheets: {e}")
            return False
