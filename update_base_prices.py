import sys
from services.sheets_service import SheetsService
import build_price_updates
import parse_costos

sys.stdout.reconfigure(encoding='utf-8')

def update_base_prices(gc, spreadsheet_id):
    sh = gc.open_by_key(spreadsheet_id)
    ws_base = sh.worksheet('BASE')
    
    updates = build_price_updates.price_updates
    print(f"Applying {len(updates)} price updates (+21% IVA) to BASE...")
    
    cell_updates = []
    for code, d in updates.items():
        row_num = d['row']
        new_price = d['new_price']
        cell_updates.append({
            'range': f'Q{row_num}',
            'values': [[new_price]]
        })
    
    ws_base.batch_update(cell_updates, value_input_option='USER_ENTERED')
    print("BASE prices updated successfully!")

if __name__ == '__main__':
    service = SheetsService()
    gc = service._get_gspread_client()
    update_base_prices(gc, service.spreadsheet_id)
