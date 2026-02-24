variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "gemini_api_key" {
  description = "Gemini API key (from AI Studio)"
  type        = string
  sensitive   = true
}
