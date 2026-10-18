from unittest.mock import patch

from backend.config import Settings, settings
from backend.gcp import GoogleCloud


def test_model_client_uses_its_supported_location_independently_of_infrastructure():
    config = Settings(project='test-project', region='us-central1', gemini_location='us')
    with patch('google.genai.Client') as client:
        assert GoogleCloud(config).genai is client.return_value
    assert client.call_args.kwargs['location'] == 'us'
    assert config.region == 'us-central1'


def test_gemini_location_override_preserves_cloud_region(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_LOCATION', 'us-central1')
    monkeypatch.setenv('GEMINI_LOCATION', 'eu')
    settings.cache_clear()
    try:
        config = settings()
        assert config.gemini_location == 'eu'
        assert config.region == 'us-central1'
    finally:
        settings.cache_clear()
