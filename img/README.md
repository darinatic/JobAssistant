# Diagrams

Mermaid source (`.mmd`) for the diagrams used in the root `README.md`. GitHub
renders the same diagrams inline (from fenced ```mermaid blocks in the README),
so these files are the editable source of truth and are also handy for exporting
to PNG/SVG for slides or docs.

| File | Diagram |
|------|---------|
| `architecture.mmd`       | System architecture (SPA ↔ stateless FastAPI ↔ Claude / Tectonic / matcher / scrapers) |
| `tailoring-pipeline.mmd` | Resume-tailoring LangGraph state machine (`parse_jd → match → tailor → cover_letter`) |
| `job-search.mmd`         | Concurrent multi-platform search, lazy descriptions, background enrichment |
| `intel-panel.mmd`        | Job-intel panel — legitimacy red-flags + tiered contacts lookup |
| `request-lifecycle.mmd`  | Stateless request lifecycle (the browser holds the CV; the server stores nothing) |
| `deployment.mmd`         | Single Docker image on Render, auto-deployed by GitHub Actions |

## Render to an image

Use the Mermaid CLI (no install needed via `npx`):

```bash
# one file → PNG (and SVG)
npx -y @mermaid-js/mermaid-cli -i architecture.mmd -o architecture.png
npx -y @mermaid-js/mermaid-cli -i architecture.mmd -o architecture.svg

# all of them → PNG
for f in *.mmd; do npx -y @mermaid-js/mermaid-cli -i "$f" -o "${f%.mmd}.png"; done
```

Or paste the contents into the live editor at <https://mermaid.live>.
