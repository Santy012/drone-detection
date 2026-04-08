from ultralytics import YOLO
import os

def main():
    # Cargar el modelo preentrenado (YOLOv8 Nano)
    model = YOLO("yolov8n.pt")

    # 🔥 CONFIGURACIÓN DE ENTRENAMIENTO CON NUEVA ESTRATEGIA DE AUGMENTATION
    # Se eliminó el preprocesamiento manual y se usan las imágenes RGB originales
    model.train(
        data="drone.yaml",    # Asegúrate que el path en drone.yaml sea correcto
        epochs=100,
        imgsz=640,
        batch=16,             # Ajustado según capacidad de memoria
        device=0,             # Usar GPU (cambiar a 'cpu' si no hay CUDA disponible)
        
        # 🔥 AUGMENTATION (IMPORTANTE: CONFIGURACIÓN SOLICITADA)
        hsv_h=0.015,          # cambios leves de color
        hsv_s=0.5,            # saturación moderada
        hsv_v=0.4,            # valor/brillo moderado
        
        degrees=5.0,          # rotación leve para no deformar silueta
        translate=0.05,       # traslación ligera
        scale=0.4,            # CRÍTICO: aumenta drones más pequeños para mejorar detección a distancia
        
        fliplr=0.5,           # flip horizontal (simula drones volando en sentido opuesto)
        
        mosaic=0.2,           # bajo para no perder drones pequeños en el mosaico
        mixup=0.0,            # desactivado (evita confusión visual)
        
        # Parámetros adicionales de monitoreo
        save_period=10,
        cache=False
    )

if __name__ == "__main__":
    main()
