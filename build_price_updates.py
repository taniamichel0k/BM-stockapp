import sys
from services.sheets_service import SheetsService

sys.stdout.reconfigure(encoding='utf-8')

service = SheetsService()
gc = service._get_gspread_client()

# Source sheet
new_id = '1Ds3Y__Ffy3Zk_KWLTHH4SuPIHSrYoJyNW0PjnW0NWM4'
sh_new = gc.open_by_key(new_id)
ws_mat = sh_new.worksheet('Materiales')
mat_rows = ws_mat.get('A2:H52', value_render_option='UNFORMATTED_VALUE')

# Map of Materiales descriptions to our BASE barcode
mat_to_barcode = {
    'Grampa 84/12': 'INS-GRA-8411',
    'Grampa 90/40': 'INS-GRA-9040',
    'PIE_Madera 1"': 'MAD-10X6-001',
    'PIE_Madera 1,5"': 'MAD-15X6-001',
    'PIE_Madera 3/4"': 'MAD-34X6-002',
    'Pino s/natural en bruto 3/4 x 6 x 3,05 mts_MP': 'MAD-34X6-001',
    'M2_Madera terceada': 'PLA-TER-M2',
    'Madera terceada_MP': 'PLA-TER-M2',
    'Cortes Poliester  x Kg': 'POL-COR-001',
    'Block Poliester x kg': 'POL-03CM-002',
    'Guata x mts': 'REL-GUA-001',
    'Vellon x Kg': 'REL-VEL-001',
    'Copos x Kg / Scrap': 'REL-COP-001',
    'Tela Alpha': 'TEL-ALP-001',
    'Tela Pana Riff': 'TEL-PAN-RIF',
    'Tela Cuerotex': 'TEL-CTX-001',
    'Tela Eco Cuero': 'TEL-ECO-CUE',
    'Tela Pana Jaguar': 'TEL-PAN-JAG',
    'Friselina de 1,5 mts 45gr': 'TEL-FRI-001',
    'Plastillera': 'EMB-PLA-001',
    'Tornillo p/madera 75': 'TOR-FIX-075',
    'Tornillo p/madera 45': 'TOR-FIX-045',
    'Tornillo p/madera 25': 'TOR-FIX-025',
    'Hormillas': 'INS-HOR-001',
    'Hilo 40gr NEGRO': 'COS-HIL-NEG',
    'Pata Plástica': 'INS-PAT-PLA',
    'Patas Madera': 'INS-PAT-MAD',
    'Pata Fundición': 'INS-PAT-FUN',
    'Rueda Carro': 'INS-RUE-CAR',
    'Bulón': 'INS-BUL-516',
    'Bisagras': 'INS-BIS-001',
    'Tuercas': 'INS-TUE-001',
    'Cierre Reforzado x mts': 'INS-CIE-001',
    'Deslizador _MP': 'INS-DES-001',
    'Regaton 130x130x5_MP': 'INS-REG-001',
    'Parrilla': 'INS-PAR-001',
}

# Stock sheet
sh_stock = gc.open_by_key(service.spreadsheet_id)
ws_base = sh_stock.worksheet('BASE')
base_rows = ws_base.get('A1:R70', value_render_option='UNFORMATTED_VALUE')

base_indices = {}
for idx, r in enumerate(base_rows):
    if len(r) > 4 and r[4]:
        base_indices[str(r[4]).strip()] = idx + 1 # 1-based row number

price_updates = {}
for r in mat_rows:
    desc = str(r[1]).strip() if len(r) > 1 and r[1] is not None else ''
    p_no_iva = r[2] if len(r) > 2 and r[2] != '' else None
    p_c_iva = r[3] if len(r) > 3 and r[3] != '' else None
    
    if p_c_iva is not None and isinstance(p_c_iva, (int, float)) and p_c_iva > 0:
        price_val = round(float(p_c_iva), 2)
    elif p_no_iva is not None and isinstance(p_no_iva, (int, float)) and p_no_iva > 0:
        price_val = round(float(p_no_iva) * 1.21, 2)
    else:
        continue
        
    code = mat_to_barcode.get(desc)
    if code and code in base_indices:
        row_num = base_indices[code]
        old_val = base_rows[row_num - 1][16] if len(base_rows[row_num - 1]) > 16 else None
        price_updates[code] = {
            'row': row_num,
            'desc': desc,
            'new_price': price_val,
            'old_price': old_val
        }

print(f"Matched {len(price_updates)} materials to update in BASE:")
for code, d in sorted(price_updates.items()):
    print(f"Row {d['row']:02d} | {code:<14} | {d['desc']:<30} | Old: {d['old_price']} -> New (+21%): ${d['new_price']}")
