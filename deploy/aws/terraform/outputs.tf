output "production_url" {
  description = "Temporary stable HTTPS URL for web, API, OAuth callbacks, and ArmorIQ MCP registration."
  value       = local.public_url
}

output "api_health_url" {
  value = "${local.public_url}/api/health"
}

output "api_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "web_repository_url" {
  value = aws_ecr_repository.web.repository_url
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.id
}
