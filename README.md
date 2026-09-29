# 🛋️ Sistema de Control de Stock - Fábrica de Sillones

Aplicación web modular desarrollada en **Python** con **Streamlit** (frontend interactivo) y **FastAPI** (backend y webhooks), integrada en tiempo real con **Google Sheets** y sistema de alertas automáticas vía **Telegram**.

---

## 📁 Estructura del Proyecto

```text
App-Stock/
│
├── api/
│   ├── __init__.py
│   └── main.py                     # API REST FastAPI, endpoints y webhook de Telegram
│
├── models/
│   ├── __init__.py
│   └── schemas.py                  # Modelos Pydantic (StockItem, StockMovement, Categorías)
│
├── services/
│   ├── __init__.py
│   ├── sheets_service.py           # Conexión, lectura y actualización en Google Sheets
│   ├── telegram_service.py         # Envío de alertas de stock crítico y movimientos
│   └── stock_service.py            # Lógica de negocio, cálculos de inventario y KPIs
│
├── credentials/
│   ├── credentials.example.json    # Plantilla de credenciales de Google Service Account
│   └── service_account.json        # Tu clave privada de Google Cloud (ignorado en git)
├── app.py                          # Panel de control web interactivo en Streamlit
├── config.py                       # Configuración y variables de entorno centralizadas
├── run.py                          # Script de inicio rápido (Streamlit / FastAPI)
├── requirements.txt                # Dependencias del proyecto
├── .env.example                    # Plantilla de variables de entorno
├── .env                            # Variables de entorno locales
├── .gitignore                      # Protección de credenciales y archivos temporales
└── README.md                       # Documentación del proyecto
```

---

## 🏷️ Funcionamiento con Lector de Código de Barras NICTOM

Los lectores Nictom (USB o inalámbricos) funcionan como dispositivos de teclado directo (*HID*):
1. Al hacer foco en el campo **"Código de Barras / Código de Insumo"**, escaneas la etiqueta del producto.
2. El lector Nictom ingresa el código (ej: `INS-GRA-8411`, `TOR-FIX-075`, `MAD-34X6-001`) y emite `Enter` automáticamente.
3. El sistema busca el producto en la planilla y despliega su tarjeta:
   - Nombre, Categoría, Unidad, Stock Actual y Stock Mínimo.
4. **Carga Manual Inmediata:**
   - **Fijar Stock Total:** Para recuento físico de inventario.
   - **Sumar Ingreso (+):** Para recepcionar mercadería de compras semanales.
   - **Restar Egreso (-):** Para consumo en tapicería o armado de sillones.
5. Al guardar, el stock se actualiza al instante, queda registrado en el historial de escaneos y emite alerta si cae debajo del mínimo.

---

## 📋 Planilla Interactiva "STOCK BUENA MADERA" (Estilo Google Sheets)

- Imita con exactitud la estructura de columnas de tu Google Sheets:
  `Codigo de Barras` | `Descripción de Producto` | `TOTAL INVENTARIO` | `Cant. Inventario` | `Compra Semana` | `Unidad` | `Stock Mínimo` | `$ x Unidad` | `$ SubTotal` | `Observaciones`
- **Edición en celda tipo Excel:** Puedes hacer clic en cualquier celda de `TOTAL INVENTARIO`, `Stock Mínimo`, `Precio` u `Observaciones`, modificar los valores y presionar **"💾 Guardar Cambios Directos de la Planilla"**.

### 1. Clonar o ingresar a la carpeta del proyecto
```bash
cd "c:\Users\Tania Michel\Documents\App-Stock"
```

### 2. Crear entorno virtual (Recomendado)
```bash
python -m venv .venv
# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# O en Windows (CMD):
.venv\Scripts\activate.bat
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Iniciar la Aplicación

#### Opción A: Iniciar la interfaz web en Streamlit (Recomendado para operarios y taller)
```bash
python run.py streamlit
# O directamente:
streamlit run app.py
```
Se abrirá automáticamente en tu navegador en: `http://localhost:8501`

#### Opción B: Iniciar la API Backend en FastAPI
```bash
python run.py api
# O directamente:
uvicorn api.main:app --reload --port 8000
```
Documentación interactiva Swagger disponible en: `http://localhost:8000/docs`

---

## 📊 Integración con Google Sheets

- **ID de la Planilla:** `1w2U7ne3prRJlmx5e9WZG3oPRda8tS5lh`
- **Pestaña GID:** `1472867645`
- [Enlace directo a la planilla de Google Sheets](https://docs.google.com/spreadsheets/d/1w2U7ne3prRJlmx5e9WZG3oPRda8tS5lh/edit?gid=1472867645#gid=1472867645)

### Modos de Conexión:
1. **Lectura Inmediata (Sin credenciales):** La aplicación incluye un lector CSV inteligente que extrae en tiempo real los insumos de la planilla pública (códigos como `MAD-...`, `TEL-...`, `POL-...`, `INS-...`, existencias, precios y notas).
2. **Edición Bidireccional (Con Service Account):**
   - Habilita la **Google Sheets API** y **Google Drive API** en [Google Cloud Console](https://console.cloud.google.com/).
   - Crea una Cuenta de Servicio (*Service Account*), genera una clave en formato JSON y guárdala como `credentials/service_account.json`.
   - Comparte la hoja de cálculo con el email de la cuenta de servicio con rol **Editor**.

---

## 📲 Configuración de Alertas por Telegram

1. Habla con **[@BotFather](https://t.me/BotFather)** en Telegram y crea un bot con `/newbot`.
2. Copia el token generado.
3. Inicia un chat con tu bot o agrégalo a tu grupo de fábrica / compras.
4. Obtén tu `CHAT_ID` (enviándole un mensaje al bot [@userinfobot](https://t.me/userinfobot) o [@getidsbot](https://t.me/getidsbot)).
5. Agrégalos en tu archivo `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
   TELEGRAM_CHAT_ID=-1001234567890
   ```
*(Si no configuras el token, el sistema opera en modo simulación mostrando las alertas en consola sin romper el flujo).*

---

## 🛠️ Categorías de Insumos para Fábrica de Sillones

El sistema clasifica automáticamente los ítems del inventario según sus códigos y descripciones:
- **Madera (`MAD-`):** Tablones, maderas 3/4x6, 1.5x6, listones.
- **Telas (`TEL-`):** Pana, Jaguar, Chenille, Cuerotex, Rustic, Friselina.
- **Poliéster / Espumas (`POL-`):** Espumas 1cm a 13cm en varias densidades y colores (blanco, celeste, amarillo, naranja).
- **Insumos y Herrajes (`INS-`, `TOR-`):** Grampas 8411, 9040, tornillos, tuercas, bulones, patas plásticas y madera, bisagras, regatones.
- **Rellenos (`REL-`):** Vellón, guata, copos.
- **Embalaje (`EMB-`):** Film stretch, cinta de embalar, cartón corrugado.
- **Costura (`COS-`):** Hilos negro y blanco, etiquetas.
- **Químicos (`QUI-`):** Adhesivo Fana, cola, tintas.
