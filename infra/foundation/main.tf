terraform {

  required_version = ">= 1.9"
  backend "gcs" {

  }

  required_providers {

    google = {
      source = "hashicorp/google", version = "~> 7.0"
    }

    random = {
      source = "hashicorp/random", version = "~> 3.7"
    }


  }


}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "document_location" {
  type    = string
  default = "us"
}

variable "search_location" {
  type    = string
  default = "global"
}

variable "bigquery_location" {
  type    = string
  default = "US"
}

variable "sql_tier" {
  type    = string
  default = "db-custom-2-7680"
}
variable "sql_disk_size" {
  type    = number
  default = 50
  validation {
    condition     = var.sql_disk_size >= 10
    error_message = "Cloud SQL disk size must be at least 10 GB."
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "project" {
  project_id = var.project_id
}

locals {

  apis = toset(["run.googleapis.com", "cloudbuild.googleapis.com", "artifactregistry.googleapis.com",
    "sqladmin.googleapis.com", "aiplatform.googleapis.com", "documentai.googleapis.com",
    "discoveryengine.googleapis.com", "bigquery.googleapis.com", "pubsub.googleapis.com",
    "storage.googleapis.com", "secretmanager.googleapis.com", "iap.googleapis.com",
  "cloudscheduler.googleapis.com", "iamcredentials.googleapis.com"])

}

resource "google_project_service" "enabled" {

  for_each           = local.apis
  service            = each.value
  disable_on_destroy = false

}

resource "google_service_account" "runtime" {

  account_id   = "truestate-runtime"
  display_name = "TRUESTATE application and agent runtime"

}

resource "google_service_account" "push" {
  account_id = "truestate-events"
}

resource "google_service_account" "migrate" {
  account_id = "truestate-migrate"
}

resource "google_service_account" "build" {
  account_id = "truestate-build"
}

resource "google_project_iam_member" "runtime" {
  project = var.project_id

  for_each = toset(["roles/cloudsql.client", "roles/cloudsql.instanceUser", "roles/aiplatform.user",
  "roles/documentai.apiUser", "roles/documentai.viewer", "roles/discoveryengine.editor", "roles/bigquery.jobUser", "roles/logging.logWriter"])
  role   = each.value
  member = "serviceAccount:${google_service_account.runtime.email}"

}

resource "google_project_iam_member" "migration_sql" {
  project = var.project_id

  role   = "roles/cloudsql.client"
  member = "serviceAccount:${google_service_account.migrate.email}"

}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id

  role   = "roles/logging.logWriter"
  member = "serviceAccount:${google_service_account.build.email}"

}

resource "google_storage_bucket" "evidence" {

  name                        = "${var.project_id}-truestate-evidence"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning {
    enabled = true
  }


}

resource "google_storage_bucket_iam_member" "evidence" {

  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime.email}"

}

resource "google_storage_bucket_iam_member" "evidence_metadata" {

  bucket = google_storage_bucket.evidence.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.runtime.email}"

}

resource "google_storage_bucket" "build" {

  name                        = "${var.project_id}-truestate-build"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

}

resource "google_storage_bucket_iam_member" "build" {

  bucket = google_storage_bucket.build.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.build.email}"

}

resource "google_storage_bucket_iam_member" "build_metadata" {

  # Cloud Build validates the source/log bucket with storage.buckets.get.
  # Object Admin grants object access, but does not grant bucket metadata access.
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.build.email}"

}

resource "google_artifact_registry_repository" "images" {

  location      = var.region
  repository_id = "truestate"
  format        = "DOCKER"
  depends_on    = [google_project_service.enabled]

}

resource "google_artifact_registry_repository_iam_member" "build" {

  location   = var.region
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"

}

resource "google_sql_database_instance" "db" {

  name                = "truestate-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true
  settings {

    tier              = var.sql_tier
    edition           = "ENTERPRISE"
    disk_size         = var.sql_disk_size
    disk_autoresize   = true
    availability_type = "ZONAL"
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }


  }

  depends_on = [google_project_service.enabled]

}

resource "google_sql_database" "application" {

  name     = "truestate"
  instance = google_sql_database_instance.db.name

}

resource "google_sql_user" "runtime" {

  name     = trimsuffix(google_service_account.runtime.email, ".gserviceaccount.com")
  instance = google_sql_database_instance.db.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"

}

resource "random_password" "migration" {
  length  = 40
  special = false
}

resource "google_sql_user" "migration" {

  name     = "truestate_migrator"
  instance = google_sql_database_instance.db.name
  password = random_password.migration.result

}

