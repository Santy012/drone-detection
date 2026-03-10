# --------------------
# REST API
# --------------------

resource "aws_api_gateway_rest_api" "drone_api" {
  name        = "${local.project}-api"
  description = "Drone Detection API - presign + detections"
}

# --------------------
# /presign endpoint
# --------------------

resource "aws_api_gateway_resource" "presign" {
  rest_api_id = aws_api_gateway_rest_api.drone_api.id
  parent_id   = aws_api_gateway_rest_api.drone_api.root_resource_id
  path_part   = "presign"
}

resource "aws_api_gateway_method" "presign_post" {
  rest_api_id   = aws_api_gateway_rest_api.drone_api.id
  resource_id   = aws_api_gateway_resource.presign.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "presign" {
  rest_api_id             = aws_api_gateway_rest_api.drone_api.id
  resource_id             = aws_api_gateway_resource.presign.id
  http_method             = aws_api_gateway_method.presign_post.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.presign.invoke_arn
}

resource "aws_lambda_permission" "presign_apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.presign.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.drone_api.execution_arn}/*/*"
}

# --------------------
# /detections endpoint
# --------------------

resource "aws_api_gateway_resource" "detections" {
  rest_api_id = aws_api_gateway_rest_api.drone_api.id
  parent_id   = aws_api_gateway_rest_api.drone_api.root_resource_id
  path_part   = "detections"
}

resource "aws_api_gateway_method" "detections_post" {
  rest_api_id   = aws_api_gateway_rest_api.drone_api.id
  resource_id   = aws_api_gateway_resource.detections.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "detections" {
  rest_api_id             = aws_api_gateway_rest_api.drone_api.id
  resource_id             = aws_api_gateway_resource.detections.id
  http_method             = aws_api_gateway_method.detections_post.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.detection.invoke_arn
}

resource "aws_lambda_permission" "detection_apigw" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.detection.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.drone_api.execution_arn}/*/*"
}

# --------------------
# DEPLOYMENT + STAGE
# --------------------

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.drone_api.id

  depends_on = [
    aws_api_gateway_integration.presign,
    aws_api_gateway_integration.detections,
  ]

  # Force redeployment when API changes
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.presign.id,
      aws_api_gateway_method.presign_post.id,
      aws_api_gateway_integration.presign.id,
      aws_api_gateway_resource.detections.id,
      aws_api_gateway_method.detections_post.id,
      aws_api_gateway_integration.detections.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.drone_api.id
  stage_name    = "v1"
}
