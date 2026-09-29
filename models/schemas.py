from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class MovementType(str, Enum):
    INGRESO = "INGRESO"
    EGRESO = "EGRESO"
    AJUSTE = "AJUSTE"

class CategoryEnum(str, Enum):
    MADERA = "Madera"
    TELAS = "Telas"
    POLIESTER = "Poliéster / Espumas"
    HERRAJES_INSUMOS = "Insumos y Herrajes"
    RELLENOS = "Rellenos y Guata"
    COSTURA = "Costura e Hilos"
    EMBALAJE = "Embalaje"
    QUIMICOS = "Químicos y Pegamentos"
    OTROS = "Otros"

class StockItem(BaseModel):
    barcode: str = Field(..., description="Código de barras o código de insumo (ej: MAD-34X6-001)")
    description: str = Field(..., description="Descripción del producto o material")
    category: str = Field(default="Otros", description="Categoría en la fábrica de sillones")
    cant_inventario: float = Field(default=0.0, description="Cantidad contada de inventario")
    compra_semana: float = Field(default=0.0, description="Compra de la semana")
    current_stock: float = Field(default=0.0, description="TOTAL INVENTARIO disponible")
    cant_x_caja: Optional[str] = Field(default="N/A", description="Cantidad por caja o presentación")
    unit: str = Field(default="unidad", description="Unidad de medida (pie, m2, metro, unidad, kg, litro)")
    min_stock: float = Field(default=0.0, description="Stock Mínimo de seguridad")
    comprar: float = Field(default=0.0, description="Cantidad sugerida a comprar")
    unit_price: float = Field(default=0.0, description="Precio unitario ($ x Unidad)")
    subtotal: float = Field(default=0.0, description="Costo subtotal ($ x Unidad * Total)")
    notes: Optional[str] = Field(default=None, description="Observaciones")
    is_critical: bool = Field(default=False, description="Indica si requiere reposición urgente")

class StockMovement(BaseModel):
    barcode: str
    movement_type: MovementType
    quantity: float = Field(gt=0, description="Cantidad a ingresar, egresar o fijar")
    responsible: Optional[str] = Field(default="Operario Nictom", description="Nombre del operario")
    reason: Optional[str] = Field(default=None, description="Motivo / Orden de Trabajo")
    timestamp: datetime = Field(default_factory=datetime.now)

class AlertResponse(BaseModel):
    status: str
    sent_to_telegram: bool
    total_critical_items: int
    critical_items: List[StockItem]
    message: str
