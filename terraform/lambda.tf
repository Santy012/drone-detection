# --------------------
# ZIP PACKAGING
# --------------------

data "archive_file" "presign_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/presign_handler"
  output_path = "${path.module}/.build/presign_handler.zip"
}

data "archive_file" "detection_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/detection_handler"
  output_path = "${path.module}/.build/detection_handler.zip"
}

data "archive_file" "notify_handler" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/notify_handler"
  output_path = "${path.module}/.build/notify_handler.zip"
}

# --------------------
# IAM — Usa LabRole de AWS Academy
# --------------------
# En entornos AWS Academy / Learner Lab no se pueden crear roles IAM.
# Todas las Lambdas usan el LabRole existente proporcionado por el lab.

# ==============================================================================
# IAM ROLES PERSONALIZADOS (para produccion / cuenta AWS propia)
# Descomentar esta seccion y comentar la linea lab_role_arn de arriba
# cuando se use una cuenta AWS real con permisos para crear IAM roles.
# ==============================================================================

# data "aws_iam_policy_document" "lambda_assume" {
#   statement {
#     actions = ["sts:AssumeRole"]
#     principals {
#       type        = "Service"
#       identifiers = ["lambda.amazonaws.com"]
#     }
#   }
# }
#
# # -- Presign Handler Role --
#
# resource "aws_iam_role" "presign" {
#   name               = "${local.project}-presign-role"
#   assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
# }
#
# resource "aws_iam_role_policy_attachment" "presign_logs" {
#   role       = aws_iam_role.presign.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
# }
#
# resource "aws_iam_role_policy" "presign_s3" {
#   name = "s3-presign"
#   role = aws_iam_role.presign.id
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [{
#       Effect   = "Allow"
#       Action   = ["s3:PutObject"]
#       Resource = "${aws_s3_bucket.snapshots.arn}/*"
#     }]
#   })
# }
#
# # -- Detection Handler Role --
#
# resource "aws_iam_role" "detection" {
#   name               = "${local.project}-detection-role"
#   assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
# }
#
# resource "aws_iam_role_policy_attachment" "detection_logs" {
#   role       = aws_iam_role.detection.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
# }
#
# resource "aws_iam_role_policy" "detection_dynamo" {
#   name = "dynamodb-access"
#   role = aws_iam_role.detection.id
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Action = [
#           "dynamodb:PutItem",
#           "dynamodb:UpdateItem",
#           "dynamodb:GetItem",
#           "dynamodb:Query",
#         ]
#         Resource = [
#           aws_dynamodb_table.events.arn,
#           "${aws_dynamodb_table.events.arn}/index/*",
#           aws_dynamodb_table.detections.arn,
#         ]
#       },
#       {
#         Effect   = "Allow"
#         Action   = ["lambda:InvokeFunction"]
#         Resource = aws_lambda_function.notify.arn
#       },
#     ]
#   })
# }
#
# # -- Notify Handler Role --
#
# resource "aws_iam_role" "notify" {
#   name               = "${local.project}-notify-role"
#   assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
# }
#
# resource "aws_iam_role_policy_attachment" "notify_logs" {
#   role       = aws_iam_role.notify.name
#   policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
# }
#
# resource "aws_iam_role_policy" "notify_access" {
#   name = "notify-access"
#   role = aws_iam_role.notify.id
#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect   = "Allow"
#         Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
#         Resource = aws_dynamodb_table.events.arn
#       },
#       {
#         Effect   = "Allow"
#         Action   = ["s3:GetObject"]
#         Resource = "${aws_s3_bucket.snapshots.arn}/*"
#       },
#     ]
#   })
# }

# ==============================================================================
# Para produccion: reemplazar var.lab_role_arn por aws_iam_role.<name>.arn
# en cada Lambda function de abajo.
# ==============================================================================

# --------------------
# LAMBDA FUNCTIONS
# --------------------

resource "aws_lambda_function" "presign" {
  function_name    = "${local.project}-presign-handler"
  role             = var.lab_role_arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 10
  memory_size      = 128
  filename         = data.archive_file.presign_handler.output_path
  source_code_hash = data.archive_file.presign_handler.output_base64sha256

  environment {
    variables = {
      S3_BUCKET   = aws_s3_bucket.snapshots.id
      PRESIGN_TTL = "60"
    }
  }
}

resource "aws_lambda_function" "detection" {
  function_name    = "${local.project}-detection-handler"
  role             = var.lab_role_arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 15
  memory_size      = 128
  filename         = data.archive_file.detection_handler.output_path
  source_code_hash = data.archive_file.detection_handler.output_base64sha256

  environment {
    variables = {
      EVENTS_TABLE         = aws_dynamodb_table.events.name
      DETECTIONS_TABLE     = aws_dynamodb_table.detections.name
      NOTIFY_FUNCTION_NAME = aws_lambda_function.notify.function_name
    }
  }
}

resource "aws_lambda_function" "notify" {
  function_name    = "${local.project}-notify-handler"
  role             = var.lab_role_arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  timeout          = 15
  memory_size      = 128
  filename         = data.archive_file.notify_handler.output_path
  source_code_hash = data.archive_file.notify_handler.output_base64sha256

  environment {
    variables = {
      EVENTS_TABLE       = aws_dynamodb_table.events.name
      S3_BUCKET          = aws_s3_bucket.snapshots.id
      TELEGRAM_BOT_TOKEN = var.telegram_bot_token
      TELEGRAM_CHAT_ID   = var.telegram_chat_id
      COOLDOWN_SECONDS   = "30"
      MAX_NOTIFICATIONS  = "10"
    }
  }
}