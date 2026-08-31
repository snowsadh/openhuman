terraform {
  required_version = ">= 1.10.0"

  backend "s3" {
    bucket       = "openhuman-prod-651592873730-ap-south-1"
    key          = "terraform/production.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_s3_bucket" "deployment" {
  bucket = var.existing_deployment_bucket
}

data "aws_secretsmanager_secret" "runtime" {
  name = var.existing_runtime_secret_name
}
