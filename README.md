# Anti-UAV RGB Detection with YOLOv8

Proyecto local para **detección de drones (UAV)** a partir de **videos RGB (`visible.mp4`) y anotaciones (`visible.json`)**, utilizando **YOLOv8** y **PyTorch con CUDA**.

El pipeline completo cubre:
- Construcción del dataset YOLO desde video + JSON
- Verificación visual de etiquetas
- Entrenamiento con checkpoints
- Inferencia sobre video

---

## 📁 Estructura del proyecto

Anti-UAV-RGBT/
│
├── train/ # Videos y JSON (entrenamiento)
├── val/ # Videos y JSON (validación)
├── test/ # Videos y JSON (prueba)
│
├── dataset_yolo/ # Dataset generado automáticamente
│ ├── images/
│ │ ├── train/
│ │ ├── val/
│ │ └── test/
│ └── labels/
│ ├── train/
│ ├── val/
│ └── test/
│
├── runs/ # Resultados YOLO (entrenamiento e inferencia)
│
├── build_yolo_dataset.py # Genera imágenes y labels desde video + JSON
├── check_yolo_labels.py # Verificación visual de bounding boxes
├── train_yolo.py # Entrenamiento YOLOv8
├── predict_video.py # Inferencia sobre video
│
├── drone.yaml # Configuración del dataset YOLO
├── requirements.txt # Dependencias mínimas del proyecto
└── README.md


---

## 🧠 Descripción del dataset de origen

Cada subcarpeta dentro de `train/`, `val/` y `test/` contiene:

visible.mp4
visible.json
infrared.mp4 # (no usado por ahora)
infrared.json # (no usado por ahora)


El archivo `visible.json` contiene:
- `exist`: indica si el dron está presente en cada frame
- `gt_rect`: bounding box `[x, y, w, h]` por frame

Suposiciones actuales:
- **Una sola clase** (`drone`)
- **Un solo objeto por frame**

---

## ⚙️ Requisitos del sistema

- Windows
- Python **3.10.x**
- GPU NVIDIA con CUDA funcional
- Drivers NVIDIA correctamente instalados

---

## Instalación del entorno

### 1. Crear y activar entorno virtual

```bat
python -m venv venv
venv\Scripts\activate

### 2. Instalar PyTorch con CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

### 3. Instalar dependencias del proyecto
pip install -r requirements.txt

###4. Verificar disponibilidad de GPU
python -c "import torch; print(torch.cuda.is_available())"

Debe imprimir True.

## Construcción del dataset YOLO

Genera imágenes y etiquetas a partir de los videos y archivos JSON:

python build_yolo_dataset.py

Salida generada:

dataset_yolo/
  images/{train,val,test}
  labels/{train,val,test}

## Verificación visual de etiquetas (PASO OBLIGATORIO)

### Antes de entrenar, validar visualmente las bounding boxes:

python check_yolo_labels.py

Se mostrarán imágenes con las cajas dibujadas sobre el dron.

## Entrenamiento del modelo

Ejecutar el entrenamiento con checkpoints automáticos:

python train_yolo.py

Resultados generados:

runs/detect/train/
├── weights/
│   ├── best.pt
│   ├── last.pt
│   ├── epoch5.pt
│   ├── epoch10.pt
│   └── ...
├── results.csv
├── results.png

Métricas de entrenamiento

Archivo principal:

runs/detect/train/results.csv

Incluye por época:

box_loss

cls_loss

dfl_loss

precision

recall

mAP50

mAP50-95

Inferencia sobre video

Editar la ruta del video dentro de predict_video.py y ejecutar:

python predict_video.py

Resultados guardados automáticamente en:

runs/detect/predict/

Incluye el video con bounding boxes dibujadas.

Estado actual del proyecto

Dataset generado correctamente
Etiquetas verificadas visualmente
Modelo entrenado con alto desempeño
Inferencia en tiempo real funcional

Posibles extensiones futuras

Entrenamiento con infrared (IR)

Fusión RGB + IR

Inferencia batch sobre múltiples videos

Exportación a ONNX / TensorRT

Integración con trackers (BYTETrack, DeepSORT)

Nota final

Este proyecto está diseñado para uso local, reproducible y controlado, priorizando claridad del pipeline, estabilidad en GPU y facilidad de modificación del código.