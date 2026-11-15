provider "aws" {
  region = "ap-southeast-2"

  default_tags {
    tags = {
      Project   = "telco-ops-agent"
      ManagedBy = "terraform"
    }
  }
}
