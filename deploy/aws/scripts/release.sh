#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${API_IMAGE:?API_IMAGE is required}"
: "${WEB_IMAGE:?WEB_IMAGE is required}"
: "${LAUNCH_TEMPLATE_ID:?LAUNCH_TEMPLATE_ID is required}"
: "${AUTO_SCALING_GROUP:?AUTO_SCALING_GROUP is required}"
: "${HEALTH_URL:?HEALTH_URL is required}"

release_dir="$(mktemp -d)"
trap 'rm -rf "$release_dir"' EXIT

source_version="$(
  aws ec2 describe-launch-template-versions \
    --region "$AWS_REGION" \
    --launch-template-id "$LAUNCH_TEMPLATE_ID" \
    --versions '$Latest' \
    --query 'LaunchTemplateVersions[0].VersionNumber' \
    --output text
)"

aws ec2 describe-launch-template-versions \
  --region "$AWS_REGION" \
  --launch-template-id "$LAUNCH_TEMPLATE_ID" \
  --versions "$source_version" \
  --query 'LaunchTemplateVersions[0].LaunchTemplateData.UserData' \
  --output text | base64 --decode > "$release_dir/user-data.sh"

api_repository="${API_IMAGE%:*}"
web_repository="${WEB_IMAGE%:*}"
sed -E -i \
  -e "s#${api_repository}:[A-Za-z0-9._-]+#${API_IMAGE}#g" \
  -e "s#${web_repository}:[A-Za-z0-9._-]+#${WEB_IMAGE}#g" \
  "$release_dir/user-data.sh"

grep -Fq "$API_IMAGE" "$release_dir/user-data.sh"
grep -Fq "$WEB_IMAGE" "$release_dir/user-data.sh"

encoded_user_data="$(base64 --wrap=0 "$release_dir/user-data.sh")"
launch_template_data="$(jq -cn --arg user_data "$encoded_user_data" '{UserData:$user_data}')"
new_version="$(
  aws ec2 create-launch-template-version \
    --region "$AWS_REGION" \
    --launch-template-id "$LAUNCH_TEMPLATE_ID" \
    --source-version "$source_version" \
    --version-description "OpenHuman ${GITHUB_SHA:-manual}" \
    --launch-template-data "$launch_template_data" \
    --query 'LaunchTemplateVersion.VersionNumber' \
    --output text
)"
echo "Created launch-template version $new_version"

refresh_id="$(
  aws autoscaling start-instance-refresh \
    --region "$AWS_REGION" \
    --auto-scaling-group-name "$AUTO_SCALING_GROUP" \
    --strategy Rolling \
    --preferences '{"MinHealthyPercentage":0,"InstanceWarmup":600,"SkipMatching":false}' \
    --query 'InstanceRefreshId' \
    --output text
)"
echo "Started instance refresh $refresh_id"

for _ in $(seq 1 60); do
  refresh_status="$(
    aws autoscaling describe-instance-refreshes \
      --region "$AWS_REGION" \
      --auto-scaling-group-name "$AUTO_SCALING_GROUP" \
      --instance-refresh-ids "$refresh_id" \
      --query 'InstanceRefreshes[0].Status' \
      --output text
  )"
  case "$refresh_status" in
    Successful)
      curl --fail --silent --show-error --retry 12 --retry-delay 10 \
        --max-time 30 "${HEALTH_URL}?release=${GITHUB_SHA:-manual}"
      echo
      echo "AWS release is healthy"
      exit 0
      ;;
    Failed|Cancelled|RollbackFailed|RollbackSuccessful)
      echo "Instance refresh ended with status: $refresh_status" >&2
      exit 1
      ;;
  esac
  sleep 30
done

echo "Timed out waiting for instance refresh $refresh_id" >&2
exit 1
