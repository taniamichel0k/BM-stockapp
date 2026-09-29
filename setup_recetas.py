import gspread
from services.sheets_service import SheetsService

def main():
    service = SheetsService()
    gc = service._get_gspread_client()
    sh = gc.open_by_key(service.spreadsheet_id)
    ws = sh.worksheet('RECETAS')

    # Clear previous contents to start fresh and clean
    ws.clear()

    rows = []

    # Row 1: Main Banner
    rows.append([
        "BUENA MADERA • ESCANDALLO DE COSTOS Y RECETARIO DE PRODUCCIÓN",
        "", "", "", "", "", ""
    ])

    # Row 2: Subtitle
    rows.append([
        "Consumo estándar de insumos por modelo. Los precios unitarios se sincronizan con la hoja 'BASE' y se pueden actualizar cuando sea necesario.",
        "", "", "", "", "", ""
    ])

    # Row 3: Blank
    rows.append(["", "", "", "", "", "", ""])

    # Row 4: Model Title
    rows.append([
        "🛋️ RECETA: SILLÓN CONRAD",
        "", "", "", "", "", ""
    ])

    # Row 5: Column Headers
    rows.append([
        "Modelo",
        "Código Insumo",
        "Descripción Insumo (BASE)",
        "Cantidad Requerida",
        "Unidad",
        "Precio Unitario ($)",
        "Subtotal Insumo ($)"
    ])

    # Rows 6-19: 14 Insumos Fijos de Fábrica
    items = [
        # (Row, Code, Qty, Note / Fallback Desc, Fallback Unit, Fallback Price)
        (6,  "MAD-15X6-001", 12.0, "Madera 1,5\" x 6 (12 pies)"),
        (7,  "MAD-34X6-002", 1.0,  "Madera 3/4\" x 6 (1 pie)"),
        (8,  "PLA-TER-M2",   0.25, "Madera terciada x M2 (0.25 m2)"),
        (9,  "INS-GRA-8411", 875,  "Grampas 84/11 (7 tiras x 125 u)"),
        (10, "INS-GRA-9040", 200,  "Grampas 90/40 (2 tiras x 100 u)"),
        (11, "TOR-FIX-075",  4,    "Tornillo para madera de 75"),
        (12, "INS-CIE-001",  0.70, "Cierre reforzado (70 cm)"),
        (13, "TEL-FRI-001",  0.50, "Friselina 1.5 mts (50 cm)"),
        (14, "POL-01CM-001", 0.210,"Poliéster 1 cm (210 gr)"),
        (15, "POL-03CM-002", 0.790,"Poliéster 3 cm (790 gr)"),
        (16, "POL-COR-001",  0.800,"Cortes poliéster CONRAD (800 gr)"),
        (17, "INS-DES-001",  1,    "Deslizador"),
        (18, "EMB-PLA-001",  1.50, "Plastillera (1.50 mts)"),
        (19, "EMB-GEN-001",  3.00, "Embalaje (3 mts)"),
    ]

    for r_idx, code, qty, note in items:
        row_num = r_idx
        desc_formula = f'=IFERROR(VLOOKUP(B{row_num}, BASE!$E:$F, 2, FALSE), "")'
        unit_formula = f'=IFERROR(VLOOKUP(B{row_num}, BASE!$E:$N, 10, FALSE), "")'
        price_formula = f'=IFERROR(VLOOKUP(B{row_num}, BASE!$E:$Q, 13, FALSE), 0)'
        subtotal_formula = f'=D{row_num}*F{row_num}'
        rows.append([
            "Sillón Conrad",
            code,
            desc_formula,
            qty,
            unit_formula,
            price_formula,
            subtotal_formula
        ])

    # Row 20: Subtotal Materiales Base
    rows.append([
        "SUBTOTAL MATERIALES BASE (Insumos fijos de fábrica):",
        "", "", "", "", "",
        "=SUM(G6:G19)"
    ])

    # Row 21: Blank
    rows.append(["", "", "", "", "", "", ""])

    # Row 22: Header Insumo a Pedido
    rows.append([
        "📦 INSUMO A PEDIDO (Variable según cliente)",
        "", "", "", "", "", ""
    ])

    # Row 23: Data Insumo a Pedido
    # Tela: 3.5 metros (se multiplica 3.5 mts * Precio de la tela elegida)
    rows.append([
        "Tela tapicería (A pedido)",
        "A PEDIDO",
        "Pana, Chenille, Eco-cuero u otra elegida por cliente",
        3.5,
        "metros",
        12000, # Precio estimado por metro que el usuario puede editar libremente
        "=D23*F23"
    ])

    # Row 24: Note explaining calculation
    rows.append([
        "Nota: Como la tela no tiene stock fijo y se compra según lo que elija el cliente, por ejemplo Pana, Chenille o Eco-cuero, se multiplica 3.5 mts × Precio de la tela elegida.",
        "", "", "", "", "", ""
    ])

    # Row 25: Total Materiales Fijos + Tela
    rows.append([
        "TOTAL MATERIALES SILLÓN CONRAD (Fábrica + Tela estimada):",
        "", "", "", "", "",
        "=G20+G23"
    ])

    # Row 26: Blank
    rows.append(["", "", "", "", "", "", ""])

    # Row 27: Header Mano de Obra
    rows.append([
        "⏱️ TIEMPOS ESTIMADOS DE MANO DE OBRA (Fabricación)",
        "", "", "", "", "", ""
    ])

    # Row 28: Carpintería
    rows.append([
        "Mano de obra Carpintería",
        "MO-CARP",
        "Estructura de madera, corte, armado de esqueleto",
        1.0,
        "hora (60 min)",
        0, # Costo x hora a definir si quieren
        "=D28*F28"
    ])

    # Row 29: Tapicería
    rows.append([
        "Mano de obra Tapicería",
        "MO-TAPI",
        "Encinchado, pegado de espuma, tapizado final",
        0.75,
        "hora (45 min)",
        0,
        "=D29*F29"
    ])

    # Row 30: Costureras
    rows.append([
        "Mano de obra Costureras",
        "MO-COST",
        "Corte de patrones de tela, costura de fundas y cierres",
        0.50,
        "hora (30 min)",
        0,
        "=D30*F30"
    ])

    # Row 31: Total Mano de Obra
    rows.append([
        "TOTAL TIEMPO DE FABRICACIÓN:",
        "2 hs 15 min",
        "2.25 horas hombre totales por sillón",
        2.25,
        "horas",
        "SUBTOTAL M.O.:",
        "=SUM(G28:G30)"
    ])

    # Row 32: Blank
    rows.append(["", "", "", "", "", "", ""])

    # Row 33: Gran Total Costo de Fabricación
    rows.append([
        "🏁 COSTO TOTAL ESTIMADO DE PRODUCCIÓN (Materiales + Mano de Obra):",
        "", "", "", "", "",
        "=G25+G31"
    ])

    # Row 34: Blank
    rows.append(["", "", "", "", "", "", ""])

    # Row 35: Guide note on updating prices
    rows.append([
        "💡 ¿CÓMO ACTUALIZAR PRECIOS? 1) En la hoja 'BASE', modificá la columna '$ x Unidad' con los precios actualizados de proveedores; todas las recetas se actualizarán automáticamente. 2) O escribí directamente un nuevo valor sobre la columna F si querés fijar un precio manual en esta receta.",
        "", "", "", "", "", ""
    ])

    # Write all rows at once
    ws.update(values=rows, range_name=f'A1:G{len(rows)}', value_input_option='USER_ENTERED')
    print(f"Data and formulas written successfully! Total rows: {len(rows)}")

    # Formatting using Google Sheets API batchUpdate
    sheet_id = ws.id
    requests = []

    # 1. Column widths
    col_widths = [180, 140, 280, 140, 110, 150, 160]
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

    # 2. Merges
    merges = [
        (0, 1, 0, 7),   # Row 1 (A1:G1)
        (1, 2, 0, 7),   # Row 2 (A2:G2)
        (3, 4, 0, 7),   # Row 4 (A4:G4)
        (19, 20, 0, 6), # Row 20 (A20:F20)
        (21, 22, 0, 7), # Row 22 (A22:G22)
        (23, 24, 0, 7), # Row 24 (A24:G24)
        (24, 25, 0, 6), # Row 25 (A25:F25)
        (26, 27, 0, 7), # Row 27 (A27:G27)
        (32, 33, 0, 6), # Row 33 (A33:F33)
        (34, 35, 0, 7), # Row 35 (A35:G35)
    ]
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

    # Execute dimension updates and merges first
    sh.batch_update({"requests": requests})
    print("Column widths and cell merges applied.")

    # 3. Apply formatting styles
    # Row 1 banner: Navy Blue, White bold text, centered
    ws.format("A1:G1", {
        "backgroundColor": {"red": 0.08, "green": 0.13, "blue": 0.24}, # #14213d
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 13},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })

    # Row 2 subtitle
    ws.format("A2:G2", {
        "backgroundColor": {"red": 0.94, "green": 0.96, "blue": 0.98},
        "textFormat": {"foregroundColor": {"red": 0.25, "green": 0.35, "blue": 0.45}, "italic": True, "fontSize": 9},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })

    # Row 4 Model Header
    ws.format("A4:G4", {
        "backgroundColor": {"red": 0.12, "green": 0.35, "blue": 0.75}, # Royal Blue
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 12},
        "horizontalAlignment": "LEFT",
        "verticalAlignment": "MIDDLE"
    })

    # Row 5 Table Headers
    ws.format("A5:G5", {
        "backgroundColor": {"red": 0.88, "green": 0.91, "blue": 0.95},
        "textFormat": {"foregroundColor": {"red": 0.1, "green": 0.15, "blue": 0.25}, "bold": True, "fontSize": 10},
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE"
    })

    # Rows 6-19 Table Data
    ws.format("A6:A19", {"horizontalAlignment": "LEFT"})
    ws.format("B6:B19", {"horizontalAlignment": "CENTER", "textFormat": {"fontFamily": "Roboto Mono", "fontSize": 9}})
    ws.format("C6:C19", {"horizontalAlignment": "LEFT"})
    ws.format("D6:D19", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}})
    ws.format("E6:E19", {"horizontalAlignment": "CENTER"})
    ws.format("F6:F19", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})
    ws.format("G6:G19", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})

    # Row 20 Subtotal Base
    ws.format("A20:G20", {
        "backgroundColor": {"red": 0.96, "green": 0.97, "blue": 0.98},
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 0.1, "green": 0.2, "blue": 0.4}},
        "horizontalAlignment": "RIGHT"
    })
    ws.format("G20", {"numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})

    # Row 22 Header Insumo a Pedido: Warm Amber
    ws.format("A22:G22", {
        "backgroundColor": {"red": 0.95, "green": 0.65, "blue": 0.15}, # Amber
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
        "horizontalAlignment": "LEFT",
        "verticalAlignment": "MIDDLE"
    })

    # Row 23 Insumo a Pedido Data
    ws.format("A23:C23", {"horizontalAlignment": "LEFT"})
    ws.format("D23", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "NUMBER", "pattern": "0.00"}})
    ws.format("E23", {"horizontalAlignment": "CENTER"})
    ws.format("F23", {
        "backgroundColor": {"red": 0.90, "green": 0.98, "blue": 0.90}, # Light green background to highlight editable cell
        "horizontalAlignment": "RIGHT",
        "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"},
        "textFormat": {"bold": True}
    })
    ws.format("G23", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}, "textFormat": {"bold": True}})

    # Row 24 Note
    ws.format("A24:G24", {
        "backgroundColor": {"red": 0.99, "green": 0.98, "blue": 0.94},
        "textFormat": {"italic": True, "fontSize": 9, "foregroundColor": {"red": 0.4, "green": 0.3, "blue": 0.1}},
        "horizontalAlignment": "LEFT",
        "wrapStrategy": "WRAP"
    })

    # Row 25 Total Materiales con Tela
    ws.format("A25:G25", {
        "backgroundColor": {"red": 0.99, "green": 0.95, "blue": 0.88},
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 0.5, "green": 0.25, "blue": 0.0}},
        "horizontalAlignment": "RIGHT"
    })
    ws.format("G25", {"numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})

    # Row 27 Header Mano de Obra: Slate Grey
    ws.format("A27:G27", {
        "backgroundColor": {"red": 0.35, "green": 0.42, "blue": 0.52},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
        "horizontalAlignment": "LEFT",
        "verticalAlignment": "MIDDLE"
    })

    # Rows 28-30 Mano de Obra Data
    ws.format("A28:C30", {"horizontalAlignment": "LEFT"})
    ws.format("D28:D30", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "NUMBER", "pattern": "0.00"}})
    ws.format("E28:E30", {"horizontalAlignment": "CENTER"})
    ws.format("F28:F30", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})
    ws.format("G28:G30", {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})

    # Row 31 Total Mano de Obra
    ws.format("A31:G31", {
        "backgroundColor": {"red": 0.92, "green": 0.94, "blue": 0.97},
        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 0.15, "green": 0.25, "blue": 0.35}},
        "horizontalAlignment": "RIGHT"
    })
    ws.format("A31:C31", {"horizontalAlignment": "LEFT"})
    ws.format("G31", {"numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"}})

    # Row 33 Gran Total Costo Producción
    ws.format("A33:G33", {
        "backgroundColor": {"red": 0.08, "green": 0.45, "blue": 0.30}, # Dark Emerald Green
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
        "horizontalAlignment": "RIGHT",
        "verticalAlignment": "MIDDLE"
    })
    ws.format("G33", {
        "backgroundColor": {"red": 0.05, "green": 0.38, "blue": 0.25},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 12},
        "numberFormat": {"type": "CURRENCY", "pattern": "$ #,##0.00"},
        "horizontalAlignment": "RIGHT"
    })

    # Row 35 Help note
    ws.format("A35:G35", {
        "backgroundColor": {"red": 0.96, "green": 0.97, "blue": 0.99},
        "textFormat": {"italic": True, "fontSize": 9, "foregroundColor": {"red": 0.3, "green": 0.4, "blue": 0.5}},
        "horizontalAlignment": "LEFT",
        "wrapStrategy": "WRAP"
    })

    # Freeze rows up to row 5 so headers stay visible
    ws.freeze(rows=5)

    print("Formatting and freezing applied successfully!")

if __name__ == '__main__':
    main()
