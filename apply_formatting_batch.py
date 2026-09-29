import sys
import time
from services.sheets_service import SheetsService

sys.stdout.reconfigure(encoding='utf-8')

def main():
    service = SheetsService()
    gc = service._get_gspread_client()
    sh = gc.open_by_key(service.spreadsheet_id)
    ws = sh.worksheet('RECETAS')
    sheet_id = ws.id

    rows = ws.get_all_values()
    total_len = len(rows)
    print(f"Applying styling to {total_len} rows in RECETAS...")

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

    # 2. Freeze top 5 rows
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

    # 3. Formats across columns
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
                    "textFormat": {
                        "fontFamily": "Roboto Mono",
                        "fontSize": 9
                    }
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,textFormat)"
        }
    })

    # Col D: Quantity format #,##0.00, right align
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
                    "numberFormat": {
                        "type": "NUMBER",
                        "pattern": "#,##0.00"
                    }
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Col E: Unit, center
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

    # Col F: Unit price format $ #,##0.00, right align
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
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "$ #,##0.00"
                    }
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Col G: Subtotal format $ #,##0.00, right align
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
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "$ #,##0.00"
                    }
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,numberFormat)"
        }
    })

    # Row 1 banner
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

    # Identify row types
    for i, r in enumerate(rows):
        col0 = r[0].strip() if r else ''
        if not col0:
            continue

        # Model headers
        if col0.startswith("🛋️ MODELO:"):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 7
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.12, "green": 0.35, "blue": 0.75}, # Royal Blue
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                }
            })

        # Table headers
        elif col0 == "Modelo" and len(r) > 1 and r[1].strip() == "Código Insumo":
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
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

        # Subtotal rows
        elif col0.startswith("TOTAL MATERIALES ("):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
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

        # Conrad Insumo a Pedido header
        elif col0.startswith("📦 INSUMO A PEDIDO"):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 7
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.95, "green": 0.65, "blue": 0.15}, # Amber
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                }
            })

        # Conrad Mano de obra header
        elif col0.startswith("⏱️ TIEMPOS ESTIMADOS"):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 7
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.35, "green": 0.42, "blue": 0.52}, # Slate
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                }
            })

        # Conrad Gran Total
        elif col0.startswith("🏁 COSTO TOTAL ESTIMADO"):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 7
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.08, "green": 0.45, "blue": 0.30}, # Dark emerald
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11},
                            "horizontalAlignment": "RIGHT",
                            "verticalAlignment": "MIDDLE"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
                }
            })

    print(f"Generated {len(requests)} formatting requests in single batch. Sending...")
    sh.batch_update({"requests": requests})
    print("Formatting applied successfully in ONE single batchUpdate request!")

if __name__ == '__main__':
    main()
