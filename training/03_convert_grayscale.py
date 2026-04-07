"""
convert_to_grayscale.py
Convierte las imágenes de un dataset YOLO a escala de grises.
Las labels (.txt) se copian sin modificar (los bounding boxes son agnósticos al color).

Uso:
    python convert_to_grayscale.py                    # convierte ambos datasets
    python convert_to_grayscale.py --dataset dataset_personalizado
    python convert_to_grayscale.py --dataset dataset_v_yolo
    python convert_to_grayscale.py --in-place         # sobreescribe originales (¡cuidado!)
"""

import cv2
import shutil
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DATASET_ROOT = Path("C:/Users/LENOVO/Downloads/Drone-detection-dataset-master/Drone-detection-dataset-master/Data")

DATASETS = ["dataset_personalizado", "dataset_v_yolo"]
SPLITS   = ["train", "val"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}

MAX_WORKERS = 8   # hilos paralelos para conversión

# ──────────────────────────────────────────────────────────────────────────────


def convert_image(src: Path, dst: Path):
    """Lee una imagen, la convierte a gris (1 canal guardado como BGR) y la guarda."""
    img = cv2.imread(str(src))
    if img is None:
        print(f"  ⚠️  No se pudo leer: {src.name}")
        return False

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Guardamos como PNG para no perder calidad; si el original era jpg se mantiene extensión
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), gray)
    return True


def process_dataset(dataset_name: str, in_place: bool):
    src_root = DATASET_ROOT / dataset_name

    if in_place:
        dst_root = src_root
        print(f"\n[{dataset_name}]  ⚠️  Modo IN-PLACE: se sobreescribirán las originales")
    else:
        dst_root = DATASET_ROOT / (dataset_name + "_grayscale")
        print(f"\n[{dataset_name}]  Destino: {dst_root}")

    total_ok = 0
    total_fail = 0

    for split in SPLITS:
        images_src = src_root / split / "images"
        labels_src = src_root / split / "labels"

        if not images_src.exists():
            print(f"  ⚠️  No existe {images_src}, saltando.")
            continue

        images_dst = dst_root / split / "images"
        labels_dst = dst_root / split / "labels"

        # Recopilar imágenes
        img_files = [p for p in images_src.iterdir() if p.suffix.lower() in IMG_EXTS]
        print(f"  [{split}] {len(img_files)} imágenes encontradas", end=" ", flush=True)

        # Convertir en paralelo
        ok = fail = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(convert_image, img, images_dst / img.name): img
                for img in img_files
            }
            for i, future in enumerate(as_completed(futures), 1):
                if future.result():
                    ok += 1
                else:
                    fail += 1
                if i % 1000 == 0:
                    print(f"    ... {i}/{len(img_files)}", flush=True)

        print(f"→ {ok} OK, {fail} errores")
        total_ok += ok
        total_fail += fail

        # Copiar labels si no es in-place
        if not in_place and labels_src.exists():
            labels_dst.mkdir(parents=True, exist_ok=True)
            for lbl in labels_src.iterdir():
                shutil.copy2(lbl, labels_dst / lbl.name)
            print(f"  [{split}] Labels copiados: {sum(1 for _ in labels_src.iterdir())}")

        # Copiar dataset_info.txt si existe
        info = src_root / "dataset_info.txt"
        if not in_place and info.exists():
            shutil.copy2(info, dst_root / "dataset_info.txt")

    print(f"  Total: {total_ok} convertidas, {total_fail} con error")
    if not in_place:
        print(f"  Dataset generado en: {dst_root}")


def main():
    parser = argparse.ArgumentParser(description="Convierte imágenes de dataset YOLO a escala de grises")
    parser.add_argument("--dataset", choices=DATASETS, default=None,
                        help="Procesar solo un dataset (por defecto procesa ambos)")
    parser.add_argument("--in-place", action="store_true",
                        help="Sobreescribir imágenes originales (irreversible)")
    args = parser.parse_args()

    datasets = [args.dataset] if args.dataset else DATASETS

    print(f"Modo: {'IN-PLACE (sobreescritura)' if args.in_place else 'nuevo dataset _grayscale'}")
    print(f"Datasets a procesar: {datasets}")

    for ds in datasets:
        if not (DATASET_ROOT / ds).exists():
            print(f"⚠️  No encontrado: {DATASET_ROOT / ds}")
            continue
        process_dataset(ds, in_place=args.in_place)

    print("\n✅ Conversión completada")


if __name__ == "__main__":
    main()
