# AWS deployment

Terraform in `deploy/aws/terraform` is the production source of truth. The
stack uses CloudFront -> ALB -> one private EC2 application instance, RDS
PostgreSQL, ECR, private S3, Secrets Manager, and CloudWatch. The application
remains a single replica because Cognee's embedded stores require one writer;
the encrypted 80 GB root volume persists its Docker volume.

The existing standalone EC2 instance is deliberately not managed by this
stack and remains the rollback target until AWS acceptance is complete. The
existing versioned deployment bucket stores Terraform state, while the
existing `openhuman/prod/runtime` secret supplies application credentials.
RDS manages its own password in Secrets Manager.

Instances are managed with Systems Manager Session Manager; SSH is not
exposed. CloudFront's generated HTTPS hostname is the temporary production,
OAuth callback, and ArmorIQ MCP hostname.

## Bootstrap and deploy

1. Create the ECR repositories and shared infrastructure with Terraform.
2. Build both images with the same Git SHA tag and push them to ECR.
3. Set `api_image` and `web_image` in an ignored `.tfvars` file.
4. Apply Terraform. The launch template pulls the images, runs Alembic, and
   starts the full `app.main:app` API with the Slack gateway enabled.

```bash
cd deploy/aws/terraform
terraform init
terraform plan -var-file=production.auto.tfvars
terraform apply -var-file=production.auto.tfvars
```

To inspect the stack on the host:

```bash
sudo docker compose --env-file /opt/openhuman/.env -f /opt/openhuman/docker-compose.yml ps
sudo docker compose --env-file /opt/openhuman/.env -f /opt/openhuman/docker-compose.yml logs --tail=200
```
