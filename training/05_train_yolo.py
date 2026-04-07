from ultralytics import YOLO

def main():
    model = YOLO("yolov8n.pt")

    model.train(
        data="drone.yaml",
        epochs=50,
        imgsz=640,
        batch=8,
        device=0,        # usa GPU
        save_period=5,   # checkpoint cada 5 épocas
        cache=False
    )

if __name__ == "__main__":
    main()