resource "google_secret_manager_secret" "migration" {

  secret_id = "truestate-migration-db-password"
  replication {
    auto {

    }

  }

  depends_on = [google_project_service.enabled]

}

resource "google_secret_manager_secret_version" "migration" {

  secret      = google_secret_manager_secret.migration.id
  secret_data = random_password.migration.result

}

resource "google_secret_manager_secret_iam_member" "migration" {

  secret_id = google_secret_manager_secret.migration.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.migrate.email}"

}

resource "google_bigquery_dataset" "risk" {

  dataset_id                 = "truestate"
  location                   = var.bigquery_location
  delete_contents_on_destroy = false
  depends_on                 = [google_project_service.enabled]

}

resource "google_bigquery_dataset_iam_member" "risk" {

  dataset_id = google_bigquery_dataset.risk.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.runtime.email}"

}

resource "google_bigquery_table" "events" {

  dataset_id          = google_bigquery_dataset.risk.dataset_id
  table_id            = "risk_events"
  deletion_protection = true
  time_partitioning {
    type  = "DAY"
    field = "recorded_at"
  }

  clustering = ["organization", "transaction_id"]
  schema     = file("${path.module}/risk-events.json")

}

resource "google_bigquery_table" "training" {

  dataset_id          = google_bigquery_dataset.risk.dataset_id
  table_id            = "risk_training"
  deletion_protection = true
  schema              = file("${path.module}/risk-training.json")

}

resource "google_document_ai_processor" "documents" {

  location     = var.document_location
  display_name = "TRUESTATE document extraction"
  type         = "OCR_PROCESSOR"
  depends_on   = [google_project_service.enabled]

}

resource "google_discovery_engine_data_store" "knowledge" {

  location          = var.search_location
  data_store_id     = "truestate-policies-v2"
  display_name      = "TRUESTATE organization policies"
  industry_vertical = "GENERIC"
  content_config    = "CONTENT_REQUIRED"
  solution_types    = ["SOLUTION_TYPE_SEARCH"]
  acl_enabled       = false
  # Match the API's default so refresh does not propose a replacement on retry.
  document_processing_config {
    default_parsing_config {
      digital_parsing_config {}
    }
  }
  lifecycle {
    prevent_destroy = true
  }
  depends_on = [google_project_service.enabled]

}

resource "google_pubsub_topic" "events" {

  name                       = "truestate-events"
  message_retention_duration = "604800s"
  depends_on                 = [google_project_service.enabled]

}

resource "google_pubsub_topic" "actions" {

  name                       = "truestate-action-requests"
  message_retention_duration = "604800s"
  depends_on                 = [google_project_service.enabled]

}

resource "google_pubsub_topic" "deadletter" {

  name                       = "truestate-dead-letter"
  message_retention_duration = "604800s"
  depends_on                 = [google_project_service.enabled]

}

resource "google_pubsub_topic_iam_member" "publish" {

  for_each = {
    events = google_pubsub_topic.events.name, actions = google_pubsub_topic.actions.name
  }

  topic  = each.value
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.runtime.email}"

}

resource "google_pubsub_topic_iam_member" "read_metadata" {

  topic  = google_pubsub_topic.events.name
  role   = "roles/pubsub.viewer"
  member = "serviceAccount:${google_service_account.runtime.email}"

}

output "configuration" {

  value = {

    project_id         = var.project_id, project_number = data.google_project.project.number, region = var.region,
    runtime_email      = google_service_account.runtime.email, push_email = google_service_account.push.email,
    migration_email    = google_service_account.migrate.email, build_email = google_service_account.build.email,
    build_bucket       = google_storage_bucket.build.name, evidence_bucket = google_storage_bucket.evidence.name,
    sql_instance       = google_sql_database_instance.db.connection_name, sql_user = google_sql_user.runtime.name,
    sql_database       = google_sql_database.application.name, migration_user = google_sql_user.migration.name,
    migration_secret   = google_secret_manager_secret.migration.secret_id,
    document_processor = google_document_ai_processor.documents.id, document_location = var.document_location,
    search_data_store  = google_discovery_engine_data_store.knowledge.data_store_id, search_location = var.search_location,
    bigquery_dataset   = google_bigquery_dataset.risk.dataset_id, bigquery_location = var.bigquery_location,
    event_topic        = google_pubsub_topic.events.id, action_topic = google_pubsub_topic.actions.id,
    deadletter_topic   = google_pubsub_topic.deadletter.id

  }


}
