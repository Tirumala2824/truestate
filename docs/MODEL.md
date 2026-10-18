# Real Vertex prediction

The runtime calls a configured Vertex endpoint with one instance containing `amount`, `currency`, `account_changed` (0/1), `document_count`, `content_roots` and `attested_origins`. It requires one prediction object containing a finite `risk_probability` between 0 and 1. Endpoint errors propagate; no replacement score is produced. The service returns Vertex model/deployed-model identifiers with successful predictions.

The optional baseline uses scikit-learn logistic regression, trained inside Vertex custom training. It is a starting point for your data, not a pretrained fraud detector. Populate `PROJECT.truestate.risk_training` with actual adjudicated labels using the schema in `infra/foundation/risk-training.json`. Define label 1 consistently as the risk outcome your team has adjudicated. Do not use model-generated decisions as ground-truth labels. Avoid features derived after the outcome.

Training requires at least 500 labeled records, at least 300 training and 100 holdout records, both labels with at least 20 examples per split, and a time-ordered holdout whose supplier identities are excluded from training. It uses a single currency and rejects a dataset over 100,000 rows rather than silently training on a partial sample. It records measured ROC AUC, average precision, Brier score, population size and prevalence. Training fails if the operator-supplied minimum AUC is not met. These gates are engineering checks, not evidence of production fitness; evaluate calibration, drift and bias for your use case.

After the foundation is deployed, build the model image with `./scripts/build-model.sh`. It uses Cloud Build, the private build bucket and Artifact Registry created by the deployment. Export its printed `MODEL_IMAGE`, choose `TRAINING_CURRENCY` and `REQUIRED_AUC`, then run:

```bash
python scripts/train-and-deploy.py \
  --project "$PROJECT_ID" --region "$REGION" \
  --image "$MODEL_IMAGE" \
  --bucket "gs://${PROJECT_ID}-truestate-evidence" \
  --service-account "truestate-runtime@${PROJECT_ID}.iam.gserviceaccount.com" \
  --table "${PROJECT_ID}.truestate.risk_training" \
  --currency "$TRAINING_CURRENCY" --minimum-auc "$REQUIRED_AUC"
```

This explicit command creates billable training and a continuously provisioned prediction endpoint with one minimum replica. It does not run during ordinary application deployment. The invoking principal needs Vertex administration and service-account impersonation permissions; the training identity needs read access to the training table and write access to its artifact bucket. The provisioned runtime identity has those permissions in the prototype project. Separate training and serving identities in a production deployment.

Set the returned full endpoint resource name as `VERTEX_PREDICTION_ENDPOINT` and redeploy the application. The serving container loads only the private model artifact provided through Vertex `AIP_STORAGE_URI`; it fails startup without a real artifact. It rejects currencies different from its training currency. For multi-currency workflows, deploy a reviewed model with appropriate currency handling and the same request/response contract.

Reference: [Google CustomContainerTrainingJob API](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.CustomContainerTrainingJob). No training or live prediction was run during this development session because no labeled data or GCP project access was available.
