# ContractWeaver

English | [简体中文](README_zh-CN.md)

ContractWeaver is a multi-agent web application for contract completion. It turns negotiation chats or meeting minutes into source-backed field proposals, retrieves suitable contract templates, runs an independent review, and exports an edited DOCX after user approval.

## Workflow

1. Import TXT, Markdown, or DOCX records, or paste the text directly.
2. The record-analysis agent identifies the contract type, agreed terms, disputes, and missing facts.
3. Retrieval returns up to five candidates while keeping the full template library available for manual selection.
4. The field-extraction agent maps source facts to fillable positions and cites supporting lines.
5. The review agent checks evidence, types, and conflicts. The supervisor may request one targeted repair round.
6. The user confirms, edits, or leaves fields blank, reviews the preview, and exports DOCX.

The original DOCX remains the layout source. The model receives the source record, field locations, and nearby context, then returns structured proposals. The document engine writes approved values back into Word.

## Stack

- Frontend: Vue 3, Vite, Vue Router, Vitest
- Backend: FastAPI, Pydantic, SQLite
- Model access: OpenAI-compatible API, with a DeepSeek Flash preset
- Retrieval: title BM25, business-keyword BM25, exact-name matching, RRF fusion, and an optional local FAISS channel
- Documents: DOCX structure scanning, stable field locations, controlled writes, and post-write integrity checks
- Agent runtime: bounded supervisor, four specialist roles, shared budgets, run journals, and concurrency leases

## Quick start on Windows 11

Install Python 3.11+ and Node.js 20+, then run:

```bat
scripts\setup.bat
```

Create the backend configuration:

```bat
copy backend\.env.example backend\.env
```

Edit `backend/.env`:

```ini
LAW_LLM_API_KEY=your-key
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
```

Start the backend and frontend in separate terminals:

```bat
scripts\start-backend.bat
scripts\start-frontend.bat
```

Open `http://127.0.0.1:5173`. API documentation is available at `http://127.0.0.1:8000/docs`.

Stop project services:

```bat
scripts\stop-project.bat
```

Stop services and remove installed dependencies and build caches:

```bat
scripts\stop-and-clean.bat
```

The cleanup script preserves source files, `backend/.env`, templates, the database, and generated contracts.

## Docker

Copy `backend/.env.example` to `backend/.env`, add the API key, and run:

```bash
docker compose up --build -d
```

The default endpoint is `http://127.0.0.1:8080`.

## Secret handling

- Store API keys only in `backend/.env`.
- Git ignores environment files.
- Variables prefixed with `VITE_` become part of the browser bundle and must contain public settings only.
- Runtime logs keep steps, status, counters, and short summaries. Keys, full prompts, and full model responses are excluded.

## Repository layout

```text
ContractWeaver/
├─ backend/       FastAPI, agents, retrieval, DOCX engine, and tests
├─ frontend/      Vue application and frontend tests
├─ docs/          Chinese and English guides
├─ examples/      Fictional meeting minutes
├─ scripts/       Setup, start, check, and stop scripts
└─ compose.yaml   Container orchestration
```

Historical engineering records and screenshots live in the ignored `local-notes/` directory.

## Documentation and examples

Recommended order: this README → [English guide](docs/guide.en.md) (or [中文完整指南](docs/guide.zh-CN.md))

The full guide covers operation, architecture, configuration, deployment, troubleshooting, and tests. The source-reading guide focuses on backend agent coordination and runtime implementation.

- [Custody-contract meeting minutes](examples/meeting-minutes-custody.md)

## Operational scope

Model results are review candidates. Before signing, verify parties, amounts, dates, liability terms, dispute resolution, appendices, and signatures. The text preview cannot replace a final Word layout review. Formal use also requires appropriate business, finance, and legal review.

The current release targets local development and demonstration. Production deployment requires HTTPS, access control, backups, monitoring, rate limits, and evaluation with representative data.
