# Deploy Claros to Google Cloud Run

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Docker (optional; you can use Cloud Build)

## Build and push image

```bash
# Set your project and region
export PROJECT_ID=your-project-id
export REGION=us-central1
export IMAGE=claros-backend

# Build with Cloud Build (no local Docker needed)
gcloud builds submit --tag gcr.io/${PROJECT_ID}/${IMAGE}

# Or with Artifact Registry
gcloud artifacts repositories create claros --repository-format=docker --location=${REGION} 2>/dev/null || true
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/claros/${IMAGE}:latest
```

## Deploy to Cloud Run

```bash
gcloud run deploy claros \
  --image gcr.io/${PROJECT_ID}/${IMAGE} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=your-key,GCS_BUCKET_NAME=your-bucket,GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --min-instances 1 \
  --timeout 3600
```

- **min-instances=1** avoids cold starts during demo.
- **timeout=3600** keeps WebSocket connections alive (Cloud Run default is 60s).
- Create a GCS bucket and grant the Cloud Run service account Storage Object Admin (or equivalent) on that bucket.

## Frontend

The app serves `frontend/index.html` at `/`. No config change needed: when users open the Cloud Run URL, the frontend uses the same host for API and WebSocket.
