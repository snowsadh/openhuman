#!/usr/bin/env bash
set -euo pipefail

exec > >(tee -a /var/log/openhuman-bootstrap.log) 2>&1

: "${AWS_REGION:?AWS_REGION is required}"
: "${DEPLOYMENT_BUCKET:?DEPLOYMENT_BUCKET is required}"
: "${ARTIFACT_KEY:?ARTIFACT_KEY is required}"
: "${RUNTIME_SECRET_ID:?RUNTIME_SECRET_ID is required}"

dnf install -y docker git jq tar gzip
systemctl enable --now docker

install -d -m 0755 /usr/local/lib/docker/cli-plugins
curl -fsSL \
  https://github.com/docker/compose/releases/download/v2.40.3/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
curl -fsSL \
  https://github.com/docker/buildx/releases/download/v0.21.2/buildx-v0.21.2.linux-amd64 \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose
chmod 0755 /usr/local/lib/docker/cli-plugins/docker-buildx

install -d -m 0755 /opt/openhuman
aws s3 cp "s3://${DEPLOYMENT_BUCKET}/${ARTIFACT_KEY}" /tmp/openhuman.tar.gz \
  --region "${AWS_REGION}"
tar -xzf /tmp/openhuman.tar.gz -C /opt/openhuman

aws secretsmanager get-secret-value \
  --region "${AWS_REGION}" \
  --secret-id "${RUNTIME_SECRET_ID}" \
  --query SecretString \
  --output text > /run/openhuman-runtime.json

jq -r 'to_entries[] | "\(.key)=\(.value | tostring)"' \
  /run/openhuman-runtime.json > /opt/openhuman/.env
chmod 0600 /opt/openhuman/.env
rm -f /run/openhuman-runtime.json /tmp/openhuman.tar.gz

cd /opt/openhuman
docker compose --env-file /opt/openhuman/.env -f deploy/aws/docker-compose.yml build
docker compose --env-file /opt/openhuman/.env -f deploy/aws/docker-compose.yml up -d
docker image prune -f

docker compose --env-file /opt/openhuman/.env -f deploy/aws/docker-compose.yml ps
