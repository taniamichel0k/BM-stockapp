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

def dry_run():
    sections = parse_costos.sections
    alpha_and_unique = []
    seen_bases = set()
    
    # Priority order: Alpha sections first, then unique other sections
    for s in sections:
        title = s['title']
        if 'alpha' in title.lower():
            alpha_and_unique.append(s)
            base = re.sub(r'[\s\-_]*alpha[\s\-_]*', '', title, flags=re.IGNORECASE).strip()
            seen_bases.add(base.lower())
            
    for s in sections:
        title = s['title']
        base = re.sub(r'[\s\-_]*(alpha|pana riff|pana jaguar/ cuero tex|pana jaguar / cuero tex|cuero tex|eco cuero)[\s\-_]*', '', title, flags=re.IGNORECASE).strip()
        if base.lower() not in seen_bases:
            alpha_and_unique.append(s)
            seen_bases.add(base.lower())
            
    print(f"Selected {len(alpha_and_unique)} models for RECETAS:")
    total_rows = 5 # header
    for s in alpha_and_unique:
        items_count = sum(1 for it in s['items'] if 'mano obra' not in it['component'].lower() and 'm.o.' not in it['component'].lower())
        total_rows += items_count + 3 # title, header, total, blank
        print(f"  - {s['title']}: {items_count} items")
        
    print(f"\nEstimated total rows in RECETAS: {total_rows}")

if __name__ == '__main__':
    dry_run()
