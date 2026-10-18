terraform {

  required_version = ">= 1.9"
  backend "gcs" {

  }

  required_providers {
    google = {
      source = "hashicorp/google", version = "~> 7.0"
    }

  }


}

variable "foundation" {
  type = map(string)
}

variable "image" {
  type = string
}

variable "gemini_model" {
  type = string
}

variable "reoperator_emails" {
  type = list(string)
}

variable "operator_emails" {
  type    = list(string)
  default = []
}

variable "source_connector_emails" {
  type    = list(string)
  default = []
}

variable "prediction_endpoint" {
  type    = string
  default = ""
}

variable "organization_id" {
  type    = string
  default = "default"
}

provider "google" {
  project = var.foundation.project_id
  region  = var.foundation.region
}

locals {

  worker_audience = "https://truestate.internal/${var.foundation.project_id}/worker"
  environment = {

    GOOGLE_CLOUD_PROJECT      = var.foundation.project_id, GOOGLE_CLOUD_LOCATION = var.foundation.region,
    GOOGLE_GENAI_USE_VERTEXAI = "true", GOOGLE_GENAI_USE_ENTERPRISE = "true", GEMINI_MODEL = var.gemini_model,
    ORGANIZATION_ID           = var.organization_id, INSTANCE_CONNECTION_NAME = var.foundation.sql_instance,
    DB_IAM_USER               = var.foundation.sql_user, DB_NAME = var.foundation.sql_database,
    EVIDENCE_BUCKET           = var.foundation.evidence_bucket, DOCUMENT_AI_PROCESSOR = var.foundation.document_processor,
    DOCUMENT_AI_LOCATION      = var.foundation.document_location, SEARCH_DATA_STORE = var.foundation.search_data_store,
    SEARCH_LOCATION           = var.foundation.search_location, BIGQUERY_DATASET = var.foundation.bigquery_dataset,
    BIGQUERY_LOCATION         = var.foundation.bigquery_location, EVENT_TOPIC = var.foundation.event_topic,
    ACTION_TOPIC              = var.foundation.action_topic, VERTEX_PREDICTION_ENDPOINT = var.prediction_endpoint,
    IAP_AUDIENCE              = "/projects/${var.foundation.project_number}/locations/${var.foundation.region}/services/truestate",
    WORKER_AUDIENCE           = local.worker_audience, WORKER_CALLER_EMAIL = var.foundation.push_email,
    REOPERATOR_EMAILS         = join(",", var.reoperator_emails), SOURCE_CONNECTOR_EMAILS = join(",", var.source_connector_emails)

  }


}

