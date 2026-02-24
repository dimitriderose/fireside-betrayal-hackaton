# ──────────────────────────────────────────────────────────────────────────────
# Fireside: Betrayal — Terraform IaC
# One-command deployment: enables APIs, provisions Firestore, builds + deploys
# the Docker image to Cloud Run with WebSocket session affinity.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required GCP APIs ─────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ── Cloud Firestore ──────────────────────────────────────────────────────────

resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.apis]
}

# ── Artifact Registry (Docker images) ────────────────────────────────────────

resource "google_artifact_registry_repository" "docker" {
  repository_id = "fireside"
  location      = var.region
  format        = "DOCKER"
  description   = "Fireside: Betrayal container images"

  depends_on = [google_project_service.apis]
}

# ── Cloud Build trigger (auto-deploy on push to main) ────────────────────────
# NOTE: Requires GitHub repo to be connected in Cloud Build console first.
# If you prefer manual builds, comment this out and use:
#   gcloud builds submit --tag $IMAGE_URL

# resource "google_cloudbuild_trigger" "deploy" {
#   name     = "fireside-deploy"
#   filename = "cloudbuild.yaml"
#
#   github {
#     owner = "dimitriderose"
#     name  = "fireside-betrayal-hackaton"
#     push {
#       branch = "^main$"
#     }
#   }
#
#   depends_on = [google_project_service.apis]
# }

# ── Cloud Run service ────────────────────────────────────────────────────────

locals {
  image_url = "${var.region}-docker.pkg.dev/${var.project_id}/fireside/fireside-betrayal:latest"
}

resource "google_cloud_run_v2_service" "fireside" {
  name     = "fireside-betrayal"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    session_affinity = true  # Critical for WebSocket connections

    containers {
      image = local.image_url

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GEMINI_API_KEY"
        value = var.gemini_api_key
      }
      env {
        name  = "EXTRA_ORIGIN"
        value = ""  # Updated after first deploy (see output)
      }
      env {
        name  = "DEBUG"
        value = "false"
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.default,
    google_artifact_registry_repository.docker,
  ]
}

# ── Allow unauthenticated access (public game) ──────────────────────────────

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.fireside.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "service_url" {
  description = "Cloud Run URL — set this as EXTRA_ORIGIN after first deploy"
  value       = google_cloud_run_v2_service.fireside.uri
}

output "image_url" {
  description = "Docker image URL to push to"
  value       = local.image_url
}

output "firestore_database" {
  description = "Firestore database name"
  value       = google_firestore_database.default.name
}
