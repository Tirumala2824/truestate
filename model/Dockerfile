FROM python:3.12-slim
WORKDIR /app
COPY model/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY model model
USER 10001
EXPOSE 8080
CMD ["uvicorn", "model.server:app", "--host", "0.0.0.0", "--port", "8080"]
