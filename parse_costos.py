import sys
from services.sheets_service import SheetsService

sys.stdout.reconfigure(encoding='utf-8')

service = SheetsService()
gc = service._get_gspread_client()

# Source sheet
new_id = '1Ds3Y__Ffy3Zk_KWLTHH4SuPIHSrYoJyNW0PjnW0NWM4'
sh_new = gc.open_by_key(new_id)
ws_cost = sh_new.worksheet('Armado de Costo')
rows = ws_cost.get_all_values()

sections = []
current = None

for i, r in enumerate(rows):
    col0 = r[0].strip()
    if not col0 or col0 == 'Artículo / Componente':
        continue
    
    qty = r[3].strip() if len(r) > 3 else ''
    price = r[4].strip() if len(r) > 4 else ''
    total = r[5].strip() if len(r) > 5 else ''
    pct = r[6].strip() if len(r) > 6 else ''
    
    # Check if header
    if not qty and not price and not total and 'total planeado' not in col0.lower():
        current = {
            'title': col0,
            'line': i + 1,
            'items': [],
            'total_planeado': None
        }
        sections.append(current)
    elif 'total planeado' in col0.lower():
        if current:
            current['total_planeado'] = total
    else:
        if current:
            current['items'].append({
                'component': col0,
                'qty_str': qty,
                'price_str': price,
                'total_str': total,
                'pct_str': pct
            })

print(f"Parsed {len(sections)} sections in total.")
alpha_sections = [s for s in sections if 'alpha' in s['title'].lower()]
print(f"Alpha sections: {len(alpha_sections)}")
for s in alpha_sections:
    print(f"- {s['title']} ({len(s['items'])} items, Total: {s['total_planeado']})")
