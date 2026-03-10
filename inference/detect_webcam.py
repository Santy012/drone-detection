"""
Deteccion de drones en tiempo real desde webcam.
Usa cv2.dnn con modelo ONNX (sin PyTorch/Ultralytics).
Incluye deteccion de movimiento como prefiltro para ahorrar CPU.

Uso:
    python detect_webcam.py
    python detect_webcam.py --source 1              # webcam secundaria
    python detect_webcam.py --conf 0.5              # umbral de confianza
    python detect_webcam.py --motion-thresh 5000    # sensibilidad movimiento
    python detect_webcam.py --no-motion-filter      # desactivar prefiltro
    python detect_webcam.py --source rtsp://...     # stream RTSP

Controles:
    q - Salir
    m - Activar/desactivar prefiltro de movimiento
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import time
import threading
from datetime import datetime, timezone

# --------------------
# ARGUMENTOS
# --------------------

parser = argparse.ArgumentParser(description="Deteccion de drones en tiempo real")
parser.add_argument("--source", default="0", help="Indice de webcam (0, 1, ...) o URL RTSP")
parser.add_argument("--model", default=str(Path(__file__).parent.parent / "model" / "best.onnx"),
                    help="Ruta al modelo ONNX")
parser.add_argument("--conf", type=float, default=0.4, help="Umbral de confianza")
parser.add_argument("--iou", type=float, default=0.5, help="Umbral IoU para NMS")
parser.add_argument("--motion-thresh", type=int, default=5000,
                    help="Umbral de pixeles cambiados para detectar movimiento (menor = mas sensible)")
parser.add_argument("--no-motion-filter", action="store_true",
                    help="Desactivar prefiltro de movimiento (inferencia en cada frame)")
parser.add_argument("--api-url", default=None,
                    help="URL de API Gateway (e.g., https://xyz.execute-api.us-east-1.amazonaws.com/v1)")
parser.add_argument("--device-id", default="laptop-01",
                    help="Identificador del dispositivo")
parser.add_argument("--upload-cooldown", type=float, default=2.0,
                    help="Segundos minimos entre uploads al cloud")
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

MOTION_THRESH = args.motion_thresh
motion_filter_enabled = not args.no_motion_filter
API_URL = args.api_url
DEVICE_ID = args.device_id
UPLOAD_COOLDOWN = args.upload_cooldown

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"No se encontro el modelo: {MODEL_PATH}")

# --------------------
# CLOUD REPORTING
# --------------------

last_upload_time = 0.0

def report_detection(api_url, device_id, frame, detections):
    """Sube imagen anotada a S3 y reporta deteccion a la API (background thread)."""
    try:
        import requests as req

        # 1. Obtener presigned URL
        resp = req.post(f"{api_url}/presign",
                        json={"device_id": device_id}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        upload_url = data["upload_url"]
        s3_key = data["s3_key"]

        # 2. Codificar frame como JPEG
        _, jpg_bytes = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # 3. Subir a S3
        req.put(upload_url, data=jpg_bytes.tobytes(),
                headers={"Content-Type": "image/jpeg"}, timeout=10)

        # 4. Reportar deteccion
        det_payload = [{"x1": d[0], "y1": d[1], "x2": d[2], "y2": d[3],
                        "confidence": d[4]} for d in detections]

        ts = datetime.now(timezone.utc).isoformat()
        req.post(f"{api_url}/detections", json={
            "device_id": device_id,
            "timestamp": ts,
            "snapshot_key": s3_key,
            "detections": det_payload,
        }, timeout=5)

        print(f"  [cloud] Reportado: {len(detections)} detecciones -> {s3_key}")
    except Exception as e:
        print(f"  [cloud] Error: {e}")

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


def detect_motion(gray_curr, gray_prev, threshold):
    """Detecta movimiento comparando dos frames en escala de grises.
    Retorna (hay_movimiento, cantidad_pixeles_cambiados)."""
    if gray_prev is None:
        return True, 0
    diff = cv2.absdiff(gray_curr, gray_prev)
    _, thresh_img = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    changed_pixels = cv2.countNonZero(thresh_img)
    return changed_pixels > threshold, changed_pixels


def draw_hud(frame, fps, num_detections, motion_active, has_motion, motion_pixels):
    h, w = frame.shape[:2]
    # FPS
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    # Detecciones
    cv2.putText(frame, f"Detecciones: {num_detections}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    # Estado del motion filter
    if motion_active:
        motion_color = (0, 255, 0) if has_motion else (0, 0, 255)
        motion_text = f"Movimiento: {'SI' if has_motion else 'NO'} ({motion_pixels}px)"
        cv2.putText(frame, motion_text, (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, motion_color, 2)
    else:
        cv2.putText(frame, "Movimiento: OFF", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)
    # Instrucciones
    cv2.putText(frame, "'q' salir | 'm' toggle movimiento", (10, h - 15),
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
print(f"Motion filter: {'ON (thresh={})'.format(MOTION_THRESH) if motion_filter_enabled else 'OFF'}")
print(f"Cloud API: {API_URL if API_URL else 'OFF (modo local)'}")
print("Iniciando deteccion en tiempo real...")
print("  'q' para salir | 'm' para toggle motion filter")

prev_time = time.time()
fps = 0.0
prev_gray = None
detections = []
has_motion = True
motion_pixels = 0
skipped_frames = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error al leer frame de la webcam")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_blurred = cv2.GaussianBlur(gray, (21, 21), 0)

    # Detectar movimiento
    if motion_filter_enabled:
        has_motion, motion_pixels = detect_motion(gray_blurred, prev_gray, MOTION_THRESH)
    else:
        has_motion = True
        motion_pixels = 0

    prev_gray = gray_blurred

    # Solo ejecutar inferencia si hay movimiento
    if has_motion:
        img_lb, scale, (pad_x, pad_y) = letterbox(frame, INPUT_SIZE)
        blob = cv2.dnn.blobFromImage(img_lb, 1.0 / 255.0, (INPUT_SIZE, INPUT_SIZE),
                                      swapRB=True, crop=False)
        net.setInput(blob)
        output = net.forward()
        detections = postprocess(output, scale, pad_x, pad_y, height, width)
    else:
        detections = []
        skipped_frames += 1

    # Calcular FPS
    curr_time = time.time()
    fps = 0.7 * fps + 0.3 * (1.0 / (curr_time - prev_time + 1e-9))
    prev_time = curr_time

    # Reportar al cloud si hay detecciones y pasó el cooldown
    if detections and API_URL:
        now = time.time()
        if now - last_upload_time >= UPLOAD_COOLDOWN:
            last_upload_time = now
            annotated_copy = draw_detections(frame.copy(), detections)
            threading.Thread(
                target=report_detection,
                args=(API_URL, DEVICE_ID, annotated_copy, detections),
                daemon=True,
            ).start()

    # Dibujar
    annotated = draw_detections(frame, detections)
    annotated = draw_hud(annotated, fps, len(detections),
                         motion_filter_enabled, has_motion, motion_pixels)

    cv2.imshow("Drone Detection", annotated)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    elif key == ord("m"):
        motion_filter_enabled = not motion_filter_enabled
        state = "ON" if motion_filter_enabled else "OFF"
        print(f"Motion filter: {state}")

cap.release()
cv2.destroyAllWindows()
print(f"Sesion finalizada. Frames saltados por no-movimiento: {skipped_frames}")
