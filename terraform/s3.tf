resource "aws_s3_bucket" "snapshots" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "snapshots" {
  bucket = aws_s3_bucket.snapshots.id

  rule {
    id     = "expire-raw-24h"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "expire-annotated-30d"
    status = "Enabled"

    filter {
      prefix = "annotated/"
    }

    expiration {
      days = 30
    }
  }
}
