output "function_name" {
  value = aws_lambda_function.agent.function_name
}

output "bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}

output "ssm_parameter_name" {
  value = var.snowflake_key_param_name
}
