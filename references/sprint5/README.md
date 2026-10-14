# Sprint 5 — Deployment

Planning docs and user stories for this sprint. Goal: deploy the assistant —
the FastAPI backend containerised and running on Azure, the Streamlit interface
on Streamlit Community Cloud. See
[`../Project_User_Stories.md`](../Project_User_Stories.md).

**Deployment decision:** backend image on Docker Hub, run on Azure Container
Apps (Consumption plan, min replicas = 1, 0.5 vCPU / 1 GiB) so it never goes
cold; frontend on Streamlit Community Cloud (free, sleeps after ~12 hours idle).
Azure Container Registry, scale-to-zero and Vercel were ruled out on cost,
cold-start delay and the need to rewrite the UI respectively. The only spend is
the existing Azure credit (~$10/month).

---

## 1. Containerise the Backend

**MoSCoW:** Must | **Est:** 2–3 hours

As a developer, I want the FastAPI backend packaged as a Docker image that runs the same anywhere so that it can be deployed to Azure without depending on anyone's local setup.

**Tasks**
- Replace the placeholder `Dockerfile` with a working one, using the Python version in `.python-version`
- Start the app with uvicorn on `src.api.app:app`, without `--reload`, listening on `0.0.0.0` and a port that can be set at runtime
- Include `vectorstore/` in the image so the backend has its collection without re-embedding
- Add a `.dockerignore` that keeps `.env`, notebooks, tests, caches, the vectorstore snapshot tarball and anything else the backend doesn't need out of the image
- Pass the OpenAI key in as an environment variable at run time — never copy it into the image
- Build and run the image locally and check it against the existing local setup

**Acceptance Tests**
- Given the image is built, when it is run locally with the OpenAI key passed in, then `GET /health` reports the collection with its full chunk count.
- Given the container is running, when the Streamlit app is pointed at it with `HS_API_BASE_URL`, then a question gets an answer with sources, as it does against `./scripts/run_api.sh`.
- Given the built image, when its contents are inspected, then no `.env` file or API key is inside it.

**Definition of Done**
- `Dockerfile` and `.dockerignore` committed
- Image size and local cold start recorded in `docs/startup_and_query_timings.md`

---

## 2. Deploy the Backend to Azure Container Apps

**MoSCoW:** Must | **Est:** 2–3 hours

As a client, I want the backend running on Azure behind a public HTTPS address so that the assistant works without anyone's laptop being switched on.

**Tasks**
- Confirm when the Azure credit expires and set a budget alert before creating anything
- Tag and push the image from story 1 to Docker Hub, with a version tag rather than relying on `latest` alone
- Create a resource group, a Container Apps environment and a Container App that pulls the image from Docker Hub
- Set min replicas to 1 and size it at 0.5 vCPU / 1 GiB, raising it only if the container runs out of memory
- Store the OpenAI key as a Container Apps secret and expose it to the app as an environment variable
- Enable external ingress on the app's port and note the HTTPS URL
- Check the container logs for a clean startup

**Acceptance Tests**
- Given the app is deployed, when `GET /health` is called on the public URL, then it returns the collection and full chunk count.
- Given the app has been idle, when a question is posted to `/chat`, then it answers without a cold-start delay.
- Given a new image version is pushed, when the Container App is updated to it, then the new version is serving without the app being recreated.

**Definition of Done**
- No Azure resources running that weren't in the deployment decision (no Container Registry, no extra replicas)
- The steps used, the public URL and the resource names written up in the repo so the client could repeat or take over the deployment
- Deployed query latency recorded in `docs/startup_and_query_timings.md` next to the local figures

---

## 3. Deploy the Frontend to Streamlit Community Cloud

**MoSCoW:** Must | **Est:** 1–2 hours

As a user, I want to open the assistant from a link in my browser so that I can ask questions without installing anything.

**Tasks**
- Connect the GitHub repo to Streamlit Community Cloud and deploy `streamlit_app.py`
- Set `HS_API_BASE_URL` to the Azure URL from story 2 in the app's Secrets
- Make sure the install Streamlit Cloud does works on its Linux image and Python version — trim what the frontend installs if the full `requirements.txt` fails or is needlessly slow, without changing the backend's dependencies
- Check that `.streamlit/config.toml` settings carry over
- Run the deployed app end to end: a normal question, a follow-up, an out-of-scope question and voice input

**Acceptance Tests**
- Given the deployed frontend, when a question is asked, then the answer and sources come back from the Azure backend.
- Given the backend is unreachable, when a question is asked, then the interface shows its existing error message rather than crashing.
- Given the app has gone to sleep, when someone opens the link and wakes it, then it works again without redeploying.

**Definition of Done**
- The public app link shared with the team and the client
- How to wake the app, and how the client could self-host the frontend against the Azure backend, written up alongside the story 2 deployment notes
- No API keys in the frontend's secrets — the frontend only needs the backend URL
