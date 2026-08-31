variable "project_name" {
  description = "Short name used for AWS resources."
  type        = string
  default     = "openhuman"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region for the production stack."
  type        = string
  default     = "ap-south-1"
}

variable "vpc_cidr" {
  description = "CIDR for the dedicated production VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "instance_type" {
  description = "Single-writer OpenHuman application instance type."
  type        = string
  default     = "t3a.large"
}

variable "root_volume_size_gb" {
  description = "Encrypted root volume size; also holds persistent Cognee Docker data."
  type        = number
  default     = 80
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "openhuman"
}

variable "db_username" {
  description = "RDS master/application username."
  type        = string
  default     = "openhuman"
}

variable "existing_deployment_bucket" {
  description = "Existing versioned deployment/state bucket; never recreated by this stack."
  type        = string
  default     = "openhuman-prod-651592873730-ap-south-1"
}

variable "existing_runtime_secret_name" {
  description = "Existing runtime secret containing application and provider credentials."
  type        = string
  default     = "openhuman/prod/runtime"
}

variable "api_image" {
  description = "Immutable API image URI including a non-latest tag."
  type        = string

  validation {
    condition     = !endswith(var.api_image, ":latest") && strcontains(var.api_image, ":")
    error_message = "api_image must include an immutable tag and cannot use :latest."
  }
}

variable "web_image" {
  description = "Immutable web image URI including a non-latest tag."
  type        = string

  validation {
    condition     = !endswith(var.web_image, ":latest") && strcontains(var.web_image, ":")
    error_message = "web_image must include an immutable tag and cannot use :latest."
  }
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deployment role."
  type        = string
  default     = "snowsadh/openhuman"
}

variable "github_branch" {
  description = "GitHub branch allowed to deploy production."
  type        = string
  default     = "main"
}
