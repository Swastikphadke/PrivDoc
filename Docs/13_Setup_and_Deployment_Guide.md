# 13 --- Setup and Deployment Guide

## 1. Prerequisites

-   Python 3.11 or newer.
-   Node.js LTS and npm.
-   Git.
-   A supported local model runtime if SLM features are enabled.
-   Sufficient disk space for dependencies and model weights.

Exact versions should be pinned after the first successful integration
test.

## 2. Repository initialization

``` bash
mkdir PrivyDoc
cd PrivyDoc
git init
mkdir backend frontend Docs datasets models
```

## 3. Backend setup

Windows PowerShell:

``` powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Linux/macOS:

``` bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install the pinned dependencies from `requirements.txt` once created.
Initial candidate dependencies include FastAPI, Uvicorn, Pydantic,
PyMuPDF, RapidFuzz, pytest and the selected NLP/model libraries.

Start the backend:

``` bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 4. Frontend setup

``` bash
cd frontend
npm install
npm run dev
```

Configure the frontend to call the local API at `http://127.0.0.1:8000`.
Use a development proxy or explicit local CORS configuration. Do not
open CORS to all origins in production.

## 5. Local model runtime

Choose one runtime after benchmarking. If using Ollama: - Install
Ollama. - Pull the selected supported model. - Confirm local inference
works. - Configure the backend to use the local endpoint. - Test with
the network disabled after model download.

Do not assume a model tag or size is available forever; record the exact
model version used.

## 6. Configuration

Use environment variables for: - Maximum upload size. - Temporary
workspace path. - Session retention period. - Model/runtime endpoint on
localhost. - Model identifier. - Inference timeout. - Feature flags for
optional detectors.

Do not store secrets or personal documents in `.env` or source control.

## 7. Run tests

``` bash
pytest
```

Frontend test command should be documented in `package.json`, for
example:

``` bash
npm test
```

## 8. Local deployment security

-   Bind backend to `127.0.0.1`.
-   Keep the model runtime local.
-   Do not expose ports to a public network.
-   Restrict temporary workspace permissions.
-   Use a cleanup mechanism.
-   Avoid production debug mode.
-   Confirm offline processing before making local-only claims.

## 9. Troubleshooting

-   PDF has no extracted text: likely scanned/image-only or malformed;
    report unsupported.
-   Model unavailable: run deterministic/NER degraded mode and disclose
    it.
-   Model output invalid: reject schema-invalid output and continue
    safely.
-   Port in use: configure another local port.
-   Memory pressure: reduce model size, process sequentially and lower
    chunk size.
-   Export verification fails: do not provide the file as safe; inspect
    span mapping and PDF redaction behavior.
