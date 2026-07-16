#!/usr/bin/env bash
# Deploy the MarketDX MCP server to Cloud Run (us-east1) — hosted Streamable HTTP.
# Usage:  ./deploy.sh
# Env:    PROJECT (default ava-advisor-26c7b)  REGION (default us-east1)
#
# One runtime secret: DEEPSEEK_API_KEY (composite tools). NO MarketDX key — auth is per-request
# (the caller's Bearer). After first deploy, map the domain ONCE:
#   gcloud beta run domain-mappings create --service marketdx-mcp \
#     --domain mcp.marketdx.lab.ai --region us-east1 --project ava-advisor-26c7b
#   → then add the CNAME/A records it prints to the marketdx.lab.ai DNS zone.
set -euo pipefail
PROJECT="${PROJECT:-ava-advisor-26c7b}"
REGION="${REGION:-us-east1}"
SERVICE="marketdx-mcp"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "Deploying ${SERVICE} → Cloud Run (${PROJECT}/${REGION})"
gcloud run deploy "${SERVICE}" \
  --source "${HERE}" \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-secrets "DEEPSEEK_API_KEY=DEEPSEEK_API_KEY:latest" \
  --update-env-vars "WORKOS_ISSUER=${WORKOS_ISSUER:-https://cuddly-honey-96-staging.authkit.app}" \
  --cpu 1 --memory 512Mi --min-instances 0 --max-instances 4 --timeout 120

echo "Deployed. Test the .run.app URL, then map mcp.marketdx.lab.ai (see header)."
