import sys
import re
from services.sheets_service import SheetsService
import parse_costos

sys.stdout.reconfigure(encoding='utf-8')

# Component to barcode mapping
COMPONENT_MAP = {
    'Grampa 84/12': ('INS-GRA-8411', 'grampas 8411', 'unidad', 2.02),
    'Grampa 90/40': ('INS-GRA-9040', 'grampas 9040', 'unidad', 5.05),
    'Tornillo p/madera 75': ('TOR-FIX-075', 'tornillo 75', 'unidad', 81.03),
    'Tornillo p/madera 45': ('TOR-FIX-045', 'tornillo 45', 'unidad', 48.22),
    'Tornillo p/madera 25': ('TOR-FIX-025', 'tornillo 25', 'unidad', 29.77),
    'Cierre Reforzado x mts': ('INS-CIE-001', 'cierre', 'metro', 336.00),
    'Friselina de 1,5 mts 45gr': ('TEL-FRI-001', 'friselina', 'metro', 703.00),
    'Block Poliester x kg': ('POL-03CM-002', 'Poliester 3 cm celeste', 'kg', 17700.00),
    'Cortes Poliester  x Kg': ('POL-COR-001', 'cortes poliester CONRAD', 'kg', 24300.00),
    'Tela Alpha': ('TEL-ALP-001', 'tela alpha', 'metro', 4666.00),
    'Tela Pana Riff': ('TEL-PAN-RIF', 'tela pana riff', 'metro', 4115.00),
    'Tela Cuerotex': ('TEL-CTX-001', 'Tela Cuerotex', 'metro', 10000.00),
    'Tela Eco Cuero': ('TEL-ECO-CUE', 'Tela Eco Cuero', 'metro', 5100.00),
    'Tela Pana Jaguar': ('TEL-PAN-JAG', 'Tela Pana Jaguar', 'metro', 7298.00),
    'M2_Madera terceada': ('PLA-TER-M2', 'M2 Terciado', 'm2', 3936.00),
    'Madera terceada_MP': ('PLA-TER-M2', 'M2 Terciado', 'm2', 3936.00),
    'PIE_Madera 1"': ('MAD-10X6-001', 'madera 1 x 6  (3.05mts)', 'pie', 1089.00),
    'PIE_Madera 1,5"': ('MAD-15X6-001', 'madera 1,5 x 6  (3.05 mts)', 'pie', 1089.00),
    'PIE_Madera 3/4"': ('MAD-34X6-002', 'madera 3/4  x 6 (3,7 mts)', 'pie', 1089.00),
    'Pino s/natural en bruto 3/4 x 6 x 3,05 mts_MP': ('MAD-34X6-001', 'madera 3/4 x 6  (3.05 mts)', 'pie', 2819.30),
    'Madera Ferreryra _MP': ('MAD-3434-LIS', 'Listones 3/4 x 3/4  (3.05 mts)', 'pie', 1089.00),
    'Plastillera': ('EMB-PLA-001', 'plastillera', 'metro', 1079.00),
    'Deslizador _MP': ('INS-DES-001', 'deslizadores', 'unidad', 102.08),
    'Pata Plástica': ('INS-PAT-PLA', 'Pata Plástica', 'unidad', 125.00),
    'Patas Madera': ('INS-PAT-MAD', 'Patas Madera', 'unidad', 2450.25),
    'Pata Fundición': ('INS-PAT-FUN', 'Pata Fundición', 'unidad', 3499.00),
    'Rueda Carro': ('INS-RUE-CAR', 'Rueda Carro', 'unidad', 1242.67),
    'Bisagras': ('INS-BIS-001', 'bisagras', 'unidad', 44.77),
    'Bulón': ('INS-BUL-516', 'bulones 5/16', 'unidad', 171.82),
    'Tuercas': ('INS-TUE-001', 'Tuercas', 'unidad', 36.30),
    'Hormillas': ('INS-HOR-001', 'Hormillas', 'unidad', 74.45),
    'Regaton 130x130x5_MP': ('INS-REG-001', 'regatones', 'unidad', 124.00),
    'Guata x mts': ('REL-GUA-001', 'Guata x mts', 'metro', 2057.73),
    'Vellon x Kg': ('REL-VEL-001', 'Vellon x Kg', 'kg', 8436.90),
    'Copos x Kg / Scrap': ('REL-COP-001', 'Copos X kg', 'kg', 2990.00),
    'Embalaje': ('EMB-GEN-001', 'embalaje', 'metro', 0.00),
    'Parrilla': ('INS-PAR-001', 'Parrilla', 'unidad', 44770.00),
    'Hilo 40gr NEGRO': ('COS-HIL-NEG', 'hilo negro', 'unidad', 33.60),
    'Almohadones x Kg _MP': ('POL-COR-001', 'cortes poliester CONRAD', 'kg', 24300.00),
    'Banqueton 71x 71 - Alpha': ('SUB-BAN-71A', 'Banquetón 71x71 Alpha', 'unidad', 56191.55),
    'Sillon Recto 1,90 brz15 Alpha': ('SUB-REC-19A', 'Sillón Recto 1.90 brz15 Alpha', 'unidad', 230296.28),
}

