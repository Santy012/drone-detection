import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import sys
import csv

# --------------------
# CONFIGURACIÓN
# --------------------

MODEL_PATH = Path("best.onnx")

if len(sys.argv) < 2:
    raise ValueError(
        "Debe proporcionar la ruta del video.\n"
        "Uso: python predict_video_onnx.py ruta/al/video.mp4"
    )

VIDEO_PATH = Path(sys.argv[1])

if not VIDEO_PATH.exists():
    raise FileNotFoundError(f"No se encontro el video: {VIDEO_PATH}")
if not MODEL_PATH.exists():
    raise FileNotFoundError(f"No se encontro el modelo: {MODEL_PATH}")

CONF_THRES = 0.4
IOU_THRES = 0.5
INPUT_SIZE = 640

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

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
    # output shape: [1, 5, 8400] -> transpose a [8400, 5]
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

# --------------------
# CARGAR MODELO ONNX CON OpenCV DNN
# --------------------

print(f"Cargando modelo: {MODEL_PATH}")
print(f"OpenCV version: {cv2.__version__}")

net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

print("Modelo cargado exitosamente con cv2.dnn")

# --------------------
# INFERENCIA
# --------------------

cap = cv2.VideoCapture(str(VIDEO_PATH))
if not cap.isOpened():
    raise RuntimeError(f"No se pudo abrir el video: {VIDEO_PATH}")

fps = cap.get(cv2.CAP_PROP_FPS)
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

output_path = OUTPUT_DIR / f"{VIDEO_PATH.stem}_detected.mp4"
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

print(f"Video: {VIDEO_PATH.name} ({width}x{height} @ {fps:.1f}fps, {total_video_frames} frames)")
print("Procesando...")

total_frames = 0
frames_with_detection = 0
frames_without_detection = 0
all_confidences = []

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Preprocesar: letterbox + blob
    img_lb, scale, (pad_x, pad_y) = letterbox(frame, INPUT_SIZE)
    blob = cv2.dnn.blobFromImage(img_lb, 1.0 / 255.0, (INPUT_SIZE, INPUT_SIZE),
                                  swapRB=True, crop=False)

    # Inferencia
    net.setInput(blob)
    output = net.forward()  # shape: [1, 5, 8400]

    # Postprocesar
    detections = postprocess(output, scale, pad_x, pad_y, height, width)

    total_frames += 1
    if len(detections) > 0:
        frames_with_detection += 1
        for d in detections:
            all_confidences.append(d[4])
    else:
        frames_without_detection += 1

    annotated = draw_detections(frame.copy(), detections)
    writer.write(annotated)

    if total_frames % 100 == 0:
        print(f"  Frame {total_frames}/{total_video_frames} "
              f"({total_frames/total_video_frames*100:.0f}%) - "
              f"Detecciones: {len(detections)}")

cap.release()
writer.release()

print(f"\nInferencia finalizada. Video anotado: {output_path}")

# --------------------
# METRICAS
# --------------------

ratio_detected = frames_with_detection / total_frames if total_frames > 0 else 0
avg_confidence = np.mean(all_confidences) if all_confidences else 0
total_detections = len(all_confidences)

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
md_filename = LOGS_DIR / f"{timestamp}_{VIDEO_PATH.stem}_onnx.md"

with open(md_filename, "w", encoding="utf-8") as f:
    f.write("# Registro de Inferencia - Deteccion de Drones (OpenCV DNN + ONNX)\n\n")
    f.write("## Informacion general\n")
    f.write(f"- Fecha y hora: {timestamp}\n")
    f.write(f"- Modelo: {MODEL_PATH}\n")
    f.write(f"- Runtime: OpenCV DNN {cv2.__version__}\n")
    f.write(f"- Video: {VIDEO_PATH.name}\n")
    f.write(f"- Resolucion: {width}x{height} @ {fps:.1f}fps\n")
    f.write(f"- Conf threshold: {CONF_THRES}\n")
    f.write(f"- IOU threshold: {IOU_THRES}\n\n")
    f.write("## Resultados\n")
    f.write(f"- Total frames: {total_frames}\n")
    f.write(f"- Frames con deteccion: {frames_with_detection}\n")
    f.write(f"- Frames sin deteccion: {frames_without_detection}\n")
    f.write(f"- Ratio deteccion: {ratio_detected:.4f}\n")
    f.write(f"- Total detecciones: {total_detections}\n")
    f.write(f"- Confianza promedio: {avg_confidence:.4f}\n")

print(f"Registro guardado en: {md_filename}")

COMPARISON_FILE = LOGS_DIR / "onnx_comparison.csv"
file_exists = COMPARISON_FILE.exists()

with open(COMPARISON_FILE, mode="a", newline="", encoding="utf-8") as csvfile:
    csv_writer = csv.writer(csvfile)
    if not file_exists:
        csv_writer.writerow([
            "timestamp", "video", "modelo", "runtime",
            "conf_threshold", "iou_threshold", "total_frames",
            "frames_with_detection", "ratio_detected",
            "total_detections", "avg_confidence"
        ])
    csv_writer.writerow([
        timestamp, VIDEO_PATH.name, MODEL_PATH.name,
        f"opencv-dnn-{cv2.__version__}", CONF_THRES, IOU_THRES,
        total_frames, frames_with_detection, f"{ratio_detected:.4f}",
        total_detections, f"{avg_confidence:.4f}"
    ])

print(f"Comparacion actualizada en: {COMPARISON_FILE}")
