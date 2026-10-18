FROM node:24-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY index.html tsconfig.json vite.config.ts ./
COPY frontend ./frontend
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY agents ./agents
COPY automation-policy.yaml ./
COPY --from=frontend /app/dist ./dist
RUN useradd --uid 10001 --create-home app && chown -R app:app /app
USER app
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--timeout-keep-alive", "15"]
