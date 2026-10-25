# ContractWeaver — Multi-Agent Contract Filling

English | [简体中文](README_zh-CN.md)

An early-stage, human-reviewed multi-agent contract workflow, not a general legal chatbot.
Provide negotiation chats or meeting minutes; the agent retrieves templates and
proposes source-grounded values. The user chooses the template, reviews every
candidate, corrects errors and supplies missing facts before DOCX export.

## Workflow

Developer guides (中文): [illustrated Agent + Harness guide](docs/agent-harness-guide.zh-CN.md),
[whole-project reading order](docs/code-reading-guide.zh-CN.md), and
[commenting conventions/checks](docs/code-commenting.md).

Versioned [task prompts](backend/app/agents/prompts.py) explain inputs, processing
rules, slot mapping and structured output for the supervisor and four specialists. See the
[prompt specification](docs/agent-prompts.md); this works independently of provider thinking mode.

Email-only sign-in, explicit next-step guidance, live batch polling and actual
HTTP model-call counters distinguish waiting, failure and human review. Internal
Word locators are not shown as field labels; final preview uses paragraphs and
tables. See the [user guide and limits](docs/user-guide.md).

```text
Negotiation record → supervisor → analysis ↔ template search/observations → user selection
    → typed Word slots → extraction → independent review ↔ supervisor-targeted repair
    → whole-contract coverage agent
    → user corrections / explicit omissions → preview approval → DOCX
```

Each agent has separate instructions and context, sharing one configured API
model. The server controls revisions and permissions; agents cannot approve
values or generate files on their own. Users may bypass recommendations and
browse the complete library. Manual filling works without an LLM key.

The supervisor makes bounded, model-selected action decisions using structured
JSON, not provider-native tool calls. Repairs are revalidated and independently
reviewed before merging; unresolved facts go to the user. See the
[architecture and executable evidence](docs/project-evidence.md).

A constrained **agent harness** enforces shared execution budgets, tool-step
allowlists and a SQLite run journal/lease. The UI exposes actual steps, usage and
brief decision summaries—not a model's complete private chain of thought.
See [harness architecture, reasoning configuration and recovery limits](docs/agent-harness.md).

## Model configuration

Configure **`backend/.env`**, never the frontend:

```dotenv
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
LAW_LLM_API_KEY=your-secret
LAW_LLM_JSON_MODE=json_object
LAW_LLM_THINKING_MODE=disabled
LAW_LLM_REASONING_EFFORT=provider_default
LAW_LLM_MAX_TOKENS=8192
```

