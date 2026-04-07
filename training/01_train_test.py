from ultralytics import YOLO
import torch

print("CUDA available:", torch.cuda.is_available())
print("Using device:", "cuda" if torch.cuda.is_available() else "cpu")

model = YOLO("yolov8n.pt")

print("Model loaded successfully")
