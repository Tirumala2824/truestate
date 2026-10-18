variable "foundation" { type = map(string) }
variable "gemini_model" { type = string }
variable "organization_id" { type = string }
variable "reviewer_emails" { type = list(string) }
variable "source_connector_emails" { type = list(string) }
variable "prediction_endpoint" { type = string }
variable "release_sha" { type = string }
variable "seed_organization_id" { type = string }

output "values" {
  value = {
    GOOGLE_CLOUD_PROJECT        = var.foundation.project_id
    GOOGLE_CLOUD_LOCATION       = var.foundation.region
    GOOGLE_GENAI_USE_VERTEXAI   = "true"
    GOOGLE_GENAI_USE_ENTERPRISE = "true"
    GEMINI_MODEL                = var.gemini_model
    ORGANIZATION_ID             = var.organization_id
    INSTANCE_CONNECTION_NAME    = var.foundation.sql_instance
    DB_IAM_USER                 = var.foundation.sql_user
    DB_NAME                     = var.foundation.sql_database
    EVIDENCE_BUCKET             = var.foundation.evidence_bucket
    DOCUMENT_AI_PROCESSOR       = var.foundation.document_processor
    DOCUMENT_AI_LOCATION        = var.foundation.document_location
    SEARCH_DATA_STORE           = var.foundation.search_data_store
    SEARCH_LOCATION             = var.foundation.search_location
    BIGQUERY_DATASET            = var.foundation.bigquery_dataset
    BIGQUERY_LOCATION           = var.foundation.bigquery_location
    EVENT_TOPIC                 = var.foundation.event_topic
    ACTION_TOPIC                = var.foundation.action_topic
    VERTEX_PREDICTION_ENDPOINT  = var.prediction_endpoint
    IAP_AUDIENCE                = "/projects/${var.foundation.project_number}/locations/${var.foundation.region}/services/truestate"
    WORKER_AUDIENCE             = "https://truestate.internal/${var.foundation.project_id}/worker"
    WORKER_CALLER_EMAIL         = var.foundation.push_email
    REVIEWER_EMAILS             = join(",", var.reviewer_emails)
    SOURCE_CONNECTOR_EMAILS     = join(",", var.source_connector_emails)
    SEED_ORGANIZATION_ID        = var.seed_organization_id
    RELEASE_SHA                 = var.release_sha
  }
}
