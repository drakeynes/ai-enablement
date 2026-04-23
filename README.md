# AI Enablement

Internal AI enablement system for a coaching/consulting agency. Agents across customer success, sales, and operations. Shared knowledge base, portable architecture, documented as it's built.

## Quick Start

1. Complete WSL2 setup if on Windows: see `docs/runbooks/setup_wsl.md`
2. Clone this repo inside WSL (not on the Windows filesystem)
3. Copy `.env.example` to `.env.local` and fill in values (ask Drake for keys)
4. `python -m venv .venv && source .venv/bin/activate`
5. `pip install -e ".[dev]"`
6. `cd frontend && npm install` (for frontend work)

## Read Before Contributing

- `CLAUDE.md` — project context, conventions, and rules
- `docs/architecture.md` — how the system fits together
- `docs/collaboration.md` — how work is divided
- `docs/decisions/` — why things are the way they are

## Project Status

See the **Current Focus** section of [`CLAUDE.md`](CLAUDE.md) for canonical status. Near-term milestone: Ella V1 in pilot-client beta the week of April 27.

## Key Principles

1. Our database is the source of truth
2. Agents query the database, not external tools
3. External tools are replaceable adapters
4. Interfaces are thin clients on a shared brain

Full detail in `CLAUDE.md`.

## Structure

```
ai-enablement/
├── CLAUDE.md            # Primary project context
├── docs/                # Architecture, schema, agents, decisions, runbooks
├── supabase/            # Database migrations and seed data
├── ingestion/           # Data pipelines from external tools
├── agents/              # Agent implementations
├── orchestration/       # n8n workflow exports
├── frontend/            # Next.js dashboards
├── shared/              # Shared Python utilities
├── evals/               # Golden datasets and eval runner
└── scripts/             # One-off scripts
```

## Contact

Drake — primary developer and architect
Zain — technical operations and n8n workflows
