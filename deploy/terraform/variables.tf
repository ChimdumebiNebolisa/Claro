variable "project_id" {
  description = "Google Cloud project that owns the Claros deployment."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid Google Cloud project ID."
  }
}

variable "region" {
  description = "Single region for Artifact Registry and both Cloud Run services."
  type        = string
  default     = "us-central1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z0-9]+[0-9]$", var.region))
    error_message = "region must be a valid Google Cloud region."
  }
}

variable "bucket_name" {
  description = "Globally unique private GCS bucket for immutable sources and derivatives."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid lower-case Cloud Storage bucket name."
  }
}

variable "bucket_location" {
  description = "Cloud Storage location; normally the upper-case form of region."
  type        = string
  default     = "US-CENTRAL1"
}

variable "artifact_repository_id" {
  description = "Existing or new Artifact Registry repository used for Claros images."
  type        = string
  default     = "cloud-run-source-deploy"
}

variable "deploy_service_account_id" {
  description = "Existing or new service account impersonated by GitHub Actions."
  type        = string
  default     = "claros-github-deploy"
}

variable "staging_service_name" {
  description = "Cloud Run staging service the deploy identity may update."
  type        = string
  default     = "claros"
}

variable "production_service_name" {
  description = "Cloud Run production service the deploy identity may update."
  type        = string
  default     = "claros"
}

variable "github_repository" {
  description = "GitHub owner/repository used only to bind the exact workflow_ref claim."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/repository form."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric repository_id claim from GitHub OIDC."
  type        = string

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_id))
    error_message = "github_repository_id must be the immutable numeric GitHub ID."
  }
}

variable "github_repository_owner_id" {
  description = "Immutable numeric repository_owner_id claim from GitHub OIDC."
  type        = string

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must be the immutable numeric GitHub ID."
  }
}

variable "deployment_branch" {
  description = "Only this branch may use the deploy Workload Identity provider."
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[A-Za-z0-9._/-]+$", var.deployment_branch))
    error_message = "deployment_branch contains unsupported characters."
  }
}

variable "workload_identity_pool_id" {
  description = "Existing or new Workload Identity pool used by GitHub Actions."
  type        = string
  default     = "github-pool"

  validation {
    condition     = can(regex("^[a-z](?:[-a-z0-9]{2,30}[a-z0-9])$", var.workload_identity_pool_id))
    error_message = "workload_identity_pool_id must be a valid workload identity pool ID."
  }
}

variable "workload_identity_provider_id" {
  description = "Existing or new OIDC provider inside the GitHub Actions pool."
  type        = string
  default     = "github-provider"

  validation {
    condition     = can(regex("^[a-z](?:[-a-z0-9]{2,30}[a-z0-9])$", var.workload_identity_provider_id))
    error_message = "workload_identity_provider_id must be a valid workload identity provider ID."
  }
}