The example now presets DeepSeek Flash's public settings, but never a secret.
The model ID and endpoint are documented by [DeepSeek](https://api-docs.deepseek.com/).
To use another provider, replace the base URL and model, without appending
`/chat/completions`, and set thinking mode to `provider_default` unless supported.
Requests use backend-only bearer authentication and Chat Completions. Supported
JSON modes are `json_object`, `json_schema`, and `prompt`; outputs always undergo
schema validation with bounded retries. Environment variables override `.env`.
Restart the backend after configuration changes.

The Flash preset explicitly disables thinking for bounded structured extraction;
it is not a claim that non-thinking output is always correct. All five roles
share these settings. You may enable thinking, but review timeout/output limits.

Copy [the backend example](backend/.env.example) only if `.env` does
not already exist. Remote endpoints require HTTPS; loopback HTTP is supported.
Secrets, databases and generated files are Git-ignored. Production deployments
should inject secrets through their deployment secret manager. Revoke any keys
previously exposed in the project's history.

## Local setup

A fictional [custody-contract meeting-minutes example](examples/meeting-minutes-custody.md)
and [review checklist](examples/README.md) are available. Windows 11 users without
Docker can follow the [startup/shutdown guide](docs/windows-quickstart.md).
`stop-project.bat` stops project processes and removes transient caches;
`stop-and-clean.bat` also removes dependencies/build output, preserving secrets,
templates and user data. Shared system/browser caches are not deleted.

Beginner-friendly [deployment instructions](docs/deployment.md) include Windows
`scripts/setup.bat`, separate `start-backend.bat` / `start-frontend.bat`, and
Linux/macOS `.sh` equivalents. Setup never overwrites existing backend secrets.
Dockerfiles and `compose.yaml` provide an alternative: configure `backend/.env`,
then run `docker compose up -d --build --wait` and open `http://localhost:8080`.
Compose uses a separate persistent volume, not existing local user data. Container
runtime acceptance is still pending; see the deployment and validation records.

Requirements: Python 3.11+, Node.js 20+. From the project root in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env before using automatic analysis/extraction.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. API docs: `http://127.0.0.1:8000/docs`.
`GET /api/v1/health` reports missing configuration names, not credentials; it
does not validate a real provider connection.

Detailed Windows/Linux/macOS setup, troubleshooting and production deployment
guidance are in [Deployment](docs/deployment.md). README keeps the quick start;
longer operational instructions live in `docs/`.

## Original templates, not free-form rewriting

The catalog reads originals from
`backend/resources/contracts/templates/{Ministerial,Regional}`.
Manually inserted placeholders are **not required**. An in-memory compiler
identifies underscore blanks, underlined whitespace, repeated internal spaces,
empty table cells and colon-adjacent candidates. Stable per-location fields
include surrounding text and table context. Existing explicit markers remain
supported. Original DOCX files are never modified.

The LLM proposes field values with quoted source lines; a separate agent reviews
them. Humans must confirm every candidate or explain why it remains blank.
Code then writes only reviewed locations, preserves surrounding run formatting
and checks resulting paragraph text before saving. Omitted generated candidates
restore their original blanks. File and engine fingerprints invalidate stale
field mappings.

This is **not a guarantee of semantic completeness**. Formatting blanks can be
false positives; single spaces, visual choices and arbitrary Word layouts may
need manual maintenance. Images/shapes are preserved rather than blanket-blocked;
they are not OCR-filled and require separate human visual acknowledgement.
Text boxes are scanned, and identical modern/legacy branches are synchronized.
Unsupported embedded content, controls, tracked changes, notes and inconsistent
compatibility branches still block filling. Compare the original against the
review and inspect the final DOCX. The current audit verifies 494 of 567 originals,
with 73 blocked and 92 of the supported templates requiring visual acknowledgement.
See the [current audit](docs/validation.md)
for coverage and acceptance limits; structural checks are not semantic certification.
The obsolete placeholder DOCX/JSON library has been removed at the owner's
request; its contents remain recoverable from Git history. Runtime reads only
originals under `templates/`. Resource cleanup alone does not increase coverage.

See [template safety and acceptance](docs/template-engine.md), the
[Chinese configuration reference](README_zh-CN.md), [API workflow](docs/contract-workflow.md),
and [validation record](docs/validation.md).
Default retrieval fuses separate name/keyword BM25 ranks and exact-name matches
with RRF. Up to 30 candidates undergo structural filtering to recommend at most
five candidates; ordinary non-named results must be fillable, and results are not
guaranteed globally optimal. This is not
full-corpus question-answering RAG. See [retrieval design](docs/template-retrieval.md).
Explicitly requested names are preserved with source evidence and prioritized;
literal positive source requests also have a deterministic fallback. Named but
unsupported originals remain visible with reasons and cannot be auto-filled.
Ambiguous names, versions and changed decisions still require human judgment.
Optional local MiniLM/FAISS retrieval uses `requirements-search.txt` and
`LAW_EMBEDDING_MODEL_PATH`; this is not a fine-tuned conversational LLM.

## Architecture and checks

Backend layers: `api` → `services` / specialist `agents` → `domain` and
`repositories`; `documents` handles deterministic Word structure. Frontend
features separate contract components, state orchestration and HTTP contracts.
SQLite uses owner-scoped records and revision compare-and-swap. Generated
versions are immutable snapshots. No standalone legal consultation or law lookup
is part of this workflow.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m app.cli.audit_templates
cd ../frontend
npm test
npm run build
```

Automated model tests use fakes, not paid API calls. Real provider accuracy,
production deployment and per-template business completeness still require
acceptance testing. Input supports TXT/MD/DOCX, not OCR, PDF or audio. Preview is
textual, not a Word layout renderer. Multi-instance deployments require further
database and background-job infrastructure. Version `0.1.0` identifies this
architecture; no release tag or production certification is implied.
See [requirements and remaining acceptance](docs/requirements-status.md) before
describing the project as fully complete or ready for unrestricted distribution.

## Repository layout

```text
ContractWeaver/
  backend/      API, specialist agents, workflow, persistence and document engine
  frontend/     Vue application, feature components and client-side state
  docs/         Architecture, workflow, validation and repository guidance
  scripts/      Local verification entry point
```

This is one deployable backend and one frontend, not a fleet of microservices.
Each specialist agent has its own task and context, coordinated by a bounded,
human-in-the-loop workflow. Product identity is independent from Git history.
See [repository naming and migration](docs/repository.md) before renaming GitHub.
For local checks, run `./scripts/check.ps1` after installing development dependencies.
