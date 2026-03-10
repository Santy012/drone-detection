from ultralytics import YOLO
from pathlib import Path
from datetime import datetime
import sys
import csv
import yaml
import hashlib
import os

# --------------------
# CONFIGURACIÓN
# --------------------

MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "best.pt"

# VIDEO POR ARGUMENTO
if len(sys.argv) < 2:
    raise ValueError(
        "Debe proporcionar la ruta del video.\n"
        "Uso: python predict_video.py ruta/al/video.mp4"
    )

VIDEO_PATH = Path(sys.argv[1])

'''
# VIDEO POR DEFECTO
VIDEO_PATH = Path("data/videos/test_video.mp4") # El video que quieres analizar
'''

if not VIDEO_PATH.exists():
    raise FileNotFoundError(f"No se encontró el video: {VIDEO_PATH}")

CONF_THRES = 0.4
DEVICE = "cpu"
IOU = 0.5
TRACKER_CONFIG = "bytetrack.yaml"  # Cambia aquí si usas custom_bytetrack.yaml

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

COMPARISON_FILE = LOGS_DIR / "tracker_comparison_rgb.csv"

# --------------------
# CARGAR MODELO
# --------------------

model = YOLO(MODEL_PATH)

# --------------------
# CARGAR CONFIGURACIÓN DEL TRACKER
# --------------------

tracker_params = {}
tracker_hash = "N/A"
tracker_path = Path(TRACKER_CONFIG)

# Caso 1: tracker personalizado en tu proyecto
if tracker_path.exists():
    with open(tracker_path, "r", encoding="utf-8") as f:
        tracker_params = yaml.safe_load(f)
    with open(tracker_path, "rb") as f:
        tracker_hash = hashlib.md5(f.read()).hexdigest()

# Caso 2: tracker interno de Ultralytics
else:
    try:
        import ultralytics
        ultralytics_path = Path(ultralytics.__file__).parent
        default_tracker = ultralytics_path / "cfg" / "trackers" / TRACKER_CONFIG

        if default_tracker.exists():
            with open(default_tracker, "r", encoding="utf-8") as f:
                tracker_params = yaml.safe_load(f)
            with open(default_tracker, "rb") as f:
                tracker_hash = hashlib.md5(f.read()).hexdigest()
    except Exception:
        pass

# --------------------
# INFERENCIA CON TRACKING
# --------------------

results = model.track(
    source=str(VIDEO_PATH),
    conf=CONF_THRES,
    device=DEVICE,
    iou=IOU,
    tracker=TRACKER_CONFIG,
    persist=True,
    save=True,
    show=True
)

print("Inferencia finalizada, procesando métricas...")

# --------------------
# CONTADORES Y MÉTRICAS
# --------------------

total_frames = len(results)
frames_with_detection = 0
frames_without_detection = 0

unique_ids = set()
id_frame_count = {}

for r in results:
    if r.boxes is not None and len(r.boxes) > 0:
        frames_with_detection += 1

        for box in r.boxes:
            if box.id is not None:
                track_id = int(box.id[0])
                unique_ids.add(track_id)

                if track_id not in id_frame_count:
                    id_frame_count[track_id] = 0
                id_frame_count[track_id] += 1
    else:
        frames_without_detection += 1

ratio_detected = frames_with_detection / total_frames if total_frames > 0 else 0
ratio_not_detected = frames_without_detection / total_frames if total_frames > 0 else 0

total_unique_ids = len(unique_ids)
avg_frames_per_id = (
    sum(id_frame_count.values()) / total_unique_ids
    if total_unique_ids > 0 else 0
)

# --------------------
# CREAR ARCHIVO MARKDOWN INDIVIDUAL
# --------------------

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
md_filename = LOGS_DIR / f"{timestamp}_{VIDEO_PATH.stem}.md"

with open(md_filename, "w", encoding="utf-8") as f:
    f.write("# Registro de Inferencia – Detección de Drones\n\n")

    f.write("## Información general\n")
    f.write(f"- Fecha y hora: {timestamp}\n")
    f.write(f"- Modelo: {MODEL_PATH}\n")
    f.write(f"- Video: {VIDEO_PATH.name}\n")
    f.write(f"- Ruta del video: {VIDEO_PATH}\n")
    f.write(f"- Conf: {CONF_THRES}\n")
    f.write(f"- IOU: {IOU}\n")
    f.write(f"- Tracker: {TRACKER_CONFIG}\n")
    f.write(f"- Tracker hash: {tracker_hash}\n\n")

    f.write("## Parámetros del Tracker\n")
    for key, value in tracker_params.items():
        f.write(f"- {key}: {value}\n")

    f.write("\n## Resultados\n")
    f.write(f"- Total frames: {total_frames}\n")
    f.write(f"- Frames con detección: {frames_with_detection}\n")
    f.write(f"- Frames sin detección: {frames_without_detection}\n")
    f.write(f"- Ratio detección: {ratio_detected:.4f}\n")
    f.write(f"- IDs únicos detectados: {total_unique_ids}\n")
    f.write(f"- Promedio frames por ID: {avg_frames_per_id:.2f}\n")

print(f"Registro individual guardado en: {md_filename}")

# --------------------
# ARCHIVO COMPARATIVO GLOBAL (ACUMULATIVO)
# --------------------

file_exists = COMPARISON_FILE.exists()

with open(COMPARISON_FILE, mode="a", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)

    if not file_exists:
        writer.writerow([
            "timestamp",
            "video",
            "modelo",
            "tracker",
            "tracker_hash",
            "conf",
            "iou",
            "track_high_thresh",
            "track_low_thresh",
            "new_track_thresh",
            "track_buffer",
            "match_thresh",
            "total_frames",
            "ratio_detected",
            "unique_ids",
            "avg_frames_per_id"
        ])

    writer.writerow([
        timestamp,
        VIDEO_PATH.name,
        MODEL_PATH.name,
        TRACKER_CONFIG,
        tracker_hash,
        CONF_THRES,
        IOU,
        tracker_params.get("track_high_thresh"),
        tracker_params.get("track_low_thresh"),
        tracker_params.get("new_track_thresh"),
        tracker_params.get("track_buffer"),
        tracker_params.get("match_thresh"),
        total_frames,
        f"{ratio_detected:.4f}",
        total_unique_ids,
        f"{avg_frames_per_id:.2f}"
    ])

print(f"Comparación acumulativa actualizada en: {COMPARISON_FILE}")