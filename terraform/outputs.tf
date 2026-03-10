output "api_url" {
  description = "Base URL of the API Gateway (use with --api-url in detect_webcam.py)"
  value       = aws_api_gateway_stage.v1.invoke_url
}

output "s3_bucket" {
  description = "S3 bucket name for snapshots"
  value       = aws_s3_bucket.snapshots.id
}

output "events_table" {
  description = "DynamoDB Events table name"
  value       = aws_dynamodb_table.events.name
}

output "detections_table" {
  description = "DynamoDB Detections table name"
  value       = aws_dynamodb_table.detections.name
}
