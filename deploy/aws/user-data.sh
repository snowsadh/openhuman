#!/usr/bin/env bash
set -euo pipefail

export AWS_REGION=ap-south-1
export DEPLOYMENT_BUCKET=openhuman-prod-651592873730-ap-south-1
export ARTIFACT_KEY=releases/27a4e1b-aws1.tar.gz
export RUNTIME_SECRET_ID=openhuman/prod/runtime

aws s3 cp \
  "s3://${DEPLOYMENT_BUCKET}/bootstrap/bootstrap.sh" \
  /tmp/openhuman-bootstrap.sh \
  --region "${AWS_REGION}"
chmod 0700 /tmp/openhuman-bootstrap.sh
/tmp/openhuman-bootstrap.sh
