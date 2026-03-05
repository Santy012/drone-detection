# SISTEMA HIBRIDO DE DETECCION DE DRONES: EDGE + CLOUD (SERVERLESS)

**Proyecto:** Deteccion de Drones con YOLOv8 - Arquitectura Hibrida Serverless
**Version:** 2.0
**Fecha:** Febrero 2026

---

# TABLA DE CONTENIDOS

1. [Introduccion](#1-introduccion)
2. [Objetivo](#2-objetivo)
3. [Requerimientos Funcionales](#3-requerimientos-funcionales)
4. [Requerimientos No Funcionales](#4-requerimientos-no-funcionales)
5. [Arquitectura del Sistema](#5-arquitectura-del-sistema)
6. [Flujo de Datos](#6-flujo-de-datos)
7. [Tecnologias](#7-tecnologias)
8. [Diagramas](#8-diagramas)
9. [Politicas de Cadencia](#9-politicas-de-cadencia)
10. [Gestion de Eventos](#10-gestion-de-eventos)
11. [Alternativas de Hardware](#11-alternativas-de-hardware)
12. [Upgrade: Kit Vilros Pi 4 4GB](#12-upgrade-kit-vilros-pi-4-4gb)
13. [Costos AWS](#13-costos-aws)
14. [Plan de Implementacion](#14-plan-de-implementacion)
15. [Riesgos](#15-riesgos)

---

# 1. INTRODUCCION

El modelo YOLOv8n entrenado con Anti-UAV-RGBT alcanza mAP50 de 99.25%, pero ejecutarlo en una Raspberry Pi 3B+ (1GB RAM, CPU ARM Cortex-A53) es inviable: apenas 0.5-1.5 FPS.

Este documento describe una arquitectura **100% serverless en AWS** que delega la inferencia a la nube. El Pi 3B+ actua unicamente como dispositivo de captura con deteccion de movimiento basica (sin IA). Toda la logica de negocio, inferencia y notificacion ocurre en servicios serverless de AWS (Lambda, API Gateway, DynamoDB, S3).

### Modelo entrenado

| Metrica | Valor |
|---------|-------|
| Modelo | YOLOv8n (3.2M params) |
| mAP50 | 99.25% |
| Precision / Recall | 99.1% / 98.8% |
| Formato | `.pt` -> exportar a ONNX INT8 para Lambda |
| Clase | `drone` (unica) |

### Hardware disponible

| Componente | Modelo | Limitacion clave |
|------------|--------|-----------------|
| Edge device | Raspberry Pi 3 Model B+ | 1GB RAM, sin GPU, CPU lento |
| Camara | EZVIZ H1C (1080p, RTSP, FOV 130) | Solo WiFi 2.4GHz |
| Cloud | AWS (servicios serverless) | Cold starts en Lambda |

---

# 2. OBJETIVO

Disenar un sistema hibrido serverless que detecte drones en tiempo real combinando captura edge (Pi 3B+) con inferencia cloud (AWS Lambda), con latencia end-to-end < 3 segundos y costo < $15 USD/mes para 1 camara.

### Objetivos especificos

1. Captura inteligente en Pi con deteccion de movimiento (sin IA)
2. Inferencia con Lambda + ONNX cuantizado en < 500ms por imagen
3. Pipeline event-driven: S3 trigger -> Lambda inferencia -> DynamoDB -> Telegram
4. Comunicacion reactiva Pi <-> nube via WebSocket (API Gateway)
5. Notificacion a Telegram con imagen anotada en < 5s desde captura

---

# 3. REQUERIMIENTOS FUNCIONALES

| ID | Requerimiento |
|----|---------------|
| RF-01 | Conectarse al stream RTSP de la EZVIZ H1C y capturar frames |
| RF-02 | Detectar movimiento por diferencia de frames (absdiff, sin IA) |
| RF-03 | Subir snapshots a S3 via presigned URL (sin credenciales AWS en Pi) |
| RF-04 | Disparar inferencia YOLOv8 (ONNX INT8) automaticamente al llegar imagen a S3 |
| RF-05 | Gestionar eventos de deteccion (PENDING -> ACTIVE -> ENDED) en DynamoDB |
| RF-06 | Notificar a Telegram con imagen + bounding box + metricas |
| RF-07 | Comunicar cambios de modo (NORMAL/ALERTA) al Pi via WebSocket |
| RF-08 | Eliminar snapshots sin deteccion tras 24h (S3 lifecycle) |

---

# 4. REQUERIMIENTOS NO FUNCIONALES

| ID | Requerimiento | Umbral |
|----|---------------|--------|
| RNF-01 | Latencia end-to-end | < 3 segundos |
| RNF-02 | Latencia de inferencia | < 500ms |
| RNF-03 | Costo mensual (1 camara) | < $15 USD |
| RNF-04 | CPU del Pi en modo normal | < 40% |
| RNF-05 | Disponibilidad cloud | > 99.5% |
| RNF-06 | Soporte multi-camara | Hasta 5 sin cambios arquitectonicos |
| RNF-07 | Seguridad | HTTPS, presigned URLs con TTL 60s, sin creds en edge |
| RNF-08 | Resiliencia | Reconexion RTSP automatica, cola local en Pi |

---

# 5. ARQUITECTURA DEL SISTEMA

## 5.1 Principios de diseño

1. **Full serverless**: Sin servidores persistentes. Costo $0 cuando no hay actividad.
2. **El Pi no hace IA**: Solo captura + deteccion de movimiento (absdiff).
3. **S3 como bus de eventos**: La llegada de un objeto dispara la inferencia.
4. **WebSocket para reactividad**: La nube empuja cambios de modo al Pi en tiempo real.
5. **DynamoDB nativo**: Sin drivers externos, sin connection pooling desde Lambda.

## 5.2 Componentes

### Raspberry Pi 3B+ (Edge)
- Captura RTSP desde EZVIZ H1C
- Deteccion de movimiento (OpenCV absdiff, < 5% CPU)
- Compresion JPEG (640x480, calidad 80%, ~60KB)
- Solicita presigned URL a API Gateway
- Sube snapshot directo a S3
- Escucha WebSocket para cambios de modo

### AWS API Gateway
- **REST API**: Endpoint `/presign` para generar presigned URLs
- **WebSocket API**: Canal bidireccional para empujar modo NORMAL/ALERTA al Pi

### AWS Lambda (3 funciones)
- **presign-handler**: Genera presigned URLs de subida a S3
- **inference-handler**: Descarga imagen de S3, ejecuta ONNX, registra resultado
- **notify-handler**: Evalua cooldown, envia a Telegram si corresponde

### AWS S3
- Bucket `drone-snapshots/raw/` y `drone-snapshots/annotated/`
- Trigger `ObjectCreated` en `raw/` -> invoca `inference-handler`
- Lifecycle: eliminar `raw/` sin deteccion tras 24h

### DynamoDB
- Tabla `Events`: estado de eventos (PENDING/ACTIVE/ENDED)
- Tabla `Detections`: cada deteccion con snapshot_key, conf, bbox
- Tabla `Connections`: WebSocket connection IDs de los Pi conectados

### Telegram Bot
- Recibe alertas: imagen con bbox + metricas humanizadas
- Cooldown: 30s entre mensajes, maximo 10 por evento

---

# 6. FLUJO DE DATOS

## 6.1 Flujo paso a paso

```
1. Pi detecta movimiento (absdiff)
2. Pi -> API Gateway REST: POST /presign {device_id, ts}
3. API Gateway -> Lambda presign-handler -> genera presigned URL
4. Lambda -> Pi: {url, s3_key, mode: "NORMAL", cadence_ms: 2000}
5. Pi -> S3: PUT snapshot via presigned URL (~60KB JPEG)
6. S3 ObjectCreated -> trigger -> Lambda inference-handler
7. Lambda descarga imagen, ejecuta ONNX, obtiene {class, conf, bbox}
8. SI deteccion positiva:
   a. Lambda dibuja bbox, sube imagen anotada a S3/annotated/
   b. Lambda escribe deteccion en DynamoDB (Detections + Events)
   c. Lambda invoca notify-handler (async)
   d. notify-handler verifica cooldown en DynamoDB
   e. Si pasa cooldown: envia foto + metricas a Telegram
   f. Lambda empuja {mode: "ALERT", cadence_ms: 1000} via WebSocket al Pi
9. SI no deteccion: Lambda registra "clean", no notifica
```

## 6.2 Tiempos estimados

| Paso | Tiempo |
|------|--------|
| Presigned URL request | 100-200ms |
| Upload JPEG a S3 | 200-400ms |
| S3 trigger a Lambda | 100-500ms |
| Inferencia ONNX en Lambda | 200-800ms |
| Registro en DynamoDB | 50-100ms |
| Envio a Telegram | 200-500ms |
| **Total end-to-end** | **~1.5-2.5s** (sin cold start) |

Cold start de Lambda (primera invocacion tras inactividad): **+5-15 segundos**.

---

# 7. TECNOLOGIAS

| Componente | Tecnologia | Justificacion |
|------------|------------|---------------|
| Edge OS | Raspberry Pi OS Lite 64-bit | Sin desktop, ligero |
| Edge captura | OpenCV headless + Python 3.11 | RTSP + motion detection |
| Edge HTTP | requests / websocket-client | Comunicacion con AWS |
| Cloud API | API Gateway (REST + WebSocket) | Serverless, pay-per-request |
| Cloud compute | Lambda (Python 3.11, 512MB-1GB) | Inferencia + logica |
| Cloud storage | S3 | Snapshots + evidencia |
| Cloud DB | DynamoDB (on-demand) | Estado, eventos, conexiones |
| Cloud modelo | ONNX Runtime (INT8 cuantizado) | Inferencia en CPU Lambda |
| Notificaciones | Telegram Bot API | Alertas con imagen |
| IaC | AWS SAM o CDK | Infraestructura reproducible |
| Monitoreo | CloudWatch | Logs, metricas, alarmas |

### Modelo: pipeline de conversion

```
best.pt (PyTorch, 6.2MB)
  -> ultralytics export format=onnx -> best.onnx (~6MB FP32)
    -> onnxruntime.quantization (INT8) -> best_int8.onnx (~2-3MB)
      -> empaquetado como Lambda Layer
```

---

# 8. DIAGRAMAS

## 8.1 Arquitectura cloud

```
                    +---[ Raspberry Pi 3B+ ]---+
                    |                          |
                    | EZVIZ H1C --RTSP--> Pi   |
                    | Pi: motion detection     |
                    | Pi: JPEG compress        |
                    +-----+--------+-----------+
                          |        ^
              HTTPS PUT   |        | WebSocket (modo ALERTA/NORMAL)
              presign req |        |
                          v        |
+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+
|                           AWS CLOUD                                      |
|                                                                          |
|  +--[ API Gateway ]---------------------------------------------+       |
|  |  REST: POST /presign -> Lambda presign-handler               |       |
|  |  WebSocket: wss://... -> connections en DynamoDB              |       |
|  +------+---------------------------------------------------+---+       |
|         |                                                    |           |
|         v                                                    |           |
|  +--[ S3 Bucket: drone-snapshots ]--+                        |           |
|  |  raw/{device}/{date}/{ts}.jpg    |                        |           |
|  |  annotated/{device}/{date}/...   |                        |           |
|  +------+---------------------------+                        |           |
|         |                                                    |           |
|         | S3 Event (ObjectCreated)                            |           |
|         v                                                    |           |
|  +--[ Lambda: inference-handler ]---+                        |           |
|  |  1. Descarga imagen de S3        |                        |           |
|  |  2. ONNX Runtime (INT8)          |                        |           |
|  |  3. Post-proceso (NMS, bbox)     |                        |           |
|  |  4. Si DRONE:                    |                        |           |
|  |     - Sube annotated a S3        |                        |           |
|  |     - Escribe DynamoDB           |     Empuja modo        |           |
|  |     - Invoca notify-handler      |     via WebSocket      |           |
|  |     - Empuja ALERT al Pi --------+------->--------->>>----+           |
|  +----------------------------------+                                    |
|         |                                                                |
|         v (async)                                                        |
|  +--[ Lambda: notify-handler ]------+    +--[ DynamoDB ]-------------+  |
|  |  1. Lee cooldown de DynamoDB     |--->|  Events: estado, timestamps|  |
|  |  2. Si aplica: sendPhoto Telegram|    |  Detections: conf, bbox   |  |
|  |  3. Actualiza last_notification  |    |  Connections: websocket   |  |
|  +----------------------------------+    +---------------------------+  |
|                                                                          |
+~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~+
         |
         v
+--[ Telegram Bot API ]--+     +--[ Usuario ]--+
|  sendPhoto + caption   |---->|  App Telegram  |
+------------------------+     +---------------+
```

## 8.2 Diagrama de secuencia

```
Pi          API GW       Lambda:presign    S3        Lambda:inference   DynamoDB    Lambda:notify   Telegram
|               |              |            |              |               |              |            |
| POST /presign |              |            |              |               |              |            |
|-------------->|------------->|            |              |               |              |            |
|               |   gen URL    |            |              |               |              |            |
|<--------------+<-------------|            |              |               |              |            |
| {url, mode}   |              |            |              |               |              |            |
|               |              |            |              |               |              |            |
| PUT snapshot  |              |            |              |               |              |            |
|-------------------------------------->    |              |               |              |            |
|               |              |            |              |               |              |            |
|               |              |  ObjectCreated trigger    |               |              |            |
|               |              |            |------------->|               |              |            |
|               |              |            |  get image   |               |              |            |
|               |              |            |<-------------|               |              |            |
|               |              |            |              |               |              |            |
|               |              |            |   ONNX infer |               |              |            |
|               |              |            |              |--DRONE------->|              |            |
|               |              |            |              | write event   |              |            |
|               |              |            |              |               |              |            |
|               |              |            |              |---async------>|------------->|            |
|               |              |            |              |               | check cooldown|            |
|               |              |            |              |               |              |            |
|<~~~~~~~~~~~~~WebSocket: {mode: ALERT}~~~~~|              |               |  sendPhoto   |            |
|               |              |            |              |               |------------->|----------->|
|  cadence=1s   |              |            |              |               |              |   foto +   |
|               |              |            |              |               |              |  metricas  |
```

## 8.3 Estados del evento

```
Primer snapshot llega
        |
        v
   [ PENDING ] --IA dice DRONE--> [ ACTIVE ] --sin deteccion 10s--> [ ENDED ]
        |                              |                                 |
   IA dice NO DRONE              Nueva deteccion                  Msg cierre
        |                        (actualiza last_det)              a Telegram
        v                              |
   [ DISMISSED ]                  se mantiene ACTIVE
```

## 8.4 Modos de cadencia del Pi

```
   [ IDLE: 0 FPS ]
        |
   movimiento detectado
        |
        v
   [ NORMAL: 0.5 FPS ] <------- evento ENDED (via WebSocket)
        |
   nube confirma DRONE
   (via WebSocket push)
        |
        v
   [ ALERTA: 1 FPS ] ----------> 10s sin movimiento -> vuelve a IDLE
```

---

# 9. POLITICAS DE CADENCIA

| Modo | Cadencia | Trigger de entrada | Trigger de salida |
|------|----------|-------------------|-------------------|
| IDLE | 0 FPS (no sube) | Sin movimiento por 30s | Movimiento detectado |
| NORMAL | 0.5 FPS (1 cada 2s) | Movimiento detectado | WebSocket: ALERT |
| ALERTA | 1 FPS (1 cada 1s) | WebSocket: DRONE confirmado | WebSocket: ENDED + 10s |

### Tamaño de imagen optimizado

| Parametro | Valor |
|-----------|-------|
| Resolucion de captura | 640x480 (no 1080p) |
| Formato | JPEG, calidad 80% |
| Tamano promedio | ~60KB |
| Ancho de banda ALERTA (1 FPS) | ~480 Kbps |

640x480 es suficiente porque YOLOv8 redimensiona a 640x640 internamente.

---

# 10. GESTION DE EVENTOS

### Reglas en DynamoDB

| Regla | Valor |
|-------|-------|
| Creacion de evento | Primera deteccion positiva (conf >= 0.4) |
| Mantenimiento | Cada nueva deteccion actualiza `last_detection_at` |
| Cierre | 10 segundos sin deteccion positiva -> ENDED |
| Fusion | Nuevo dron < 30s tras cierre -> reabre evento anterior |

### Cooldown de Telegram

| Tipo | Cuando | Contenido |
|------|--------|-----------|
| Alerta inicial | Primera deteccion del evento | Imagen + metricas |
| Update | Cada 30s mientras ACTIVE | Mejor snapshot (mayor conf) |
| Cierre | Evento pasa a ENDED | Resumen: duracion, detecciones, mejor imagen |
| Maximo por evento | 10 mensajes | Evitar spam |

### Esquema DynamoDB

**Tabla Events**
```
PK: device_id | SK: event_id
status, started_at, last_detection_at, ended_at,
total_detections, max_confidence, best_snapshot_key,
notifications_sent, last_notification_at
```

**Tabla Detections**
```
PK: event_id | SK: timestamp
device_id, snapshot_key, class, confidence,
bbox_x1, bbox_y1, bbox_x2, bbox_y2, annotated_key
```

**Tabla Connections**
```
PK: connection_id
device_id, connected_at, last_ping
```

---

# 11. ALTERNATIVAS DE HARDWARE

## Alternativas al Pi 3B+

| Opcion | IA local | Costo | Ventaja principal |
|--------|----------|-------|-------------------|
| **Pi 3B+ (actual)** | 0.5-1.5 FPS | $35 | Ya lo tienes, suficiente para edge sin IA |
| Pi 4 4GB | 3-5 FPS ONNX | $55 | Fallback local si pierde internet |
| Pi 5 4GB | 5-8 FPS + PCIe para Coral | $60-80 | Mejor estabilidad, opcion de TPU |
| **Jetson Nano** | **15-25 FPS TensorRT** | **$150** | **Elimina dependencia cloud** |
| Pi 3B+ + Coral USB | 8-12 FPS TFLite | $95 | Upgrade minimo con acelerador |

**Recomendacion**: Mantener Pi 3B+ para MVP (cloud inference). Migrar a Jetson Nano si se quiere eliminar cloud a futuro.

## Alternativas a EZVIZ H1C

| Opcion | Ventaja sobre H1C | Costo |
|--------|-------------------|-------|
| **EZVIZ H1C (actual)** | Ya la tienes, RTSP disponible | $30 |
| Reolink RLC-510 | Exterior IP66, IR 30m, POE | $50-60 |
| Tapo C320WS | Exterior, 2K, IR 30m | $40 |
| Pi Camera Module 3 | Latencia 10ms (directo al Pi) | $25-35 |

---

# 12. UPGRADE: KIT VILROS PI 4 4GB

Si se reemplaza el Pi 3B+ por el **Kit Vilros Raspberry Pi 4 4GB**, el sistema gana capacidades significativas que simplifican la arquitectura y reducen riesgos.

## 12.1 Que incluye el kit (todo lo necesario)

| Pieza | Funcion |
|-------|---------|
| Raspberry Pi 4 Model B 4GB | Edge device |
| MicroSD 64GB con Raspberry Pi OS preinstalado | Listo para usar, sin setup |
| Fuente 3A USB-C con switch on/off | Alimentacion |
| Caja con ventilador preinstalado | Refrigeracion activa para 24/7 |
| Disipadores de calor (x4) | Refrigeracion pasiva |
| Cable micro HDMI a HDMI | Solo para setup inicial (opcional con SSH) |
| Adaptador MicroSD a USB | Para reflashear si necesario |

**Solo necesitas agregar**: EZVIZ H1C (ya la tienes) + cable Ethernet (~$3-5, recomendado).

## 12.2 Que cambia en la arquitectura

### Comparativa Pi 3B+ vs Pi 4 4GB

| Aspecto | Pi 3B+ (actual) | Pi 4 4GB (upgrade) | Impacto |
|---------|-----------------|---------------------|---------|
| RAM | 1GB | 4GB | Elimina riesgo de crash por RAM |
| CPU | Cortex-A53 1.4GHz | Cortex-A72 1.5GHz | ~40% mas rapido en OpenCV |
| WiFi | Solo 2.4GHz | 2.4GHz + **5GHz** | Pi en 5GHz, camara en 2.4GHz, sin interferencia |
| Ethernet | 300Mbps (via USB) | **Gigabit nativo** | Upload a S3 mas rapido y estable |
| USB | 2.0 compartido | **3.0 dedicado** | Sin cuello de botella I/O |
| ONNX local | 0.5-1.5 FPS (inutilizable) | **3-5 FPS (viable como fallback)** | Fallback offline posible |
| Temperatura | Se recalienta rapido | Kit con ventilador + disipadores | Estable 24/7 |

### Capacidad nueva: Fallback de inferencia local

Con 4GB de RAM, el Pi 4 puede ejecutar YOLOv8n-INT8 localmente a 3-5 FPS. Esto habilita un **modo offline** que el Pi 3B+ no podia:

```
                    Internet disponible?
                           |
                  SI ------+------ NO
                  |                |
                  v                v
           [MODO CLOUD]     [MODO LOCAL]
           (arquitectura     (fallback)
            normal)
                            Pi ejecuta ONNX
           Pi sube a S3     localmente a 3-5 FPS
           Lambda infiere
           DynamoDB          Guarda detecciones
           Telegram          en SQLite local

                            Cuando vuelve internet:
                            sincroniza con la nube
```

Esto elimina el riesgo mas critico del sistema: **si se cae internet, el Pi 4 sigue detectando drones localmente**.

## 12.3 Procesos que se simplifican

| Proceso | Con Pi 3B+ | Con Pi 4 4GB |
|---------|-----------|-------------|
| **Setup inicial** | Comprar MicroSD aparte, flashear OS, instalar deps | MicroSD viene con OS preinstalado, solo instalar deps |
| **Compresion JPEG** | ~40ms por frame (CPU lento) | ~25ms por frame (~40% mas rapido) |
| **Motion detection** | Funciona pero ajustado en RAM | Holgado, puede procesar a mayor resolucion |
| **WebSocket + Upload simultaneo** | Compite por USB 2.0 compartido | Ethernet nativo + USB 3.0 separado |
| **Estabilidad 24/7** | Riesgo de throttling sin ventilador | Ventilador + disipadores incluidos |
| **Perdida de internet** | Sistema ciego (sin deteccion) | Fallback local a 3-5 FPS |
| **Logs y debug** | Poca RAM para logs extensos | Puede mantener logs en memoria |

## 12.4 Costos que se reducen

| Concepto | Con Pi 3B+ | Con Pi 4 4GB | Ahorro |
|----------|-----------|-------------|--------|
| **AWS Lambda** (con fallback local) | ~$1.61/mes | ~$1.20/mes (menos invocaciones si hay cortes) | ~$0.41 |
| **Riesgo de reboot** | Alto (OOM kills) | Bajo | Menos downtime |
| **Hardware adicional** | MicroSD ($10) + fuente ($10) + ventilador ($8) = **$28** | **$0 (todo incluido en kit)** | $28 en accesorios |
| **Tiempo de setup** | ~2 horas (flashear, configurar, probar) | ~30 min (OS preinstalado) | ~1.5 horas |

### Costo total del proyecto con cada opcion

| Concepto | Pi 3B+ (ya lo tienes) | Kit Vilros Pi 4 |
|----------|----------------------|-----------------|
| Placa | $0 (ya la tienes) | ~$90-100 (kit completo) |
| Accesorios faltantes | ~$28 (MicroSD + fuente + ventilador) | $0 (todo incluido) |
| Cable Ethernet | ~$5 | ~$5 |
| EZVIZ H1C | $0 (ya la tienes) | $0 (ya la tienes) |
| AWS mensual | ~$6.70/mes | ~$6.70/mes |
| **Total hardware** | **~$33** | **~$95-105** |
| **Diferencia** | Mas barato pero con limitaciones | +$65-70 pero sin riesgos |

## 12.5 Riesgos que se eliminan

| Riesgo del Pi 3B+ | Con Pi 4 4GB |
|--------------------|-------------|
| "Pi 3B+ sin RAM -> crash del servicio" | **ELIMINADO** - 4GB es mas que suficiente |
| "Perdida de internet -> sin deteccion" | **MITIGADO** - Fallback local a 3-5 FPS |
| "USB compartido -> cuello de botella" | **ELIMINADO** - USB 3.0 + Gigabit separados |
| "WiFi 2.4GHz compite con camara" | **ELIMINADO** - Pi usa 5GHz, camara usa 2.4GHz |
| "Sin ventilador -> throttling" | **ELIMINADO** - Kit trae ventilador preinstalado |

## 12.6 Recomendacion

Si el presupuesto lo permite (~$95-105 USD por el kit), el **Pi 4 4GB es la mejor opcion** porque:

1. Elimina 5 de 7 riesgos identificados en la seccion de riesgos
2. Habilita fallback offline (deteccion sin internet)
3. No requiere comprar accesorios por separado
4. Viene listo para usar (OS preinstalado)
5. Estabilidad garantizada para operacion 24/7

Si ya tienes el Pi 3B+ y el presupuesto es limitado, el sistema funciona igual pero con las limitaciones documentadas.

---

# 13. COSTOS AWS

## Escenario: 1 camara, ~4h de movimiento/dia

| Modo | Cadencia | Horas/dia | Inferencias/dia |
|------|----------|-----------|-----------------|
| IDLE | 0 FPS | 20h | 0 |
| NORMAL | 0.5 FPS | 3.9h | 7,020 |
| ALERTA | 1 FPS | 0.1h | 360 |
| **Total/dia** | | | **~7,380** |
| **Total/mes** | | | **~221,400** |

| Servicio | Calculo | Costo/mes |
|----------|---------|-----------|
| Lambda compute (512MB, ~0.8s avg) | 221,400 x 0.5GB x 0.8s | ~$1.48 |
| Lambda invocaciones | 221,400 x 3 funciones | ~$0.13 |
| API Gateway REST | 221,400 requests | ~$0.74 |
| API Gateway WebSocket | ~720h conexion + mensajes | ~$0.50 |
| S3 storage + requests | ~10GB + PUTs/GETs | ~$1.50 |
| DynamoDB on-demand | ~665K writes + reads | ~$0.85 |
| CloudWatch logs | ~3GB | ~$1.50 |
| **TOTAL** | | **~$6.70/mes** |

Costo cuando NO hay movimiento (noche, dia tranquilo): **~$0/mes** (solo WebSocket idle ~$0.25).

---

# 14. PLAN DE IMPLEMENTACION

## Fase 0: Modelo (3-4 dias)

- Exportar `best.pt` a ONNX
- Cuantizar a INT8
- Validar precision INT8 vs FP32
- Empaquetar como Lambda Layer
- Probar inferencia local con SAM CLI

## Fase 1: Infraestructura AWS (3-4 dias)

- Crear bucket S3 con lifecycle policies
- Crear tablas DynamoDB (Events, Detections, Connections)
- Crear Lambda functions (presign, inference, notify)
- Configurar S3 trigger -> inference Lambda
- Configurar API Gateway REST + WebSocket
- Definir todo con AWS SAM template

## Fase 2: Edge Software (4-5 dias)

- Modulo captura RTSP (OpenCV headless)
- Modulo deteccion de movimiento (absdiff)
- Modulo uploader (presigned URL + S3 PUT)
- Cliente WebSocket (recibe modo NORMAL/ALERTA)
- Cola local para resiliencia
- Systemd service para auto-arranque

## Fase 3: Integracion + Telegram (3-4 dias)

- Crear bot Telegram
- Implementar notify-handler con cooldown
- Test end-to-end: Pi -> S3 -> Lambda -> DynamoDB -> Telegram
- Medir latencia en cada paso
- Prueba de estabilidad 24h

## Fase 4: Ajustes (2-3 dias)

- Optimizar cold starts (ajustar memoria Lambda)
- Ajustar umbrales de movimiento y confianza
- Dashboard basico en CloudWatch
- Documentacion final

### Timeline

```
Sem 1          Sem 2          Sem 3          Sem 4
+--------------+--------------+--------------+--------------+
| Fase 0       | Fase 1       | Fase 2       | Fase 3 + 4   |
| Modelo ONNX  | Infra AWS    | Edge (Pi)    | Integracion  |
| + cuantizar  | SAM template | RTSP+motion  | Telegram     |
| + Lambda Layer| S3+DDB+APIGW| WebSocket    | E2E test     |
+--------------+--------------+--------------+--------------+
```

---

# 15. RIESGOS

| Riesgo | Impacto | Mitigacion |
|--------|---------|------------|
| Cold start Lambda (5-15s) | Primera deteccion lenta | Aceptable para MVP; usar provisioned concurrency si critico ($) |
| Pi 3B+ sin RAM | Crash del servicio | Swap 512MB, limitar procesos, upgrade a Pi 4 si inestable |
| RTSP de H1C inestable | Perdida de frames | Reconexion automatica con backoff exponencial |
| Perdida de internet | Sin deteccion cloud | Cola local en Pi, movimiento sigue funcionando como alarma basica |
| INT8 degrada precision | Mas falsos negativos | Validar exhaustivamente antes de deploy; ajustar umbral de conf |
| WebSocket se desconecta | Pi no recibe ALERTA | Fallback a polling en respuesta de presign; reconexion automatica |
| Costos inesperados | Factura alta | Budget alerts AWS ($20), limite de cadencia, modo IDLE sin subida |

---

**Resumen en una linea:**
*Pi captura + movimiento -> presigned URL -> S3 -> Lambda ONNX -> DynamoDB -> Telegram. WebSocket empuja modo ALERTA al Pi. Full serverless, ~$6.70/mes.*
