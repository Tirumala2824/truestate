# Reused components

| Component | Actual use | Upstream |
|---|---|---|
| Google ADK (Apache-2.0) | Parallel specialist and sequential resolution agents | https://github.com/google/adk-python |
| Google Gen AI SDK (Apache-2.0) | Gemini on Vertex AI, streaming explanations | https://github.com/googleapis/python-genai |
| Google Cloud SDK clients (Apache-2.0) | Document AI, Search, BigQuery, Pub/Sub, Storage, Vertex AI | https://github.com/googleapis/google-cloud-python |
| Cloud SQL Python Connector (Apache-2.0) | IAM database connections | https://github.com/GoogleCloudPlatform/cloud-sql-python-connector |
| FastAPI (MIT) / SQLAlchemy (MIT) | Typed APIs and transactional persistence | https://github.com/fastapi/fastapi / https://github.com/sqlalchemy/sqlalchemy |
| Alembic (MIT) | Versioned schema migrations, legacy adoption and SQL generation | https://github.com/sqlalchemy/alembic |
| React (MIT), Vite (MIT), Lucide (ISC) | Responsive operations console and icons | https://github.com/facebook/react / https://github.com/vitejs/vite / https://github.com/lucide-icons/lucide |
| scikit-learn (BSD-3-Clause) | Optional real-data baseline training | https://github.com/scikit-learn/scikit-learn |

Installed package distributions retain upstream licenses. Versions are pinned in the application manifests. ADK 2.12 still supports the chosen ParallelAgent/SequentialAgent API but emits deprecation warnings in favor of Workflow; a future ADK upgrade should migrate and regression-test orchestration.

The repository's finance/security/legal skills are task-specific instructions loaded into ADK. No unreviewed remote skill code is fetched at runtime. Google's [ADK recipes](https://github.com/google/adk-recipes) and [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack) were examined as references; this repository does not claim to embed their entire platforms or import unused recipes.
