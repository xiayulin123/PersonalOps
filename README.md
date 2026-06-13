# PersonalOps

PersonalOps is a **local-first AI workspace** for study and software projects. Upload your files, chat with an agent that can search those files, optionally search the web, and remember workspace preferences — all backed by a FastAPI backend and a Tauri + React desktop app.

## What it does

- **Study workspaces** — lecture notes, PDFs, assignments, exam prep
- **Code workspaces** — READMEs, docs, error logs, project structure questions
- **RAG chat** — answers grounded in uploaded files with filename + page citations
- **Agent routing** — chooses direct answer, file search, web search, or hybrid
- **Workspace memory** — persistent key/value preferences (language, course, tech stack)
- **Task templates** — one-click prompts for study guides, exam plans, PR summaries, etc.

## Project structure

```
personalops/
├── apps/
│   ├── api/                    # FastAPI backend (Python)
│   │   ├── main.py             # App entry, router registration
│   │   ├── config.py           # Env: OPENAI_API_KEY, DATA_DIR, Chroma, Tavily
│   │   ├── models.py           # SQLite ORM: Workspace, File, Memory, Message
│   │   ├── routers/            # HTTP endpoints
│   │   │   ├── workspaces.py   # CRUD workspaces
│   │   │   ├── files.py        # Upload, list, delete + background indexing
│   │   │   ├── chat.py         # Agent chat (supports template_id)
│   │   │   ├── memory.py       # Workspace memory CRUD
│   │   │   ├── tools.py        # Per-workspace tool toggles
│   │   │   └── templates.py    # Task template list by workspace type
│   │   └── services/
│   │       ├── parser.py       # PDF, DOCX, Markdown, TXT
│   │       ├── chunker.py      # Token-based chunking (tiktoken)
│   │       ├── indexer.py      # OpenAI embeddings → Chroma
│   │       ├── rag.py          # retrieve_chunks() for agent + legacy RAG
│   │       ├── web_search.py   # Tavily primary, DuckDuckGo fallback
│   │       ├── templates.py    # Study + Code task template definitions
│   │       └── agent/          # LangGraph agent
│   │           ├── graph.py    # classify → memory → retrieve/web → generate → verify
│   │           ├── prompts.py  # Router, generator, verifier prompts
│   │           ├── runner.py   # run_agent(workspace_id, question)
│   │           └── state.py    # AgentState, Route types
│   └── desktop/                # Tauri + React + TypeScript UI
│       └── src/
│           ├── App.tsx         # Tabs: Files | Chat | Memory | Tools
│           ├── lib/api.ts      # REST client → localhost:8000
│           └── components/
│               ├── FilesTab.tsx
│               ├── ChatTab.tsx
│               ├── MemoryTab.tsx
│               ├── ToolsTab.tsx
│               ├── TaskTemplatePicker.tsx
│               └── ChatAgentMeta.tsx   # Trace + file/web citations
├── data/                       # Local data (gitignored)
│   ├── personalops.db          # SQLite
│   ├── chroma/                 # Vector store per workspace
│   └── uploads/{workspace_id}/ # Uploaded files on disk
└── docs/                       # Phase guides (outside this repo root in monorepo)
```

## Tech stack

| Layer | Technology |
|-------|------------|
| Desktop shell | Tauri 2 |
| Frontend | React, TypeScript, Vite, Tailwind |
| API | FastAPI, SQLAlchemy (async), SQLite |
| Vector DB | Chroma (local persist) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat / agent | OpenAI `gpt-4o-mini`, LangGraph |
| Web search | Tavily (primary), DuckDuckGo (fallback) |
| File parsing | PyMuPDF (PDF), python-docx, plain text for `.md`/`.txt`/code |

## Quick start

### 1. Backend

```bash
conda activate py311
cd personalops/apps/api
pip install -r requirements.txt

# One-time setup: copy env template and add your keys
cp .env.example .env
# Edit .env — OPENAI_API_KEY, Azure OCR keys, etc. (.env is gitignored)

uvicorn main:app --reload --port 8000
```

Settings load automatically from `apps/api/.env` on startup (no manual `export` each session).

### 2. Desktop

```bash
cd personalops/apps/desktop
npm install
npm run tauri dev
```

The UI expects the API at `http://localhost:8000`. The header shows **Backend online** when `/health` returns OK.

## Desktop tabs

| Tab | Purpose |
|-----|---------|
| **Files** | Upload PDF, DOCX, Markdown, TXT, code files; background indexing to Chroma |
| **Chat** | Agent chat with trace, file citations, web citations, task templates |
| **Memory** | Key/value preferences injected into the agent prompt |
| **Tools** | Toggle `file_search`, `web_search`, `memory` per workspace |

## Agent routes

The LangGraph agent classifies each message into one route:

