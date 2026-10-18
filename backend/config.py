"""Configuration is explicit; no local database or synthetic service fallback."""
import os
from functools import lru_cache
from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    project: str = ''
    region: str = 'us-central1'
    organization: str = 'default'
    mode: str = 'app'
    public_demo: bool = False

    @model_validator(mode='after')
    def validate_public_demo(self):
        if self.public_demo and (self.mode != 'app' or not self.organization.startswith('synthetic-')):
            raise ValueError('Public access requires an app in a synthetic-* organization.')
        return self
    gemini_model: str = ''
    gemini_location: str = 'us'
    sql_instance: str = ''
    sql_database: str = 'truestate'
    sql_user: str = ''
    sql_private_ip: bool = False
    bucket: str = ''
    bq_dataset: str = 'truestate'
    bq_location: str = 'US'
    document_processor: str = ''
    document_location: str = 'us'
    search_data_store: str = ''
    search_location: str = 'global'
    prediction_endpoint: str = ''
    topic: str = ''
    action_topic: str = ''
    iap_audience: str = ''
    worker_audience: str = ''
    worker_caller: str = ''
    reviewers: list[str] = Field(default_factory=list)
    source_connectors: list[str] = Field(default_factory=list)
    policy_path: str = 'automation-policy.yaml'
    max_upload_bytes: int = 20 * 1024 * 1024

    def missing(self) -> list[str]:
        fields = ['project', 'gemini_model', 'sql_instance', 'sql_user', 'bucket',
                  'document_processor', 'search_data_store', 'topic', 'action_topic']
        fields += ['iap_audience'] if self.mode == 'app' else ['worker_audience', 'worker_caller']
        return [name for name in fields if not getattr(self, name)]


@lru_cache
def settings() -> Settings:
    names = {
        'project': 'GOOGLE_CLOUD_PROJECT', 'region': 'GOOGLE_CLOUD_LOCATION',
        'organization': 'ORGANIZATION_ID', 'mode': 'SERVICE_MODE',
        'gemini_model': 'GEMINI_MODEL', 'gemini_location': 'GEMINI_LOCATION', 'sql_instance': 'INSTANCE_CONNECTION_NAME',
        'sql_database': 'DB_NAME', 'sql_user': 'DB_IAM_USER', 'bucket': 'EVIDENCE_BUCKET',
        'bq_dataset': 'BIGQUERY_DATASET', 'bq_location': 'BIGQUERY_LOCATION',
        'document_processor': 'DOCUMENT_AI_PROCESSOR', 'document_location': 'DOCUMENT_AI_LOCATION',
        'search_data_store': 'SEARCH_DATA_STORE', 'search_location': 'SEARCH_LOCATION',
        'prediction_endpoint': 'VERTEX_PREDICTION_ENDPOINT', 'topic': 'EVENT_TOPIC',
        'action_topic': 'ACTION_TOPIC', 'iap_audience': 'IAP_AUDIENCE',
        'worker_audience': 'WORKER_AUDIENCE', 'worker_caller': 'WORKER_CALLER_EMAIL',
        'policy_path': 'AUTOMATION_POLICY_PATH',
    }
    values = {field: os.environ[name] for field, name in names.items() if os.environ.get(name)}
    values['reviewers'] = [v.strip().lower() for v in os.getenv('REVIEWER_EMAILS', '').split(',') if v.strip()]
    values['source_connectors'] = [v.strip().lower() for v in os.getenv('SOURCE_CONNECTOR_EMAILS', '').split(',') if v.strip()]
    values['public_demo'] = os.getenv('PUBLIC_DEMO', 'false').lower() == 'true'
    values['sql_private_ip'] = os.getenv('SQL_PRIVATE_IP', 'false').lower() == 'true'
    return Settings(**values)
