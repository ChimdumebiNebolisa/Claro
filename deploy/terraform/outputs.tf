output "artifact_registry_repository" {
  description = "Repository prefix used by the digest-only deploy workflow."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.claros.repository_id}"
}

output "assignment_bucket" {
  description = "Private assignment bucket consumed by the runtime service."
  value       = google_storage_bucket.assignments.name
}

output "deploy_service_account" {
  description = "Service account impersonated by GitHub Actions through WIF."
  value       = google_service_account.deployer.email
}

output "runtime_service_account" {
  description = "Least-privilege identity assigned to both Cloud Run services."
  value       = google_service_account.runtime.email
}

output "workload_identity_provider" {
  description = "Provider resource name for google-github-actions/auth."
  value       = google_iam_workload_identity_pool_provider.github.name
}
