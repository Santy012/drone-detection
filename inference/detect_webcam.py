"""
Deteccion de drones en tiempo real desde webcam.
Usa Ultralytics YOLOv8 con modelo best.pt.
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
from ultralytics import YOLO

# --------------------
# ARGUMENTOS
# --------------------

parser = argparse.ArgumentParser(description="Deteccion de drones en tiempo real")
parser.add_argument("--source", default="0", help="Indice de webcam (0, 1, ...) o URL RTSP")
parser.add_argument("--model", default=str(Path(__file__).parent.parent / "model" / "best.pt"),
                    help="Ruta al modelo .pt")
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
# FUNCIONES AUXILIARES
# --------------------

def detect_motion(gray_curr, gray_prev, threshold):
    """Detecta movimiento comparando dos frames en escala de grises.
    Retorna (hay_movimiento, cantidad_pixeles_cambiados)."""
    if gray_prev is None:
        return True, 0
    diff = cv2.absdiff(gray_curr, gray_prev)
    _, thresh_img = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    changed_pixels = cv2.countNonZero(thresh_img)
    return changed_pixels > threshold, changed_pixels


def draw_detections(frame, detections):
    for (x1, y1, x2, y2, conf) in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"drone {conf:.2f}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - label_size[1] - 6), (x1 + label_size[0], y1), (0, 255, 0), -1)
        cv2.putText(frame, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return frame


def draw_hud(frame, fps, num_detections, motion_active, has_motion, motion_pixels):
    h, w = frame.shape[:2]
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(frame, f"Detecciones: {num_detections}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    if motion_active:
        motion_color = (0, 255, 0) if has_motion else (0, 0, 255)
        motion_text = f"Movimiento: {'SI' if has_motion else 'NO'} ({motion_pixels}px)"
        cv2.putText(frame, motion_text, (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, motion_color, 2)
    else:
        cv2.putText(frame, "Movimiento: OFF", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)
    cv2.putText(frame, "'q' salir | 'm' toggle movimiento", (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return frame

# --------------------
# CARGAR MODELO
# --------------------

print(f"Cargando modelo: {MODEL_PATH}")
model = YOLO(str(MODEL_PATH))
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
        results = model.predict(frame, conf=CONF_THRES, iou=IOU_THRES, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])
                detections.append((x1, y1, x2, y2, conf))
    else:
        detections = []
        skipped_frames += 1

    # Calcular FPS
    curr_time = time.time()
    fps = 0.7 * fps + 0.3 * (1.0 / (curr_time - prev_time + 1e-9))
    prev_time = curr_time

    # Reportar al cloud si hay detecciones y paso el cooldown
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
