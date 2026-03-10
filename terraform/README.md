# Infraestructura AWS — Drone Detection

Backend serverless para el sistema de deteccion de drones. Recibe snapshots anotados desde `detect_webcam.py`, los almacena en S3, registra eventos en DynamoDB y notifica via Telegram.

## Requisitos previos

1. **Terraform >= 1.5** — [Instalar](https://developer.hashicorp.com/terraform/install)

   ```bash
   terraform -version
   ```

2. **AWS CLI configurado** con credenciales que tengan permisos para crear S3, DynamoDB, Lambda, API Gateway e IAM.

   ```bash
   aws configure
   # Verificar acceso:
   aws sts get-caller-identity
   ```

3. **Bot de Telegram** — Crear uno con [@BotFather](https://t.me/BotFather) y obtener:
   - `telegram_bot_token`: el token del bot (formato `123456:ABC-DEF...`)
   - `telegram_chat_id`: ID del chat/grupo donde enviara alertas

   Para obtener el chat ID, agrega el bot al grupo y consulta:
   ```bash
   curl https://api.telegram.org/bot<TU_TOKEN>/getUpdates
   ```
   Busca `"chat":{"id": -100XXXXXXXXXX}` en la respuesta.

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `main.tf` | Provider AWS, random suffix para nombres unicos |
| `variables.tf` | Variables: region, telegram_bot_token, telegram_chat_id |
| `s3.tf` | Bucket de snapshots con lifecycle (raw/ 24h, annotated/ 30d) |
| `dynamodb.tf` | Tablas DroneEvents (PK: device_id, SK: event_id) y DroneDetections (PK: event_id, SK: timestamp) |
| `lambda.tf` | 3 funciones Lambda + roles IAM least-privilege + empaquetado ZIP |
| `api_gateway.tf` | REST API con endpoints POST /presign y POST /detections |
| `outputs.tf` | URLs y nombres de recursos creados |

## Inicializacion

### 1. Crear archivo de variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Editar `terraform.tfvars` con valores reales:

```hcl
aws_region         = "us-east-1"
telegram_bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
telegram_chat_id   = "-1001234567890"
```

> **IMPORTANTE:** `terraform.tfvars` contiene secrets y esta excluido en `.gitignore`. No commitear este archivo.

### 2. Inicializar Terraform

```bash
cd terraform
terraform init
```

Esto descarga los providers (AWS ~> 5.0, random ~> 3.0) y prepara el directorio de trabajo.

### 3. Revisar el plan

```bash
terraform plan
```

Muestra todos los recursos que se van a crear sin aplicar cambios. Verificar que no haya errores.

Recursos esperados (~15):
- 1 S3 bucket + 1 lifecycle rule + 1 public access block
- 2 tablas DynamoDB (DroneEvents, DroneDetections)
- 3 funciones Lambda (presign, detection, notify)
- 3 roles IAM + 3 policies inline + 3 policy attachments
- 1 API Gateway REST + 2 resources + 2 methods + 2 integrations + 1 deployment + 1 stage
- 2 Lambda permissions para API Gateway

### 4. Aplicar infraestructura

```bash
terraform apply
```

Escribir `yes` cuando pregunte. Tarda ~1-2 minutos.

Al finalizar, muestra los outputs:

```
api_url          = "https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/v1"
s3_bucket        = "drone-detection-snapshots-a1b2c3d4"
events_table     = "DroneEvents"
detections_table = "DroneDetections"
```

### 5. Verificar el deploy

Probar el endpoint presign:

```bash
curl -X POST $(terraform output -raw api_url)/presign \
  -H "Content-Type: application/json" \
  -d '{"device_id": "test-device"}'
```

Respuesta esperada:

```json
{
  "upload_url": "https://drone-detection-snapshots-xxxx.s3.amazonaws.com/annotated/...",
  "s3_key": "annotated/test-device/2026-03-05/1709654321.jpg"
}
```

## Uso con detect_webcam.py

Una vez desplegada la infraestructura:

```bash
cd ..
python inference/detect_webcam.py \
  --api-url $(cd terraform && terraform output -raw api_url) \
  --device-id laptop-01
```

O copiar la URL manualmente:

```bash
python inference/detect_webcam.py \
  --api-url https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/v1 \
  --device-id laptop-01
```

Cuando detecte un dron:
1. Sube snapshot anotado a S3
2. Registra evento en DynamoDB
3. Envia foto + alerta al chat de Telegram (cooldown 30s entre mensajes)

## Destruir infraestructura

Para eliminar todos los recursos creados:

```bash
terraform destroy
```

Escribir `yes` para confirmar. Esto elimina S3 (debe estar vacio), DynamoDB, Lambdas, API Gateway y roles IAM.

> Si el bucket S3 tiene objetos, vaciarlos primero:
> ```bash
> aws s3 rm s3://$(terraform output -raw s3_bucket) --recursive
> ```

## Costos estimados

Todos los recursos usan tier gratuito o pay-per-request:

| Recurso | Costo |
|---------|-------|
| Lambda | Gratis hasta 1M invocaciones/mes |
| API Gateway | Gratis hasta 1M requests/mes (12 meses) |
| DynamoDB | Gratis hasta 25GB + 25 WCU/RCU |
| S3 | Gratis hasta 5GB (12 meses) |

Para uso de desarrollo/pruebas, el costo esperado es **$0/mes**.

## Troubleshooting

| Problema | Solucion |
|----------|----------|
| `terraform init` falla | Verificar que Terraform >= 1.5 esta instalado |
| `Error: No valid credential sources` | Ejecutar `aws configure` con access key y secret key validos |
| `403 Forbidden` en API Gateway | Verificar que el deploy fue exitoso con `terraform apply` |
| Telegram no envia mensajes | Verificar token y chat_id. El bot debe estar agregado al grupo |
| `[cloud] Error: ConnectionError` en detect_webcam.py | Verificar la URL de API con `terraform output api_url` |
