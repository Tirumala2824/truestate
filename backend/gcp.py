"""Real managed-service clients; failures are propagated, never replaced with examples."""
import json
import re
import hashlib
from functools import cached_property
from google.api_core.client_options import ClientOptions
from .domain import digest


class GoogleCloud:
    def __init__(self, settings):
        self.s = settings

    @cached_property
    def storage(self):
        from google.cloud import storage
        return storage.Client(project=self.s.project)

    @cached_property
    def publisher(self):
        from google.cloud import pubsub_v1
        return pubsub_v1.PublisherClient()

    @cached_property
    def bigquery(self):
        from google.cloud import bigquery
        return bigquery.Client(project=self.s.project, location=self.s.bq_location)

    @cached_property
    def genai(self):
        from google import genai
        from google.genai import types
        return genai.Client(vertexai=True, project=self.s.project, location=self.s.region,
                            http_options=types.HttpOptions(api_version='v1', timeout=90000))

    def put_object(self, key, data: bytes, mime):
        from google.api_core.exceptions import PreconditionFailed
        blob = self.storage.bucket(self.s.bucket).blob(key)
        try:
            blob.upload_from_string(data, content_type=mime, if_generation_match=0, timeout=60)
        except PreconditionFailed:
            blob.reload()
            existing = blob.download_as_bytes(if_generation_match=int(blob.generation), timeout=60)
            if hashlib.sha256(existing).digest() != hashlib.sha256(data).digest():
                raise ValueError('An immutable evidence object already contains different bytes.')
        return {'object': key, 'generation': str(blob.generation), 'uri': f'gs://{self.s.bucket}/{key}',
                'content_sha256': hashlib.sha256(data).hexdigest()}

    def read_object(self, doc):
        return self.storage.bucket(self.s.bucket).blob(doc['object'], generation=int(doc['generation'])).download_as_bytes(timeout=60)

    def extract(self, data, mime):
        if mime in {'text/plain', 'message/rfc822', 'text/csv'}:
            text = data.decode('utf-8-sig')
            return {'text': text[:150000], 'entities': [], 'processor': 'utf8-text',
                    'truncated': len(text) > 150000}
        from google.cloud import documentai_v1 as documentai
        client = documentai.DocumentProcessorServiceClient(client_options=ClientOptions(
            api_endpoint=f'{self.s.document_location}-documentai.googleapis.com'))
        response = client.process_document(request=documentai.ProcessRequest(
            name=self.s.document_processor, raw_document=documentai.RawDocument(content=data, mime_type=mime)), timeout=120)
        doc = response.document
        return {'text': doc.text[:150000], 'entities': [{'type': e.type_, 'value': e.mention_text,
                 'confidence': e.confidence} for e in doc.entities],
                'pages': len(doc.pages), 'processor': self.s.document_processor, 'truncated': len(doc.text) > 150000}

    def _search_options(self):
        return ClientOptions(api_endpoint=f'{self.s.search_location}-discoveryengine.googleapis.com') if self.s.search_location != 'global' else None

    def _branch(self):
        return (f'projects/{self.s.project}/locations/{self.s.search_location}/collections/default_collection/'
                f'dataStores/{self.s.search_data_store}/branches/default_branch')

    def index_policy(self, doc):
        from google.cloud import discoveryengine_v1 as discoveryengine
        from google.api_core.exceptions import AlreadyExists
        client = discoveryengine.DocumentServiceClient(client_options=self._search_options())
        document = discoveryengine.Document(id=doc['id'],
            content=discoveryengine.Document.Content(raw_bytes=doc['text'].encode(), mime_type='text/plain'),
            struct_data={'title': doc['filename'], 'organization': self.s.organization,
                         'sha256': doc['content_sha256']})
        try:
            result = client.create_document(parent=self._branch(), document=document, document_id=doc['id'], timeout=60)
            return {'resource': result.name, 'status': 'submitted'}
        except AlreadyExists:
            return {'resource': self._branch() + '/documents/' + doc['id'], 'status': 'submitted'}

    def search(self, query):
        from google.cloud import discoveryengine_v1 as discoveryengine
        from google.protobuf.json_format import MessageToDict
        client = discoveryengine.SearchServiceClient(client_options=self._search_options())
        request = discoveryengine.SearchRequest(
            serving_config=self._branch().replace('/branches/default_branch', '/servingConfigs/default_search'),
            query=query[:2000], page_size=8,
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(return_snippet=True)))
        response = client.search(request=request, timeout=45)
        return [{'id': r.document.id, 'metadata': MessageToDict(r.document._pb.derived_struct_data)}
                for r in response.results]

    def publish(self, payload, action=False):
        name = self.s.action_topic if action else self.s.topic
        topic = name if name.startswith('projects/') else self.publisher.topic_path(self.s.project, name)
        return self.publisher.publish(topic, json.dumps(payload, default=str).encode(),
                                      organization=self.s.organization).result(timeout=30)

    def predict(self, features):
        if not self.s.prediction_endpoint:
            return {'status': 'not_configured', 'risk_probability': None}
        from google.cloud import aiplatform_v1
        from google.protobuf.json_format import ParseDict, MessageToDict
        from google.protobuf.struct_pb2 import Value
        client = aiplatform_v1.PredictionServiceClient(client_options=ClientOptions(api_endpoint=f'{self.s.region}-aiplatform.googleapis.com'))
        response = client.predict(endpoint=self.s.prediction_endpoint,
                                  instances=[ParseDict(features, Value())], timeout=60)
        if len(response.predictions) != 1:
            raise ValueError('Prediction endpoint returned an unexpected response count.')
        prediction = dict(response.predictions[0])
        probability = float(prediction['risk_probability'])
        if not 0 <= probability <= 1:
            raise ValueError('Prediction must return risk_probability between zero and one.')
        return {'status': 'succeeded', 'risk_probability': probability,
                'endpoint': self.s.prediction_endpoint, 'model': response.model,
                'deployed_model_id': response.deployed_model_id}

    def _table(self, name):
        if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]', self.s.project):
            raise ValueError('Invalid project ID')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,1023}', self.s.bq_dataset):
            raise ValueError('Invalid BigQuery dataset')
        return f'{self.s.project}.{self.s.bq_dataset}.{name}'

    def write_analytics(self, transaction, run_id, decision, prediction):
        from google.cloud import bigquery
        # Stable event id + MERGE avoids duplicate facts on Pub/Sub retries.
        values = {'event_id': run_id, 'organization': self.s.organization,
                  'transaction_id': transaction['id'], 'supplier_id': transaction['supplier_id'],
                  'currency': transaction['currency'], 'amount': str(transaction['amount']),
                  'disposition': decision['disposition'], 'snapshot_hash': decision['snapshot_hash'],
                  'risk_probability': prediction.get('risk_probability')}
        params = [bigquery.ScalarQueryParameter(k, 'FLOAT64' if k == 'risk_probability' else 'STRING', v)
                  for k, v in values.items()]
        query = f'''MERGE `{self._table('risk_events')}` t USING (SELECT @event_id event_id) s
          ON t.event_id=s.event_id AND t.organization=@organization
          WHEN NOT MATCHED THEN INSERT
          (event_id, organization, transaction_id, supplier_id, currency, amount, disposition, snapshot_hash, risk_probability, recorded_at)
          VALUES (@event_id,@organization,@transaction_id,@supplier_id,@currency,CAST(@amount AS NUMERIC),
                  @disposition,@snapshot_hash,@risk_probability,CURRENT_TIMESTAMP())'''
        self.bigquery.query(query, job_config=bigquery.QueryJobConfig(query_parameters=params,
            maximum_bytes_billed=1_000_000_000)).result(timeout=60)

    def analytics(self):
        from google.cloud import bigquery
        # Latest assessment per transaction; currencies remain separate.
        query = f'''WITH latest AS (SELECT *, ROW_NUMBER() OVER
          (PARTITION BY organization,transaction_id ORDER BY recorded_at DESC) rank
          FROM `{self._table('risk_events')}` WHERE organization=@organization)
          SELECT currency, disposition, COUNT(*) transactions, SUM(amount) amount
          FROM latest WHERE rank=1 GROUP BY currency,disposition ORDER BY currency,disposition'''
        rows = self.bigquery.query(query, job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter('organization', 'STRING', self.s.organization)],
            maximum_bytes_billed=1_000_000_000)).result(timeout=60)
        return [{**dict(r), 'amount': str(r['amount'])} for r in rows]

    def verify(self):
        """Read actual resource metadata; configured does not mean verified."""
        from google.cloud import documentai_v1, discoveryengine_v1
        checks = {}
        probes = {
            'Cloud Storage': lambda: self.storage.get_bucket(self.s.bucket),
            'BigQuery': lambda: self.bigquery.get_table(self._table('risk_events')),
            'Document AI': lambda: documentai_v1.DocumentProcessorServiceClient(client_options=ClientOptions(
                api_endpoint=f'{self.s.document_location}-documentai.googleapis.com')).get_processor(name=self.s.document_processor),
            'Vertex AI Search': lambda: discoveryengine_v1.DataStoreServiceClient(client_options=self._search_options()).get_data_store(
                name=self._branch().split('/branches/')[0]),
            'Pub/Sub': lambda: self.publisher.get_topic(topic=self.s.topic if self.s.topic.startswith('projects/') else self.publisher.topic_path(self.s.project, self.s.topic)),
        }
        for name, probe in probes.items():
            try:
                probe()
                checks[name] = {'status': 'reachable'}
            except Exception as exc:
                checks[name] = {'status': 'error', 'error_type': type(exc).__name__}
        checks['Gemini'] = {'status': 'configured_not_invoked', 'model': self.s.gemini_model}
        checks['Vertex prediction'] = {'status': 'configured_not_invoked' if self.s.prediction_endpoint else 'not_configured'}
        return checks
