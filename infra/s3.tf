locals {
  lambda_zip = "${path.module}/../build/lambda/lambda.zip"
}

# Private bucket for the Lambda deployment zip (the zip is too big for a direct upload).
# The account id suffix keeps the name globally unique.
resource "aws_s3_bucket" "artifacts" {
  bucket        = "${var.function_name}-artifacts-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # lets `terraform destroy` delete it even with the zip inside
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "lambda_zip" {
  bucket      = aws_s3_bucket.artifacts.id
  key         = "lambda/lambda.zip"
  source      = local.lambda_zip
  source_hash = filemd5(local.lambda_zip) # re-upload when the zip changes
}
