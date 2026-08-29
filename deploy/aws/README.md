# AWS deployment

The production stack runs on one EC2 instance because the API's embedded
Cognee stores require a persistent local volume and a single API replica.
Docker volumes persist PostgreSQL and Cognee data on the encrypted root EBS
volume. Uploaded documents use a private S3 bucket through the instance role.
Caddy terminates HTTPS and proxies `/api/*` to FastAPI and all other requests
to Next.js.

The instance is managed through AWS Systems Manager Session Manager; SSH is
not exposed. Runtime secrets are held in AWS Secrets Manager and materialized
as `/opt/openhuman/.env` with mode `0600` during bootstrap.

To inspect the stack on the host:

```bash
sudo docker compose -f /opt/openhuman/deploy/aws/docker-compose.yml ps
sudo docker compose -f /opt/openhuman/deploy/aws/docker-compose.yml logs --tail=200
```
