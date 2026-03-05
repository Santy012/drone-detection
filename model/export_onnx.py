"""
Exporta best.pt a formato ONNX.
Ejecutar UNA SOLA VEZ en tu laptop Windows (donde tienes torch + ultralytics).
Luego copiar el .onnx resultante a la Raspberry Pi.

Uso:
    python export_onnx.py

Requisitos (solo en laptop):
    pip install torch torchvision ultralytics
"""
from ultralytics import YOLO
from pathlib import Path

MODEL_PATH = Path("best.pt")

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"No se encontró {MODEL_PATH}. "
        "Asegúrate de tener best.pt en el directorio actual."
    )

model = YOLO(str(MODEL_PATH))
model.export(format="onnx", imgsz=640, simplify=True)

output = MODEL_PATH.with_suffix(".onnx")
print(f"\nModelo exportado exitosamente: {output}")
print(f"Tamaño: {output.stat().st_size / 1024 / 1024:.1f} MB")
print(f"\nAhora copia {output.name} a la Raspberry Pi:")
print(f"  scp {output} gustavo1@172.20.10.9:~/Documents/drones/")