def parse_qty(qty_str):
    if not qty_str:
        return 0.0
    val = str(qty_str).replace(' ', '').strip()
    val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except:
        return 0.0

def build_all():
    service = SheetsService()
    gc = service._get_gspread_client()
    sh = gc.open_by_key(service.spreadsheet_id)
    ws = sh.worksheet('RECETAS')

    # Ensure sheet has enough rows and cols
    ws.resize(rows=1200, cols=10)
    ws.clear()

    # Organize sections
    all_sections = parse_costos.sections
    
    # 1. Put Conrad first
    conrad_sec = None
    other_sections = []
    
    for s in all_sections:
        if 'conrad' in s['title'].lower() and 'alpha' in s['title'].lower():
            conrad_sec = s
        else:
            other_sections.append(s)

    # Filter other sections: all Alpha + unique other models
    selected_others = []
    seen_bases = set(['conrad'])
    
    # All alpha models
    for s in other_sections:
        title = s['title']
        if 'alpha' in title.lower():
            selected_others.append(s)
            base = re.sub(r'[\s\-_]*alpha[\s\-_]*', '', title, flags=re.IGNORECASE).strip()
            seen_bases.add(base.lower())
            
    # Other unique models not in alpha
    for s in other_sections:
        title = s['title']
        base = re.sub(r'[\s\-_]*(alpha|pana riff|pana jaguar/ cuero tex|pana jaguar / cuero tex|cuero tex|eco cuero)[\s\-_]*', '', title, flags=re.IGNORECASE).strip()
        if base.lower() not in seen_bases:
            selected_others.append(s)
            seen_bases.add(base.lower())

    models_to_build = []
    if conrad_sec:
        models_to_build.append(conrad_sec)
    models_to_build.extend(selected_others)

    print(f"Total models to build: {len(models_to_build)}")

    rows = []
    merges = []
    model_header_rows = []
    table_header_rows = []
    subtotal_rows = []
    item_row_ranges = []

    # Banner
    rows.append([
        "BUENA MADERA • ESCANDALLO DE COSTOS Y RECETARIO DE PRODUCCIÓN",
        "", "", "", "", "", ""
    ])
    merges.append((0, 1, 0, 7))

    rows.append([
        "Consumo estándar de insumos por modelo con precios actualizados (+21% IVA). Los precios se sincronizan con la hoja 'BASE' y se pueden editar manualmente.",
        "", "", "", "", "", ""
    ])
    merges.append((1, 2, 0, 7))

    rows.append(["", "", "", "", "", "", ""])

    for s_idx, model in enumerate(models_to_build):
        is_conrad = 'conrad' in model['title'].lower()
        title = model['title'].upper()
        if not title.startswith("MODELO:"):
            title = f"MODELO: {title}"

        # Model title row
        row_num = len(rows) + 1
        rows.append([f"🛋️ {title}", "", "", "", "", "", ""])
        merges.append((row_num - 1, row_num, 0, 7))
        model_header_rows.append(row_num)

        # Table header row
        row_num = len(rows) + 1
        rows.append([
            "Modelo",
            "Código Insumo",
            "Descripción Insumo (BASE)",
            "Cantidad Requerida",
            "Unidad",
            "Precio Unitario ($)",
            "Subtotal Insumo ($)"
        ])
        table_header_rows.append(row_num)

        # Filter items (skip 0-cost labor placeholders)
        valid_items = []
        for it in model['items']:
            comp = it['component'].strip()
            if 'mano obra' in comp.lower() or 'mano de obra' in comp.lower() or 'm.o.' in comp.lower():
                continue
            qty = parse_qty(it['qty_str'])
            if qty <= 0 and comp != 'Embalaje':
                continue
            valid_items.append((comp, qty))

        # Add items
        start_item_row = len(rows) + 1
        clean_model_name = model['title'].replace(" - Alpha", "").replace("_Alpha", "").replace(" Alpha", "").strip()

        for comp, qty in valid_items:
            r_idx = len(rows) + 1
            code_info = COMPONENT_MAP.get(comp)
            if code_info:
                barcode, fallback_desc, fallback_unit, fallback_price = code_info
            else:
                barcode = "INS-VAR-001"
                fallback_desc = comp
                fallback_unit = "unidad"
                fallback_price = 0.0

            # Special case for embalaje if qty is 0, give standard 3 mts for armchairs
            if comp == 'Embalaje' and qty == 0:
                qty = 3.0

            desc_formula = f'=IFERROR(VLOOKUP(B{r_idx}, BASE!$E:$F, 2, FALSE), "{fallback_desc}")'
            unit_formula = f'=IFERROR(VLOOKUP(B{r_idx}, BASE!$E:$N, 10, FALSE), "{fallback_unit}")'
            price_formula = f'=IFERROR(VLOOKUP(B{r_idx}, BASE!$E:$Q, 13, FALSE), {fallback_price})'
            subtotal_formula = f'=D{r_idx}*F{r_idx}'

            rows.append([
                clean_model_name,
                barcode,
                desc_formula,
                qty,
                unit_formula,
                price_formula,
                subtotal_formula
            ])

        end_item_row = len(rows)
        item_row_ranges.append((start_item_row, end_item_row))

        # Subtotal row
        subtotal_row = len(rows) + 1
        subtotal_label = f"TOTAL MATERIALES ({clean_model_name}):"
        rows.append([
            subtotal_label,
            "", "", "", "", "",
            f"=SUM(G{start_item_row}:G{end_item_row})"
        ])
        merges.append((subtotal_row - 1, subtotal_row, 0, 6))
        subtotal_rows.append(subtotal_row)

        # If Conrad, append custom fabric and labor sections
        if is_conrad:
            # Row: Blank
            rows.append(["", "", "", "", "", "", ""])

            # Insumo a Pedido Header
            r_amber = len(rows) + 1
            rows.append(["📦 INSUMO A PEDIDO (Variable según cliente)", "", "", "", "", "", ""])
            merges.append((r_amber - 1, r_amber, 0, 7))

            # Insumo a Pedido Data
            r_fabric = len(rows) + 1
            rows.append([
                "Tela tapicería (A pedido)",
                "A PEDIDO",
                "Pana, Chenille, Eco-cuero u otra elegida por cliente",
                3.5,
                "metros",
                4666.0, # Precio Tela Alpha con IVA
                f"=D{r_fabric}*F{r_fabric}"
            ])

            # Insumo a Pedido Note
            r_note = len(rows) + 1
            rows.append([
                "Nota: Como la tela no tiene stock fijo y se compra según lo que elija el cliente, por ejemplo Pana, Chenille o Eco-cuero, se multiplica 3.5 mts × Precio de la tela elegida.",
                "", "", "", "", "", ""
            ])
            merges.append((r_note - 1, r_note, 0, 7))

            # Total Conrad Materiales
            r_tot_mat = len(rows) + 1
            rows.append([
                "TOTAL MATERIALES SILLÓN CONRAD (Fábrica + Tela):",
                "", "", "", "", "",
                f"=G{subtotal_row}+G{r_fabric}"
            ])
            merges.append((r_tot_mat - 1, r_tot_mat, 0, 6))

            # Blank
            rows.append(["", "", "", "", "", "", ""])

            # Mano de Obra Header
            r_mo_head = len(rows) + 1
            rows.append(["⏱️ TIEMPOS ESTIMADOS DE MANO DE OBRA (Fabricación)", "", "", "", "", "", ""])
            merges.append((r_mo_head - 1, r_mo_head, 0, 7))

            r_carp = len(rows) + 1
            rows.append(["Mano de obra Carpintería", "MO-CARP", "Estructura de madera, corte, armado de esqueleto", 1.0, "hora (60 min)", 8265.0, f"=D{r_carp}*F{r_carp}"])
            r_tapi = len(rows) + 1
            rows.append(["Mano de obra Tapicería", "MO-TAPI", "Encinchado, pegado de espuma, tapizado final", 0.75, "hora (45 min)", 8852.25, f"=D{r_tapi}*F{r_tapi}"])
            r_cost = len(rows) + 1
            rows.append(["Mano de obra Costureras", "MO-COST", "Corte de patrones de tela, costura de fundas y cierres", 0.50, "hora (30 min)", 8265.0, f"=D{r_cost}*F{r_cost}"])

            r_mo_tot = len(rows) + 1
            rows.append([
                "TOTAL TIEMPO DE FABRICACIÓN:",
                "2 hs 15 min",
                "2.25 horas hombre totales por sillón",
                2.25,
                "horas",
                "SUBTOTAL M.O.:",
                f"=SUM(G{r_carp}:G{r_cost})"
            ])
            merges.append((r_mo_tot - 1, r_mo_tot, 4, 6))

            rows.append(["", "", "", "", "", "", ""])

            r_gran_tot = len(rows) + 1
            rows.append([
                "🏁 COSTO TOTAL ESTIMADO DE PRODUCCIÓN (Materiales + Mano de Obra):",
                "", "", "", "", "",
                f"=G{r_tot_mat}+G{r_mo_tot}"
            ])
            merges.append((r_gran_tot - 1, r_gran_tot, 0, 6))

        # Blank space between models
        rows.append(["", "", "", "", "", "", ""])

    print(f"Generated {len(rows)} rows for RECETAS.")

    # Write all rows
    ws.update(values=rows, range_name=f'A1:G{len(rows)}', value_input_option='USER_ENTERED')
    print("Cells updated in Google Sheets!")

    # Format sheet
    sheet_id = ws.id
    requests = []

    # 1. Column widths
    col_widths = [200, 140, 280, 140, 110, 150, 160]
    for idx, width in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": idx,
                    "endIndex": idx + 1
                },
                "properties": {
                    "pixelSize": width
                },
                "fields": "pixelSize"
            }
        })

    # Unmerge all existing cells first to avoid merge collision
    requests.append({
        "unmergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1200,
                "startColumnIndex": 0,
                "endColumnIndex": 10
            }
        }
    })

    # 2. Merges
    for r_start, r_end, c_start, c_end in merges:
        requests.append({
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r_start,
                    "endRowIndex": r_end,
                    "startColumnIndex": c_start,
                    "endColumnIndex": c_end
                },
                "mergeType": "MERGE_ALL"
            }
        })

    # 3. Add styling requests to single batch
    # Row 1 banner: Navy Blue
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": 7
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.08, "green": 0.13, "blue": 0.24},
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 13},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # Row 2 subtitle
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 2,
                "startColumnIndex": 0,
                "endColumnIndex": 7
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.94, "green": 0.96, "blue": 0.98},
                    "textFormat": {"foregroundColor": {"red": 0.25, "green": 0.35, "blue": 0.45}, "italic": True, "fontSize": 9},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # Model headers
    for r in model_header_rows:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r - 1,
                    "endRowIndex": r,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.12, "green": 0.35, "blue": 0.75},
                        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

    # Table headers
    for r in table_header_rows:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r - 1,
                    "endRowIndex": r,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.88, "green": 0.91, "blue": 0.95},
                        "textFormat": {"foregroundColor": {"red": 0.1, "green": 0.15, "blue": 0.25}, "bold": True, "fontSize": 10},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

    # Number formats across columns
    total_len = len(rows)
    # Col B: Mono font, center
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": total_len,
                "startColumnIndex": 1,
                "endColumnIndex": 2
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "CENTER",
                    "textFormat": {"fontFamily": "Roboto Mono", "fontSize": 9}
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,textFormat)"
        }
    })

    # Col D: Quantity format #,##0.00
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": total_len,
                "startColumnIndex": 3,
                "endColumnIndex": 4
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "RIGHT",
                    "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Col E: Unit center
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": total_len,
                "startColumnIndex": 4,
                "endColumnIndex": 5
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment)"
        }
    })

    # Col F: Price format
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": total_len,
                "startColumnIndex": 5,
                "endColumnIndex": 6
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "RIGHT",
                    "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Col G: Subtotal format
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 5,
                "endRowIndex": total_len,
                "startColumnIndex": 6,
                "endColumnIndex": 7
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "RIGHT",
                    "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Subtotals styling
    for r in subtotal_rows:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r - 1,
                    "endRowIndex": r,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.95, "green": 0.97, "blue": 1.0},
                        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 0.05, "green": 0.2, "blue": 0.5}},
                        "horizontalAlignment": "RIGHT"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        })

    # Freeze top 5 rows
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": 5
                }
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    print(f"Sending {len(requests)} batch requests (dimensions, merges, styling, freeze)...")
    sh.batch_update({"requests": requests})
    print("Formatting and freeze completed successfully in ONE single batchUpdate call!")

if __name__ == '__main__':
    build_all()
