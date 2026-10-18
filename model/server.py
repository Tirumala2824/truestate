"""Vertex custom prediction container. Only load artifacts from the private model bucket."""
import io
import os
from contextlib import asynccontextmanager
import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from google.cloud import storage


@asynccontextmanager
async def lifespan(app):
    uri = os.environ['AIP_STORAGE_URI']
    if not uri.startswith('gs://'):
        raise RuntimeError('A private Vertex model artifact URI is required.')
    bucket, prefix = uri[5:].split('/', 1)
    raw = storage.Client().bucket(bucket).blob(prefix.rstrip('/') + '/model.joblib').download_as_bytes()
    app.state.model = joblib.load(io.BytesIO(raw))
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, openapi_url=None)


class Instance(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    amount: float = Field(gt=0)
    currency: str = Field(pattern='^[A-Z]{3}$')
    account_changed: int = Field(ge=0, le=1)
    document_count: int = Field(ge=0)
    content_roots: int = Field(ge=0)
    attested_origins: int = Field(ge=0)


class Predict(BaseModel):
    model_config = ConfigDict(extra='forbid')
    instances: list[Instance] = Field(min_length=1, max_length=100)
    parameters: dict | None = None


@app.get('/health')
def health():
    if not getattr(app.state, 'model', None):
        raise HTTPException(503, 'Model not loaded')
    return {'status': 'ready'}


@app.post('/predict')
def predict(body: Predict):
    model = app.state.model
    if any(i.currency != model['currency'] for i in body.instances):
        raise HTTPException(422, 'The model was trained for a different currency.')
    features = np.asarray([[getattr(i, k) for k in model['features']] for i in body.instances], dtype=float)
    return {'predictions': [{'risk_probability': float(p)} for p in model['estimator'].predict_proba(features)[:, 1]]}
