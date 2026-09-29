import sys
from services.sheets_service import SheetsService

sys.stdout.reconfigure(encoding='utf-8')
import parse_costos

component_mapping = {
    'Grampa 84/12': ('INS-GRA-8411', 'grampas 8411', 'unidad'),
    'Grampa 90/40': ('INS-GRA-9040', 'grampas 9040', 'unidad'),
    'Tornillo p/madera 75': ('TOR-FIX-075', 'tornillo 75', 'unidad'),
    'Tornillo p/madera 45': ('TOR-FIX-045', 'tornillo 45', 'unidad'),
    'Tornillo p/madera 25': ('TOR-FIX-025', 'tornillo 25', 'unidad'),
    'Cierre Reforzado x mts': ('INS-CIE-001', 'cierre reforzado', 'metro'),
    'Friselina de 1,5 mts 45gr': ('TEL-FRI-001', 'friselina', 'metro'),
    'Block Poliester x kg': ('POL-03CM-002', 'Poliester 3 cm celeste', 'kg'),
    'Cortes Poliester  x Kg': ('POL-COR-001', 'cortes poliester', 'kg'),
    'Tela Alpha': ('TEL-ALP-001', 'tela alpha', 'metro'),
    'Tela Pana Riff': ('TEL-PAN-RIF', 'tela pana riff', 'metro'),
    'Tela Cuerotex': ('TEL-CTX-001', 'Tela Cuerotex', 'metro'),
    'Tela Eco Cuero': ('TEL-ECO-CUE', 'Tela Eco Cuero', 'metro'),
    'Tela Pana Jaguar': ('TEL-PAN-JAG', 'Tela Pana Jaguar', 'metro'),
    'M2_Madera terceada': ('PLA-TER-M2', 'M2 Terciado', 'm2'),
    'Madera terceada_MP': ('PLA-TER-M2', 'M2 Terciado', 'm2'),
    'PIE_Madera 1"': ('MAD-10X6-001', 'madera 1 x 6 (3.05mts)', 'pie'),
    'PIE_Madera 1,5"': ('MAD-15X6-001', 'madera 1,5 x 6 (3.05 mts)', 'pie'),
    'PIE_Madera 3/4"': ('MAD-34X6-002', 'madera 3/4 x 6 (3.7 mts)', 'pie'),
    'Plastillera': ('EMB-PLA-001', 'plastillera', 'metro'),
    'Deslizador _MP': ('INS-DES-001', 'deslizadores', 'unidad'),
    'Pata Plástica': ('INS-PAT-PLA', 'Pata Plástica', 'unidad'),
    'Patas Madera': ('INS-PAT-MAD', 'Patas Madera', 'unidad'),
    'Pata Fundición': ('INS-PAT-FUN', 'Pata Fundición', 'unidad'),
    'Rueda Carro': ('INS-RUE-CAR', 'Rueda Carro', 'unidad'),
    'Bisagras': ('INS-BIS-001', 'bisagras', 'unidad'),
    'Bulón': ('INS-BUL-516', 'bulones 5/16', 'unidad'),
    'Tuercas': ('INS-TUE-001', 'Tuercas', 'unidad'),
    'Hormillas': ('INS-HOR-001', 'Hormillas', 'unidad'),
    'Regaton 130x130x5_MP': ('INS-REG-001', 'regatones', 'unidad'),
    'Guata x mts': ('REL-GUA-001', 'Guata x mts', 'metro'),
    'Vellon x Kg': ('REL-VEL-001', 'Vellon x Kg', 'kg'),
    'Copos x Kg / Scrap': ('REL-COP-001', 'Copos X kg', 'kg'),
    'Embalaje': ('EMB-GEN-001', 'embalaje', 'metro'),
    'Parrilla': ('INS-PAR-001', 'Parrilla', 'unidad'),
    'Hilo 40gr NEGRO': ('COS-HIL-NEG', 'hilo negro', 'unidad'),
    'Almohadones x Kg _MP': ('POL-COR-001', 'Almohadones x Kg', 'kg'),
}

unmapped = set()
for s in parse_costos.sections:
    for item in s['items']:
        comp = item['component']
        if 'mano obra' in comp.lower() or 'm.o.' in comp.lower():
            continue
        if comp not in component_mapping:
            unmapped.add(comp)

print(f"Unmapped components count: {len(unmapped)}")
for u in sorted(unmapped):
    print("-", u)
