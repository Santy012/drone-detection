resource "aws_dynamodb_table" "events" {
  name         = "DroneEvents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "device_id"
  range_key    = "event_id"

  attribute {
    name = "device_id"
    type = "S"
  }

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "started_at"
    type = "S"
  }

  global_secondary_index {
    name            = "StatusIndex"
    hash_key        = "status"
    range_key       = "started_at"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "detections" {
  name         = "DroneDetections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"
  range_key    = "timestamp"

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }
}