| Route | When used | Tools involved |
|-------|-----------|----------------|
| `direct` | Simple questions, math, greetings | Memory only |
| `file_rag` | Course content, README, uploaded docs | Memory + Chroma retrieval |
| `web_search` | Current events, maintenance status, latest docs | Memory + Tavily/DDG |
| `hybrid` | Compare local files with online info | Memory + files + web |

Tool toggles in the **Tools** tab enforce permissions. For example, if `web_search` is off, the router cannot use `web_search` or `hybrid`.

## Default tool settings

```json
{
  "file_search": true,
  "web_search": false,
  "memory": true
}
```

## Task templates

**Study** (4): Summarize lecture, Generate study guide, Generate practice quiz, 7-day exam review plan

**Code** (3): Explain codebase structure, Debug error log, Generate PR summary

Send chat with optional `template_id`; the server prepends the template prompt and appends user notes.

## Key API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET/POST/DELETE | `/workspaces` | List, create, delete workspaces |
| GET/POST/DELETE | `/workspaces/{id}/files` | File upload and management |
| POST | `/workspaces/{id}/chat` | Agent chat (`message`, optional `template_id`) |
| GET/POST/PATCH/DELETE | `/workspaces/{id}/memory` | Workspace memory |
| GET/PATCH | `/workspaces/{id}/tools` | Tool settings |
| GET | `/workspaces/{id}/templates` | Task templates for workspace type |

## File indexing pipeline

1. User uploads a file → saved under `data/uploads/{workspace_id}/`
2. Background task: `parse_file` → `chunk_text` → `index_file` (embed + Chroma)
3. Status: `pending` → `indexing` → `ready` (or `failed`, `empty`, `needs_ocr`)
4. Scanned PDFs with no extractable text → `needs_ocr`; use **Run OCR** in the Files tab
5. `chunk_count` shows how many vector chunks were stored; empty or unreadable files end at `ready` with `chunk_count = 0`

Supported formats: **PDF**, **DOCX**, **Markdown**, **TXT**, and other text/code extensions handled by `parse_text()`.

## Data model (SQLite)

- **Workspace** — `name`, `type` (`study` | `code`), `tool_settings_json`
- **File** — `filename`, `path`, `status`, `chunk_count`
- **Memory** — `key`, `value` per workspace
- **Conversation / Message** — chat history with `sources_json` metadata (trace, route, citations)

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Embeddings + chat completions |
| `DATA_DIR` | Recommended | Root for DB, uploads, Chroma |
| `DATABASE_URL` | Recommended | SQLAlchemy async SQLite URL |
| `CHROMA_PERSIST_DIR` | Recommended | Chroma persistence path |
| `TAVILY_API_KEY` | For web search | Tavily API key |
| `WEB_SEARCH_PROVIDER` | Optional | `tavily` (default) |
| `OCR_PROVIDER` | Optional | `tesseract` (default, local) or `azure` |
| `AZURE_VISION_ENDPOINT` | For Azure OCR | e.g. `https://<name>.cognitiveservices.azure.com` |
| `AZURE_VISION_KEY` | For Azure OCR | Computer Vision API key |
| `OCR_MAX_PAGES` | Optional | Max pages per OCR run (default `150`) |
| `OCR_LANG` | Optional | Tesseract language (default `eng`) |
| `TESSERACT_CMD` | Optional | Path to `tesseract` binary if not on PATH |

### OCR providers

**Tesseract (default)** — free, local, no upload. Install: `brew install tesseract` and `pip install pytesseract Pillow`.

**Azure Computer Vision Read** — cloud OCR; F0 free tier is **5,000 transactions/month**. Each submission must be **≤ 4 MB**; on F0, multi-page PDF batches are capped at **2 pages/request** (`AZURE_OCR_BATCH_MAX_PAGES`). Large scanned PDFs are sliced from the source file (not re-rendered) to pack pages efficiently. Set:

Add to `apps/api/.env` (see `.env.example`):

```bash
OCR_PROVIDER=azure
AZURE_VISION_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
AZURE_VISION_KEY=your-key
OCR_MAX_PAGES=150
```

Create a **Computer Vision** resource in [Azure Portal](https://portal.azure.com), copy endpoint + key from **Keys and Endpoint**. `/health` returns `ocr_provider` and `ocr_available`.

## Development phases

- **Phase 0** — FastAPI skeleton, SQLite, workspaces
- **Phase 1** — File upload, indexing, RAG chat with citations
- **Phase 2** — LangGraph agent, memory, tools, web search, templates, trace UI

## Testing

```bash
cd personalops/apps/api
python test_agent_26.py
```

Agent integration tests cover direct, file_rag, and web_search routing scenarios.

## License

Personal project / portfolio use. Add a license file if you open-source the repo.
