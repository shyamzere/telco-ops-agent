data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = "ap-southeast-2"

  # The Snowflake key parameter is created OUTSIDE Terraform, with
  #   aws ssm put-parameter --name <name> --type SecureString --value file://...
  # so the secret never enters Terraform state. We build its ARN as a plain
  # string instead of using a data source, because data "aws_ssm_parameter"
  # would also read the decrypted value into state.
  # The name already starts with "/", hence "parameter${...}" with no slash.
  snowflake_key_param_arn = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.snowflake_key_param_name}"
}

# Trust policy: only the Lambda service, acting for this account, may assume the role.
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.function_name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  # Write logs to this function's own log group only (Terraform creates the group,
  # so logs:CreateLogGroup is not needed).
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  # Read the Snowflake key. Create the parameter with the default AWS-managed
  # aws/ssm key (no --key-id), so no kms:Decrypt grant is needed.
  statement {
    sid       = "ReadSnowflakeKey"
    actions   = ["ssm:GetParameter"]
    resources = [local.snowflake_key_param_arn]
  }

  # Cross-region inference: the agent calls the au. inference profile in
  # ap-southeast-2, and Bedrock may serve the request from any region in that
  # profile (e.g. ap-southeast-4). IAM is checked twice: once for the profile
  # ARN, and once for the foundation-model ARN in the region that actually runs
  # the request. So the foundation-model ARN must be allowed in every
  # destination region, each one named explicitly (no region wildcard).
  statement {
    sid     = "InvokeHaiku"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = concat(
      ["arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/${var.model_id}"],
      [
        for r in var.bedrock_destination_regions :
        "arn:aws:bedrock:${r}::foundation-model/${trimprefix(var.model_id, "au.")}"
      ],
    )
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.function_name}-least-privilege"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
