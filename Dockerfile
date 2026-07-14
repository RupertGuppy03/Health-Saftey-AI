# Placeholder Dockerfile for the FastAPI backend.
#
# This is a stub to be completed during the deployment phase. The plan is to
# containerise the backend so it can be hosted somewhere with enough resources
# for the RAG workload (e.g. Azure or AWS). Nothing here is locked in yet.
#
# A typical shape will look roughly like:
#
# FROM python:3.11-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000
# CMD ["uvicorn", "src.api.<entrypoint>:app", "--host", "0.0.0.0", "--port", "8000"]
