variable "function_name" {
  description = "Name of the Lambda function (also used for the log group and bucket name)."
  type        = string
  default     = "telco-ops-agent"
}

variable "model_id" {
  description = "Bedrock inference profile id the agent calls. Keep in sync with model_id in src/telco_ops_agent/agent.py."
  type        = string
  default     = "au.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "budget_email" {
  description = "Email address that receives AWS Budgets alerts."
  type        = string
}

variable "snowflake_key_param_name" {
  description = "Name of the SecureString SSM parameter holding the Snowflake private key. Created outside Terraform."
  type        = string
  default     = "/telco-ops/snowflake-private-key"

  validation {
    condition     = startswith(var.snowflake_key_param_name, "/")
    error_message = "Must start with \"/\" so the ARN (…:parameter<name>) is well formed."
  }
}

variable "bedrock_destination_regions" {
  description = "Regions the au. inference profile can route to. Get them from: aws bedrock get-inference-profile --inference-profile-identifier <id> --query \"models[].modelArn\""
  type        = list(string)
  default     = ["ap-southeast-2", "ap-southeast-4"]
}
