# Drone Detection System

Sistema de deteccion de drones en tiempo real mediante vision por computadora (YOLOv8n) con backend serverless en AWS.

## Arquitectura

```
Laptop (webcam + inferencia ONNX)
  |
  |-- POST /presign  --> API Gateway --> presign-handler Lambda --> presigned URL S3
  |-- PUT imagen     --> S3 (annotated/{device}/{fecha}/{ts}.jpg)
  |-- POST /detections --> API Gateway --> detection-handler Lambda --> DynamoDB
                                              |-- invoca notify-handler Lambda --> Telegram
```

- **Inferencia local:** webcam + cv2.dnn + modelo ONNX (~10 FPS en CPU)
- **Backend cloud:** AWS Lambda + API Gateway + S3 + DynamoDB
- **Notificaciones:** Bot de Telegram con cooldown de 30s

## Estructura del proyecto

```
Drone Detection/
├── inference/          # Scripts de inferencia
│   ├── detect_webcam.py        # Deteccion en tiempo real (webcam + cloud)
│   ├── predict_video.py        # Inferencia con Ultralytics (referencia)
│   └── predict_video_onnx.py   # Inferencia con cv2.dnn (pipeline propio)
├── model/              # Modelo entrenado
│   ├── best.pt                 # Modelo PyTorch original (6.2MB)
│   ├── best.onnx               # Modelo exportado a ONNX
│   └── export_onnx.py          # Script de exportacion
├── terraform/          # Infraestructura AWS (Terraform)
│   ├── main.tf, variables.tf, s3.tf, dynamodb.tf
│   ├── lambda.tf, api_gateway.tf, outputs.tf
│   └── README.md               # Guia de deploy
├── lambdas/            # Codigo fuente de Lambdas
│   ├── presign_handler/        # Genera presigned URL de S3
│   ├── detection_handler/      # Gestion eventos DynamoDB
│   └── notify_handler/         # Cooldown + envio Telegram
├── training/           # Scripts de entrenamiento (completado)
├── docs/               # Documentacion tecnica
├── data/               # Videos de prueba
└── output/             # Resultados de ejecucion
```

## Modelo

| Metrica | Valor |
|---------|-------|
| Arquitectura | YOLOv8n (3.2M parametros) |
| Clase | drone (unica) |
| mAP50 | 99.25% |
| Precision | 99.1% |
| Recall | 98.8% |
| Input | 640x640 RGB |
| Runtime | cv2.dnn (CPU) |

## Requisitos

- Python 3.10+
- OpenCV (`pip install opencv-python`)
- Terraform >= 1.5 (para infraestructura AWS)
- AWS CLI configurado
- Bot de Telegram (para notificaciones)

## Uso rapido

### Deteccion local (solo webcam)

```bash
python inference/detect_webcam.py
```

Controles: `q` salir, `m` toggle filtro de movimiento.

### Deteccion con reporte a AWS

```bash
python inference/detect_webcam.py \
  --api-url https://xxxxx.execute-api.us-east-1.amazonaws.com/v1 \
  --device-id laptop-01
```

### Deploy de infraestructura AWS

Ver [terraform/README.md](terraform/README.md) para instrucciones completas.

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars con lab_role_arn, telegram_bot_token, telegram_chat_id
terraform init
terraform apply
```

## Estado del proyecto

- [x] A1 — Deteccion en tiempo real desde webcam (~10 FPS CPU)
- [x] A2 — Prefiltro de movimiento (ahorra ~85% CPU)
- [ ] A3 — Validacion ONNX vs Ultralytics
- [x] A4 — Infraestructura AWS con Terraform (desplegada)
- [x] A5 — Bot Telegram + notify-handler con cooldown
- [ ] A6 — Integracion E2E: webcam → AWS → Telegram
- [ ] A7 — Pruebas de estabilidad

## Hardware

- **Desarrollo:** Laptop Windows 11, sin GPU dedicada
- **Edge (futuro):** Raspberry Pi 3B+ (solo captura, sin IA)
- **Cloud:** AWS Lambda (Python 3.11, 128MB)
