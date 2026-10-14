# Deployment

Sprint 5. How the assistant is deployed, so the team or the client can repeat it,
update it or take it over.

```
Browser ──► Streamlit interface ──HTTPS──► FastAPI backend ──► OpenAI
            (Streamlit Community Cloud)    (Azure Container Apps,
                                            image from Docker Hub)
```

The interface only knows the backend's URL (`HS_API_BASE_URL`). The OpenAI key
lives only in the backend.

---

## Backend

| | |
|---|---|
| **Public URL** | https://hs-ai-api.orangetree-99264325.australiaeast.azurecontainerapps.io |
| **Health check** | `<url>/health` — should report `hs_construction_v1`, 3,646 chunks |
| **API docs** | `<url>/docs` |
| **Image** | `rupertguppy03/hs-ai-api` on Docker Hub (public), current tag `v2` |
| **Azure subscription** | Azure for Students |
| **Container App** | `hs-ai-api`, resource group `hs-ai-rg`, region Australia East |
| **Environment** | `managedEnvironment-plpredictorrg-9d77` (shared, see below) |
| **Size and scale** | 0.5 vCPU / 1 GiB, min replicas 1, max replicas 1 |
| **Secret** | `openai-api-key`, exposed to the container as `OPENAI_API_KEY` |
| **Cost** | ~$10/month from the student credit; budget alert set |

### Why it is set up this way

- **Min replicas 1** keeps one copy always running, so nobody waits for a cold
  start. **Max replicas 1** stops Azure adding copies and multiplying the cost.
  One copy is enough: most of an answer is spent waiting on OpenAI, not on the
  container's CPU. Raise max to 2 if many people use it at once — history is
  sent with every request, so any copy can answer any question.
- **Docker Hub** instead of Azure Container Registry, which would cost ~$5/month.
  The image holds no secrets, so a public repository is fine.
- **Shared environment.** Azure for Students allows one Container Apps
  environment per subscription, so the app runs in the environment left from an
  earlier project. An environment costs nothing on its own. It is in Australia
  East and its region cannot be changed; moving to New Zealand North would mean
  deleting it (and every app in it) and recreating the app. Australia East adds
  roughly 30 ms per request, which is negligible next to an answer.
- **Citation judge.** Every answered question also runs the DeepEval DAG citation
  check (`DAG_JUDGE_MODEL`, default `gpt-4.1`), so each answer costs one extra
  OpenAI call and takes a few seconds longer. `v1` was built before this feature
  and returns no score.
- **Azure for Students:** when the credit runs out the
  resources are switched off — no card is charged.

### Building the image

From the repo root (needs Docker Desktop running):

```bash
docker build --platform linux/amd64 -t hs-ai-api .
```

`--platform linux/amd64` matters on an Apple Silicon Mac: Azure runs x86, and an
ARM image fails there with `exec format error`. The "may have poor performance
under emulation" warning when running it locally is expected.

The image contains only what the backend needs — see `.dockerignore` (an
allowlist) and `requirements-api.txt`. The vector store comes from the committed
`vectorstore-snapshot.tar.gz`, so the image builds the same from a fresh clone.

Test it locally before pushing:

```bash
docker run --rm -p 8001:8000 --env-file .env hs-ai-api
HS_API_BASE_URL=http://localhost:8001 streamlit run streamlit_app.py
```

### Releasing a new version

1. Rebuild the image (above).
2. Tag and push with a **new** version number — never overwrite an old tag:
   ```bash
   docker tag hs-ai-api rupertguppy03/hs-ai-api:v2
   docker push rupertguppy03/hs-ai-api:v2
   ```
3. Azure Portal → `hs-ai-api` → **Application → Containers → Edit and deploy** →
   select the container → **Edit** → change the tag to `v2` → **Save** → **Create**.
4. Check **Monitoring → Log stream** (pick the new revision) for
   `Ready in …s — … 3646 chunks` with no "Model clients could not be created"
   warning, then check `/health`.

To roll back, do step 3 with the previous tag.

### Changing the OpenAI key

**Settings → Secrets** → edit `openai-api-key` → save. Then restart the active
revision (**Application → Revisions and replicas** → **Restart**) so the container
picks up the new value.

### Recreating the backend from scratch

1. Push the image to Docker Hub (above).
2. **Create a resource → Container App.**
   - Basics: resource group, name, the region of the subscription's existing
     Container Apps environment, and that environment (or create one if none exists).
   - Container: untick quickstart; Docker Hub or other registries; Public;
     `docker.io`; `rupertguppy03/hs-ai-api:<tag>`; 0.5 CPU, 1 Gi.
   - Ingress: enabled, from anywhere, HTTP, target port `8000`.
3. Add the secret and environment variable, and set min/max replicas to 1, as in
   *Changing the OpenAI key* and *Releasing a new version* (Edit and deploy →
   Environment variables → `OPENAI_API_KEY` from secret `openai-api-key`; Scale tab).
4. Check the log stream and `/health`.

---

## Frontend

Streamlit Community Cloud — see Sprint 5, story 3.
