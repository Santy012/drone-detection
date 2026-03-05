import cv2
import random
from pathlib import Path

# =====================
# CONFIG
# =====================
DATASET = Path("F:/Datasets/Drones/Anti-UAV-RGBT/dataset_yolo")
SPLIT = "train"        # puedes cambiar a val / test
NUM_SAMPLES = 5

images_dir = DATASET / "images" / SPLIT
labels_dir = DATASET / "labels" / SPLIT

images = list(images_dir.glob("*.jpg"))
samples = random.sample(images, NUM_SAMPLES)

for img_path in samples:
    label_path = labels_dir / (img_path.stem + ".txt")

    img = cv2.imread(str(img_path))
    h, w, _ = img.shape

    if not label_path.exists():
        print(f"❌ Sin label: {img_path.name}")
        continue

    with open(label_path) as f:
        for line in f:
            cls, xc, yc, bw, bh = map(float, line.split())

            # YOLO → píxeles
            x1 = int((xc - bw / 2) * w)
            y1 = int((yc - bh / 2) * h)
            x2 = int((xc + bw / 2) * w)
            y2 = int((yc + bh / 2) * h)

            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, "drone", (x1, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

    cv2.imshow("YOLO CHECK", img)
    cv2.waitKey(0)

cv2.destroyAllWindows()