resource "google_cloud_run_v2_job" "migrate" {

  name                = "truestate-migrate"
  location            = var.foundation.region
  deletion_protection = false
  template {

    template {

      service_account = var.foundation.migration_email
      timeout         = "600s"
      max_retries     = 1
      containers {

        image   = var.image
        command = ["python", "-m", "backend.migrate"]
        dynamic "env" {

          for_each = merge(local.environment, {
            MIGRATION_DB_USER = var.foundation.migration_user
            }
          )
          content {
            name  = env.key
            value = env.value
          }


        }

        env {

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

resource "google_cloud_run_v2_service" "app" {

  name                = "truestate"
  location            = var.foundation.region
  deletion_protection = false
  iap_enabled         = true
  ingress             = "INGRESS_TRAFFIC_ALL"
  template {

    service_account                  = var.foundation.runtime_email
    timeout                          = "360s"
    max_instance_request_concurrency = 30
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {

      image = var.image
      resources {
        limits = {
          cpu = "1", memory = "1Gi"
        }

      }

      dynamic "env" {

        for_each = merge(local.environment, {
          SERVICE_MODE = "app"
          }
        )
        content {
          name  = env.key
          value = env.value
        }


      }

      startup_probe {

        http_get {
          path = "/healthz"
        }

        period_seconds    = 10
        failure_threshold = 12

      }


    }


  }


}

resource "google_cloud_run_v2_service" "worker" {

  name                = "truestate-worker"
  location            = var.foundation.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  custom_audiences    = [local.worker_audience]
  template {

    service_account                  = var.foundation.runtime_email
    timeout                          = "600s"
    max_instance_request_concurrency = 4
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {

      image = var.image
      resources {
        limits = {
          cpu = "2", memory = "2Gi"
        }

      }

      dynamic "env" {

        for_each = merge(local.environment, {
          SERVICE_MODE = "worker"
          }
        )
        content {
          name  = env.key
          value = env.value
        }


      }

      startup_probe {

        http_get {
          path = "/healthz"
        }

        period_seconds    = 10
        failure_threshold = 12

      }


    }


  }


}

resource "google_cloud_run_v2_service_iam_member" "iap" {

  name     = google_cloud_run_v2_service.app.name
  location = var.foundation.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${var.foundation.project_number}@gcp-sa-iap.iam.gserviceaccount.com"

}

resource "google_iap_web_cloud_run_service_iam_member" "users" {

  for_each               = toset(concat(var.reoperator_emails, var.operator_emails))
  project                = var.foundation.project_id
  location               = var.foundation.region
  cloud_run_service_name = google_cloud_run_v2_service.app.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = "user:${each.value}"

}

resource "google_cloud_run_v2_service_iam_member" "worker" {

  for_each = toset(concat([var.foundation.push_email], var.source_connector_emails))
  name     = google_cloud_run_v2_service.worker.name
  location = var.foundation.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"

}

resource "google_service_account_iam_member" "pubsub_tokens" {

  service_account_id = "projects/${var.foundation.project_id}/serviceAccounts/${var.foundation.push_email}"
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${var.foundation.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"

}

resource "google_pubsub_subscription" "worker" {

  name                       = "truestate-worker"
  topic                      = var.foundation.event_topic
  ack_deadline_seconds       = 600
  message_retention_duration = "604800s"
  expiration_policy {
    ttl = ""
  }

  retry_policy {
    minimum_backoff = "60s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = var.foundation.deadletter_topic
    max_delivery_attempts = 10
  }

  push_config {

    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/internal/pubsub"
    oidc_token {
      service_account_email = var.foundation.push_email
      audience              = local.worker_audience
    }


  }

  depends_on = [google_cloud_run_v2_service_iam_member.worker, google_service_account_iam_member.pubsub_tokens]

}

resource "google_pubsub_subscription_iam_member" "forward_deadletter" {

  subscription = google_pubsub_subscription.worker.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${var.foundation.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"

}

resource "google_pubsub_topic_iam_member" "deadletter_publisher" {

  topic  = var.foundation.deadletter_topic
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${var.foundation.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"

}

resource "google_pubsub_subscription" "deadletter" {

  name                       = "truestate-dead-letter-review"
  topic                      = var.foundation.deadletter_topic
  message_retention_duration = "604800s"
  expiration_policy {
    ttl = ""
  }


}

resource "google_pubsub_subscription" "action_requests" {

  name                       = "truestate-action-requests"
  topic                      = var.foundation.action_topic
  message_retention_duration = "604800s"
  expiration_policy {
    ttl = ""
  }


}

resource "google_cloud_scheduler_job" "outbox" {

  name             = "truestate-dispatch"
  region           = var.foundation.region
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"
  http_target {

    uri         = "${google_cloud_run_v2_service.worker.uri}/internal/dispatch"
    http_method = "POST"
    oidc_token {
      service_account_email = var.foundation.push_email
      audience              = local.worker_audience
    }


  }


}

output "app_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "worker_url" {
  value = google_cloud_run_v2_service.worker.uri
}

output "migration_job" {
  value = google_cloud_run_v2_job.migrate.name
}

resource "google_pubsub_subscription_iam_member" "action_consumers" {
  for_each     = toset(var.source_connector_emails)
  subscription = google_pubsub_subscription.action_requests.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${each.value}"
}
resource "google_pubsub_topic_iam_member" "source_publishers" {
  for_each = toset(var.source_connector_emails)
  topic    = var.foundation.event_topic
  role     = "roles/pubsub.publisher"
  member   = "serviceAccount:${each.value}"
}
