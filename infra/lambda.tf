# Created before the function so Lambda never auto-creates it with infinite retention.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "agent" {
  function_name = var.function_name
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.13"
  architectures = ["x86_64"]
  handler       = "telco_ops_agent.lambda_handler.handler"

  s3_bucket        = aws_s3_object.lambda_zip.bucket
  s3_key           = aws_s3_object.lambda_zip.key
  source_code_hash = filebase64sha256(local.lambda_zip) # redeploy when the zip changes

  memory_size = 1024
  timeout     = 120

  environment {
    variables = {
      SNOWFLAKE_KEY_PARAM = var.snowflake_key_param_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
  ]
}
