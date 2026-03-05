"""
Deteccion de drones en tiempo real desde webcam.
Usa cv2.dnn con modelo ONNX (sin PyTorch/Ultralytics).

Uso:
    python detect_webcam.py
    python detect_webcam.py --source 1          # webcam secundaria
    python detect_webcam.py --conf 0.5          # umbral de confianza
    python detect_webcam.py --source rtsp://... # stream RTSP

Controles:
    q - Salir
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import time

# --------------------
# ARGUMENTOS
# --------------------

parser = argparse.ArgumentParser(description="Deteccion de drones en tiempo real")
parser.add_argument("--source", default="0", help="Indice de webcam (0, 1, ...) o URL RTSP")
parser.add_argument("--model", default=str(Path(__file__).parent.parent / "model" / "best.onnx"),
                    help="Ruta al modelo ONNX")
parser.add_argument("--conf", type=float, default=0.4, help="Umbral de confianza")
parser.add_argument("--iou", type=float, default=0.5, help="Umbral IoU para NMS")
args = parser.parse_args()

MODEL_PATH = Path(args.model)
CONF_THRES = args.conf
IOU_THRES = args.iou
INPUT_SIZE = 640

# Determinar si es indice de webcam o URL
try:
    SOURCE = int(args.source)
except ValueError:
    SOURCE = args.source

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"No se encontro el modelo: {MODEL_PATH}")

# --------------------
# PREPROCESAMIENTO
# --------------------

def letterbox(img, new_shape=640):
    h, w = img.shape[:2]
    scale = min(new_shape / h, new_shape / w)
    new_w, new_h = int(w * scale), int(h * scale)

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    dw = (new_shape - new_w) / 2
    dh = (new_shape - new_h) / 2
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))

    img_padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                     cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return img_padded, scale, (left, top)

# --------------------
# POSTPROCESAMIENTO
# --------------------

def nms(boxes, scores, iou_threshold):
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)

        remaining = np.where(iou <= iou_threshold)[0]
        order = order[remaining + 1]

    return keep


def postprocess(output, scale, pad_x, pad_y, orig_h, orig_w):
    preds = output[0].transpose(1, 0)

    scores = preds[:, 4]
    mask = scores > CONF_THRES
    preds = preds[mask]
    scores = scores[mask]

    if len(preds) == 0:
        return []

    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = (cx - w / 2 - pad_x) / scale
    y1 = (cy - h / 2 - pad_y) / scale
    x2 = (cx + w / 2 - pad_x) / scale
    y2 = (cy + h / 2 - pad_y) / scale

    x1 = np.clip(x1, 0, orig_w)
    y1 = np.clip(y1, 0, orig_h)
    x2 = np.clip(x2, 0, orig_w)
    y2 = np.clip(y2, 0, orig_h)

    boxes = np.stack([x1, y1, x2, y2], axis=1)

    keep = nms(boxes, scores, IOU_THRES)
    boxes = boxes[keep]
    scores = scores[keep]

    detections = []
    for box, score in zip(boxes, scores):
        detections.append((int(box[0]), int(box[1]), int(box[2]), int(box[3]), float(score)))

    return detections

# --------------------
# DIBUJAR DETECCIONES
# --------------------

def draw_detections(frame, detections):
    for (x1, y1, x2, y2, conf) in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"drone {conf:.2f}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 6), (x1 + label_size[0], y1), (0, 255, 0), -1)
        cv2.putText(frame, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return frame


def draw_hud(frame, fps, num_detections):
    h, w = frame.shape[:2]
    # FPS
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    # Detecciones
    cv2.putText(frame, f"Detecciones: {num_detections}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    # Instruccion
    cv2.putText(frame, "Presiona 'q' para salir", (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return frame

# --------------------
# CARGAR MODELO
# --------------------

print(f"Cargando modelo: {MODEL_PATH}")
print(f"OpenCV version: {cv2.__version__}")

net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

print("Modelo cargado exitosamente")

# --------------------
# CAPTURA EN TIEMPO REAL
# --------------------

cap = cv2.VideoCapture(SOURCE)
if not cap.isOpened():
    raise RuntimeError(f"No se pudo abrir la fuente de video: {SOURCE}")

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"Webcam: {width}x{height}")
print(f"Conf threshold: {CONF_THRES}, IoU threshold: {IOU_THRES}")
print("Iniciando deteccion en tiempo real... (presiona 'q' para salir)")

prev_time = time.time()
fps = 0.0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error al leer frame de la webcam")
        break

    # Preprocesar
    img_lb, scale, (pad_x, pad_y) = letterbox(frame, INPUT_SIZE)
    blob = cv2.dnn.blobFromImage(img_lb, 1.0 / 255.0, (INPUT_SIZE, INPUT_SIZE),
                                  swapRB=True, crop=False)

    # Inferencia
    net.setInput(blob)
    output = net.forward()

    # Postprocesar
    detections = postprocess(output, scale, pad_x, pad_y, height, width)

    # Calcular FPS
    curr_time = time.time()
    fps = 0.7 * fps + 0.3 * (1.0 / (curr_time - prev_time + 1e-9))
    prev_time = curr_time

    # Dibujar
    annotated = draw_detections(frame, detections)
    annotated = draw_hud(annotated, fps, len(detections))

    cv2.imshow("Drone Detection", annotated)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print("Sesion finalizada.")
