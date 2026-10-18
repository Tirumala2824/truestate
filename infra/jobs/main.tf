terraform {
  required_version = ">= 1.9"
  backend "gcs" {}
  required_providers {
    google = { source = "hashicorp/google", version = "~> 7.0" }
  }
}
variable "foundation" { type = map(string) }
variable "image" { type = string }
variable "gemini_model" { type = string }
variable "gemini_location" {
  type    = string
  default = "us"
}
variable "organization_id" { type = string }
variable "reviewer_emails" { type = list(string) }
variable "source_connector_emails" { type = list(string) }
variable "prediction_endpoint" { type = string }
variable "release_sha" { type = string }
variable "seed_organization_id" {
  type = string
  validation {
    condition     = can(regex("^synthetic-[a-z0-9][a-z0-9-]{0,88}$", var.seed_organization_id))
    error_message = "Seed data must use a reserved synthetic-* organization."
  }
}
provider "google" {
  project = var.foundation.project_id
  region  = var.foundation.region
}
module "environment" {
  source                  = "../modules/environment"
  foundation              = var.foundation
  gemini_model            = var.gemini_model
  gemini_location         = var.gemini_location
  reviewer_emails         = var.reviewer_emails
  source_connector_emails = var.source_connector_emails
  prediction_endpoint     = var.prediction_endpoint
  organization_id         = var.organization_id
  release_sha             = var.release_sha
  seed_organization_id    = var.seed_organization_id
}
locals {
  jobs = {
    migrate = { name = "truestate-release-migrate", module = "backend.migrate", timeout = "1200s", memory = "1Gi", retries = 1 }
    seed    = { name = "truestate-seed", module = "backend.seed", timeout = "3600s", memory = "2Gi", retries = 1 }
    verify  = { name = "truestate-release-verify", module = "backend.release_check", timeout = "1200s", memory = "1Gi", retries = 1 }
  }
}
resource "google_cloud_run_v2_job" "release" {
  for_each            = local.jobs
  name                = each.value.name
  location            = var.foundation.region
  deletion_protection = false
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = each.key == "verify" ? var.foundation.runtime_email : var.foundation.migration_email
      timeout         = each.value.timeout
      max_retries     = each.value.retries
      containers {
        image   = var.image
        command = ["python", "-m", each.value.module]
        resources { limits = { cpu = "2", memory = each.value.memory } }
        dynamic "env" {
          for_each = merge(module.environment.values, { SERVICE_MODE = "worker" },
          each.key == "verify" ? {} : { MIGRATION_DB_USER = var.foundation.migration_user })
          content {
            name  = env.key
            value = env.value
          }
        }
        dynamic "env" {
          for_each = each.key == "verify" ? [] : [1]
          content {
            name = "MIGRATION_DB_PASSWORD"
            value_source {
              secret_key_ref {
                secret  = var.foundation.migration_secret
                version = "latest"
              }
            }
          }
        }
      }
    }
  }
}
output "job_names" { value = { for key, job in google_cloud_run_v2_job.release : key => job.name } }
