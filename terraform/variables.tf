variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "lab_role_arn" {
  description = "ARN del LabRole de AWS Academy (ej: arn:aws:iam::123456789012:role/LabRole)"
  type        = string
}

variable "telegram_bot_token" {
  description = "Telegram Bot API token (from BotFather)"
  type        = string
  sensitive   = true
}

variable "telegram_chat_id" {
  description = "Telegram chat ID to send notifications to"
  type        = string
}
