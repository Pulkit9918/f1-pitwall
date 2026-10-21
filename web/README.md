# f1-pitwall web

A static Next.js site over the gold tables. It reads JSON files that `scripts/export_static.py` writes into
`web/public/data/`, so it needs no server.

    python scripts/export_static.py     # from the repository root: writes web/public/data
    cd web
    npm install
    npm run dev                         # http://localhost:3000
    npm test                            # unit tests for the race maths
    npm run build                       # writes the static site to web/out

Pages: `/` (latest race), `/sessions`, `/circuits`, `/race/?key=2026-R17-R` (one session).
