# FastAPI backend image, deployed to Azure Container Apps (Sprint 5).
#
# Contains only what the API needs at runtime: the backend's packages, src/, and
# the vector store. The OpenAI key is never baked in; it is passed as the
# OPENAI_API_KEY environment variable when the container starts.
#
# Build for Azure (x86) even on an Apple Silicon Mac:
#     docker build --platform linux/amd64 -t hs-ai-api .

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Dependencies first, so code changes don't reinstall every package.
COPY requirements.txt requirements-api.txt ./
RUN pip install -r requirements-api.txt -c requirements.txt

# The live vectorstore/ is gitignored, so build from the committed snapshot.
# ADD unpacks a local .tar.gz into the destination folder.
ADD vectorstore-snapshot.tar.gz vectorstore/

COPY src/ src/

# Run as a non-root user. Chroma writes to chroma.sqlite3 even when only reading,
# so that user has to own the vector store.
RUN useradd --create-home appuser && chown -R appuser /app/vectorstore
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT}"]
