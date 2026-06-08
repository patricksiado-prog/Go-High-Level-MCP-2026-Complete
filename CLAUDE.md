# Go-High-Level-MCP-2026-Complete

Model Context Protocol (MCP) server for GoHighLevel. It exposes GHL API
operations as MCP tools over stdio, Streamable HTTP, and legacy SSE.

## What this repo is

- An MCP server that wraps the GoHighLevel API.
- ~`834` registered tools: `802` raw endpoint tools plus `32` curated
  agent-workflow tools.
- Companion CLI/tooling for setup, inspection, coverage reporting, and MCP
  client config generation.
- `mcp-apps/` — companion MCP Apps server for hosts that support interactive
  MCP resources. It runs separately so the core API server stays lean.

See `README.md` for the full feature/tooling walkthrough.

## Project layout

```text
src/
  clients/       GHL API clients
  tools/         MCP tool modules
  types/         shared TypeScript types
  main.ts        Streamable HTTP MCP server
  server.ts      stdio MCP server
  http-server.ts legacy SSE MCP server
scripts/         API scanner, generator, build, smoke test
docs/            generated API coverage reports
examples/        MCP recipes and starter agent templates
mcp-apps/        companion MCP Apps server and bundled UI
tests/           Jest tests
```

## Build, run, test

```bash
npm install
npm run build              # Compile to dist/
npm run start:stdio        # stdio MCP server
npm run start:http         # Streamable HTTP server at /mcp
npm run start:legacy       # legacy SSE server at /sse
npm run lint               # Fast TypeScript syntax/transpile check
npm test                   # Jest tests
```

## Tool profiles

Set `GHL_TOOL_PROFILE` to control the exposed surface:

- `full` — default; all `834` tools.
- `curated` — only the `32` agent workspace tools (e.g. `crm_prepare_lead_intake`,
  `crm_prepare_conversation_reply`, `crm_location_health_check`).
- `raw` — only the `802` endpoint-level tools.

Curated tools return structured, confirmation-gated action plans for writes
instead of firing one ambiguous API call.

## Generated files

- `src/tools/official-spec-tools.ts` and `src/tools/official-spec-endpoints.json`
  are generated. Do not edit them by hand.
- Run `npm run scan:ghl-api` after the official GHL API docs change.
- `npm run ci:ghl-api-drift` fails if generated artifacts are stale.
- `.github/workflows/ghl-api-drift.yml` runs daily and opens a PR when the
  official API docs change.

## Conventions

- Use read tools before write tools.
- Treat deletes, outbound messages, workflow enrollment, appointment creation,
  and snapshot pushes as confirmation-gated actions.
- Summarize tool results plainly and include the IDs of any records changed.

## Config & secrets

Configure via environment variables (see `.env.example`):

```bash
GHL_API_KEY=your_private_integration_api_key
GHL_LOCATION_ID=your_location_id
GHL_BASE_URL=https://services.leadconnectorhq.com
GHL_API_VERSION=2021-07-28
```

Keep credentials in the environment only — never commit tokens, and do not
expose an unauthenticated public server URL.
