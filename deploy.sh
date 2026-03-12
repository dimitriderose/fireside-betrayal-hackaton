#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Fireside: Betrayal — One-Command Cloud Deployment
#
# Usage:
#   ./deploy.sh              # Deploy using gcloud CLI
#   ./deploy.sh --terraform  # Deploy using Terraform IaC
#
# Required environment variables:
#   GOOGLE_CLOUD_PROJECT  — GCP project ID
#   GEMINI_API_KEY        — Gemini API key (from AI Studio)
#
# Optional environment variables:
#   GCP_REGION            — Deployment region (default: us-central1)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REGION="${GCP_REGION:-us-central1}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:?Error: set GOOGLE_CLOUD_PROJECT}"
GEMINI_KEY="${GEMINI_API_KEY:?Error: set GEMINI_API_KEY}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/fireside/fireside-betrayal:latest"

echo "==> Deploying Fireside: Betrayal to ${PROJECT_ID} (${REGION})"

if [[ "${1:-}" == "--terraform" ]]; then
    # ── Terraform path: build image, then provision everything via IaC ──
    echo "==> Building Docker image via Cloud Build..."
    gcloud builds submit --tag "$IMAGE" --timeout=600 --project="$PROJECT_ID"

    echo "==> Running Terraform..."
    cd terraform
    terraform init -input=false
    terraform apply -auto-approve \
      -var="project_id=${PROJECT_ID}" \
      -var="region=${REGION}" \
      -var="gemini_api_key=${GEMINI_KEY}"
    SERVICE_URL=$(terraform output -raw service_url)
    cd ..
else
    # ── gcloud CLI path: enable APIs, build, deploy ──
    echo "==> Enabling required APIs..."
    gcloud services enable \
      run.googleapis.com \
      cloudbuild.googleapis.com \
      firestore.googleapis.com \
      artifactregistry.googleapis.com \
      --project="$PROJECT_ID"

    echo "==> Creating Firestore database (if needed)..."
    gcloud firestore databases describe --project="$PROJECT_ID" 2>/dev/null \
    || gcloud firestore databases create --location="$REGION" --project="$PROJECT_ID"

    echo "==> Creating Artifact Registry (if needed)..."
    gcloud artifacts repositories describe fireside \
      --location="$REGION" --project="$PROJECT_ID" 2>/dev/null \
    || gcloud artifacts repositories create fireside \
      --repository-format=docker \
      --location="$REGION" \
      --project="$PROJECT_ID"

    echo "==> Building Docker image via Cloud Build..."
    gcloud builds submit --tag "$IMAGE" --timeout=600 --project="$PROJECT_ID"

    echo "==> Deploying to Cloud Run (env vars passed at runtime)..."
    gcloud run deploy fireside-betrayal \
      --image "$IMAGE" \
      --platform managed \
      --region "$REGION" \
      --port 8000 \
      --memory 1Gi --cpu 1 \
      --min-instances 0 --max-instances 10 \
      --session-affinity \
      --timeout 3600 \
      --no-cpu-throttling \
      --allow-unauthenticated \
      --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GEMINI_API_KEY=${GEMINI_KEY},DEBUG=false" \
      --project="$PROJECT_ID"

    SERVICE_URL=$(gcloud run services describe fireside-betrayal \
      --region "$REGION" --project="$PROJECT_ID" --format='value(status.url)')
fi

# ── Post-deploy: set CORS origin to the Cloud Run URL ──
echo "==> Setting CORS origin to ${SERVICE_URL}..."
gcloud run services update fireside-betrayal \
  --region "$REGION" \
  --update-env-vars="EXTRA_ORIGIN=${SERVICE_URL}" \
  --project="$PROJECT_ID"

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "  URL: ${SERVICE_URL}"
echo ""
echo "  Runtime env vars set on Cloud Run:"
echo "    GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
echo "    GEMINI_API_KEY=****"
echo "    EXTRA_ORIGIN=${SERVICE_URL}"
echo "    DEBUG=false"
echo "============================================"
