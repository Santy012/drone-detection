import cv2
import json
import os
from pathlib import Path

# CONFIGURACIÓN

ROOT = Path("F:/Datasets/Drones/Anti-UAV-RGBT")
SPLITS = ["train", "val", "test"]

OUTPUT_ROOT = ROOT / "dataset_yolo"
FRAME_STRIDE = 5      # extraer 1 frame cada N
CLASS_ID = 0          # drone


# CREAR ESTRUCTURA YOLO

for split in SPLITS:
    (OUTPUT_ROOT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "labels" / split).mkdir(parents=True, exist_ok=True)


# FUNCIÓN PRINCIPAL

def process_sequence(seq_dir: Path, split: str):
    video_path = seq_dir / "visible.mp4"
    json_path = seq_dir / "visible.json"

    if not video_path.exists() or not json_path.exists():
        print(f"⚠️  Saltando {seq_dir.name} (faltan archivos)")
        return

    # Leer JSON
    with open(json_path, "r") as f:
        data = json.load(f)

    exist = data["exist"]
    gt_rect = data["gt_rect"]

    # Abrir video
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"❌ No se pudo abrir video {video_path}")
        return

    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frame_idx = 0
    saved = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx < len(exist):
            if exist[frame_idx] == 1 and frame_idx % FRAME_STRIDE == 0:
                x, y, w, h = gt_rect[frame_idx]

                # Conversión YOLO
                x_center = (x + w / 2) / W
                y_center = (y + h / 2) / H
                w_norm = w / W
                h_norm = h / H

                # Nombres
                name = f"{seq_dir.name}_f{frame_idx:06d}"
                img_out = OUTPUT_ROOT / "images" / split / f"{name}.jpg"
                lbl_out = OUTPUT_ROOT / "labels" / split / f"{name}.txt"

                # Guardar imagen
                cv2.imwrite(str(img_out), frame)

                # Guardar label
                with open(lbl_out, "w") as f:
                    f.write(f"{CLASS_ID} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}\n")

                saved += 1

        frame_idx += 1

    cap.release()
    print(f"✅ {seq_dir.name}: {saved} frames guardados")



# EJECUCIÓN

for split in SPLITS:
    split_dir = ROOT / split
    print(f"\n🔹 Procesando split: {split}")

    for seq in split_dir.iterdir():
        if seq.is_dir():
            process_sequence(seq, split)

print("\n🎉 Dataset YOLO generado correctamente")
