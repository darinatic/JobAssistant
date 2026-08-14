# Architecture

The technical companion to the [README](README.md). The README is the overview — *what* Overlap does; this document is the *how*: per-feature internals, the diagrams, and the design decisions behind them. Every diagram is Mermaid, so it renders inline on GitHub.

**Contents**

- [System overview](#system-overview)
- [Stateless request lifecycle](#stateless-request-lifecycle)
- [Resume tailoring pipeline](#resume-tailoring-pipeline)
- [PII guardrail](#pii-guardrail)
- [Honesty enforcement](#honesty-enforcement)
- [Live job search](#live-job-search)
- [Fit predictor](#fit-predictor)
- [Job-intel panel](#job-intel-panel)
- [Local matching engine](#local-matching-engine)

---

## System overview

A React SPA holds all state (CV + results) in `localStorage` and re-sends the CV in the body of every request. The FastAPI backend is a set of **pure functions of the request body** — no auth, no session, and no *user* data stored (the one exception is anonymous job-skill telemetry, below). It fans out to Claude for the language-heavy steps, a local deterministic matcher for scoring (no LLM), Tectonic for PDF, and four job scrapers.

```mermaid
flowchart TB
    subgraph Client["Browser — React 19 SPA (Vite)"]
        CV["CV + results in localStorage"]
    end

    subgraph Backend["FastAPI — stateless pure functions"]
        RL["Per-IP rate limiter (in-memory)"]
        G["Guardrails — deterministic PII redaction"]
        SVC["services · LangGraph · search · intel · insights"]
        MATCH["Local gazetteer matcher (no LLM, ~1ms)"]
    end

    Client -- "JSON over HTTP (CV re-sent each request)" --> RL
    RL --> SVC
    SVC <--> MATCH
    SVC -- "CV redacted first (name/email/phone/url stripped)" --> G
    G -- "anonymized text only" --> ANTH["Anthropic Claude<br/>Haiku 4.5 · Sonnet 4.5"]
    SVC -- "markdown → LaTeX → PDF" --> TEC["Tectonic (external binary)"]
    SVC -- "scrape live jobs" --> SCR["MyCareersFuture JSON · LinkedIn guest HTML · JobStreet (Patchright) · Careers@Gov"]
    SCR -. "optional cloud browser (prod)" .-> BB["Browserbase"]
    SVC -- "response (ephemeral)" --> Client
```

**Design intent.** The whole app is a demo anyone can try instantly, so the constraints are: no state to leak, cheap models where quality doesn't matter (Haiku for parsing), quality models where it does (Sonnet for writing), and *deterministic* code — not an LLM — for anything that must be exact and repeatable (skill matching, honesty checks, red flags, PII detection).

---

## Stateless request lifecycle

The CV is uploaded once (PDF → markdown), returned to the client, and kept in `localStorage`. It is then re-sent in the body of every subsequent request. No user data is persisted server-side (the only write to a database is anonymous job-skill telemetry — see [Local matching engine](#local-matching-engine)).

```mermaid
sequenceDiagram
    actor U as User
    participant B as Browser (localStorage)
    participant A as FastAPI (stateless)

    U->>B: upload resume (PDF)
    B->>A: POST /resume/parse (multipart)
    A-->>B: markdown CV (returned, NOT stored)
    B->>B: keep CV in localStorage
    Note over B,A: every later request re-sends the CV in its body

    B->>A: POST /search {query, resume_markdown}
    A-->>B: jobs[] + interpreted filters (ephemeral)
    B->>A: POST /tailor {jd_text, resume_markdown, style}
    A-->>B: tailored markdown + honesty[] + guardrails
    B->>A: POST /tailored/resume.pdf {resume_markdown}
    A-->>B: ATS-safe PDF (never persisted)
```

---

## Resume tailoring pipeline

Tailoring is a **LangGraph state machine** with the master CV threaded through the state and conditional edges routing between steps.

```mermaid
stateDiagram-v2
    [*] --> parse_jd
    parse_jd --> match_skills: parsed OK
    parse_jd --> [*]: parse failed
    match_skills --> tailor_resume: include_resume
    match_skills --> generate_cover_letter: cover-only + score >= 60
    match_skills --> [*]: failed
    tailor_resume --> generate_cover_letter: should generate CL
    tailor_resume --> prepare_review
    generate_cover_letter --> prepare_review
    prepare_review --> [*]

    note right of match_skills
      local deterministic matcher (no LLM)
      → missing_required = hard "never claim" list
    end note
    note right of tailor_resume
      PII guardrail wraps the Sonnet call:
      anonymize → tailor → restore + verify
    end note
```

- **`parse_jd`** (Claude **Haiku 4.5**) extracts the posting's required/preferred skills.
- **`match_skills`** runs the **local deterministic matcher** (no LLM) to split the JD's skills into what the CV supports vs. what it doesn't. The "doesn't" set becomes a hard **`missing_required`** list handed to the tailor.
- **`tailor_resume`** (Claude **Sonnet 4.5**) rewrites the resume — mirrors the JD's exact keyword wording *where the CV supports it*, preserves metrics, reorders by relevance, targets one page. The PII guardrail wraps this call (see below).
- **`generate_cover_letter`** (Sonnet, optional) is a separate on-demand step.

Two **styles** trade editorial latitude while keeping honesty rules identical: `faithful` (keep all, reorder/rephrase) and `aggressive` (restructure + cut, hard one page). A one-page budget estimator (calibrated so ~55 rendered lines ≈ one page) drives a live page-fit badge as you edit.

---

## PII guardrail

The CV is sent to Anthropic (a third party) to be tailored. Before it leaves, a **deterministic, dependency-free** guardrail strips the candidate's direct identifiers and the model tailors an *anonymized* copy; the real details are restored locally afterward. This is data minimization before a third-party LLM call — the "safe AI" story, enforced in code.

```mermaid
sequenceDiagram
    autonumber
    participant API as FastAPI /tailor
    participant M as Local matcher
    participant G as Guardrail (deterministic, ~1ms)
    participant LLM as Claude Sonnet 4.5

    API->>M: match_local(JD, REAL cv)
    Note over M: local, no LLM — needs the real CV
    M-->>API: skill match + missing_required

    API->>G: anonymize(cv)
    Note over G: name = the H1 line (doc-wide),<br/>email doc-wide, phone/URL header-only
    G-->>API: anonymized cv + entity_mapping<br/>(Jason… → [NAME_0], … → [EMAIL_0])

    API->>LLM: tailor(anonymized cv, JD)
    Note over LLM: the model NEVER sees real identifiers
    LLM-->>API: tailored markdown (echoes [NAME_0] …)

    API->>G: restore_and_verify(tailored, mapping, real cv)
    Note over G: token replacement (positions changed<br/>by the rewrite, tokens survive at temp 0).<br/>Header force-restored if any token dropped.
    G-->>API: real identifiers restored + GuardrailReport

    API->>G: lint_resume(real cv, tailored)
    G-->>API: honesty advisories

    API-->>API: respond {tailored, guardrails, honesty}
```

**Why deterministic, not NER.** The first build used Microsoft Presidio (spaCy NER). Running NER over the whole document mis-classified substance the tailor needs — it tagged *"AI"* as a location and *"PyTorch"* / a company name as a person — which forced an entity-exclusion list plus a skills-allowlist patch, and dragged in ~200 MB of model. Because a resume's identifiers live in the contact header (and the name is the `# ` H1 in this app's format), a **header-anchored deterministic** detector is lighter, exact-repeatable, on-brand with the rest of the app, and has *zero* body false positives.

**Restore is token replacement, not positional.** Presidio's de-anonymizer restores by character offset, but the tailor rewrites and reorders the text, invalidating offsets. The placeholder tokens themselves survive the rewrite verbatim (temperature 0), so we invert the mapping and replace tokens.

**Guarantees.** The contact header is force-restored from the original CV if any token fails to round-trip (so the PDF always carries the right details); and the whole layer **fails open** — any error tailors on the real CV rather than breaking the request. The same guardrail wraps the cover-letter call.

---

## Honesty enforcement

Honesty is **code-enforced, not just prompted**. The deterministic matcher decides what the tailor may claim *before* generation, and a deterministic linter checks the output *after*.

```mermaid
flowchart TB
    JD["parsed JD skills"] --> SPLIT["gap_analysis + match_local<br/>(deterministic)"]
    CV["master CV"] --> SPLIT
    SPLIT --> MR["missing_required =<br/>JD skills NOT in the CV"]
    SPLIT --> SG["surfaceable (CV-backed)<br/>vs genuine gaps"]
    MR --> PROMPT["tailor prompt rule:<br/>NEVER claim these (hard)"]
    PROMPT --> LLM["Sonnet tailor"]
    LLM --> LINT["honesty linter (post-hoc, ~1ms):<br/>invented role/project? · metric not in CV? ·<br/>industry/compliance term not in CV?"]
    LINT --> OUT["advisories — never block<br/>green 'passed' / amber 'verify these'"]
```

Fabrication means inventing *history* (a made-up role, a metric the CV never stated, a compliance domain never mentioned). Adding a JD *skill* to the Skills section for ATS coverage is the tailor's job and is explicitly allowed — the user opts in per skill via chips, with CV-backed skills shown green and not-yet-in-CV skills shown amber ("be ready to speak to these").

---

## Live job search

A natural-language query is parsed into structured filters, then four platforms are scraped **concurrently** and streamed to the client as results arrive.

```mermaid
sequenceDiagram
    participant B as Browser
    participant API as /search/stream
    participant MCF as MyCareersFuture
    participant LI as LinkedIn
    participant JS as JobStreet
    participant Q as asyncio.Queue

    B->>API: POST /search/stream {query, filters?, resume_markdown?}
    API->>API: parse_search_query (Haiku) — or build_query (deterministic, if UI filters)
    par four platforms run concurrently
        API->>MCF: JSON /v2/jobs (full JD inline)
        MCF->>Q: cards
    and
        API->>LI: guest HTML (cards only)
        LI->>Q: cards
    and
        API->>JS: Patchright browser (cards only)
        JS->>Q: cards
    end
    Q-->>API: cards as they arrive
    API->>API: tag skill have/missing + relevance,<br/>(optional) learned fit score
    API-->>B: NDJSON — interpreted line, a job line each, done
    B->>API: POST /job/description (on drawer open) — lazy full JD
    B->>API: POST /jobs/enrich/stream (background) — backfill every card's keywords
```

To stay fast and avoid tripping platform soft-walls, LinkedIn/JobStreet return **cards only**; full descriptions are fetched **on demand** when a job is opened, and keywords are **backfilled in the background** after first render. Large searches spread a **weighted per-platform budget** so a fast source can't starve the slower ones.

When the optional fit predictor is on, the flow forks:

```mermaid
flowchart TB
    R["scored results"] --> P{"predictor enabled?"}
    P -- "no (local default)" --> LAZY["lazy card-first path:<br/>rank by gazetteer relevance"]
    P -- "yes (prod)" --> EAGER["eagerly fetch + preprocess each JD,<br/>score fit (embed CV once)"]
    EAGER --> G{"strong_fits_only?"}
    G -- "false (default)" --> ALL["return EVERY scored job,<br/>ranked by fit — no hiding"]
    G -- "true (UI toggle)" --> GATE["soft gate + floor + 3× scrape cap<br/>→ curated strong-fit list"]
```

---

## Fit predictor

An optional bi-encoder (SBERT/MiniLM + LoRA) scores resume↔JD fit, exported to ONNX and split into a **two-tower** encoder + head so a search embeds the CV **once** rather than per job.

```mermaid
flowchart LR
    CVR["resume"] --> ENC["encoder.onnx<br/>(SBERT + LoRA)"]
    ENC --> EV["CV embedding<br/>computed ONCE per search"]
    JDR["each JD (preprocessed<br/>to a 512-token budget)"] --> ENC2["encoder.onnx"]
    ENC2 --> JV["JD embedding"]
    EV --> HEAD["head.onnx"]
    JV --> HEAD
    HEAD --> CAL["calibration.json<br/>percentile stretch"]
    CAL --> FIT["fit % → relative tier<br/>Strong / Moderate / Weak + top-fit marker"]
```

The headline stays **relative** (percentile within the current results), not a misleading absolute score — the signal is genuinely noisy (strong roles land ~40–85%, unrelated <15%).

---

## Job-intel panel

Opening a job runs a deterministic, stateless legitimacy scan — no LLM, ~1 ms.

```mermaid
flowchart TB
    OPEN["Open a job in the drawer"] --> RF["scan_red_flags(job)<br/>(auto, deterministic)"]
    RF --> CHECKS["upfront-payment · messaging-only contact ·<br/>personal email · NRIC/bank asks · too-good pay ·<br/>urgency · vague JD · unlicensed agency (MOM EA licence) ·<br/>stale posting · evergreen phrasing"]
    CHECKS --> OUT["flags cited to FTC / SPF / MOM<br/>advisory · never blocks"]
```

---

## Local matching engine

`src/matching/` is a curated AI/ML/data/cloud **skills gazetteer** (canonical terms → aliases) plus a deterministic phrase matcher. It resolves `torch → PyTorch`, `k8s → Kubernetes`, handles `C++`/`C#`/`Node.js`, and avoids false hits (`java` inside `javascript`, a bare `go`). It powers per-job skill overlap, the tailoring pipeline's honesty gate, search ranking, insights, and the guardrail's skill awareness — **free, ~1 ms, exact-repeatable**, with no LLM call per job.

### One extractor for search and tailoring

The gazetteer is the **single source of a JD's skills**. Search cards and the tailor's match/score/chips all run the same `extract_skills`, so a job can't show one skill count on the card and a different one in the tailor. The Haiku JD parser still reads the JD's *structure* (title, company, seniority, responsibilities), but `reconcile_jd_skills` replaces its free-form skill lists with the gazetteer — and hands back the skills Haiku named that the gazetteer *doesn't* know as **growth candidates**.

```mermaid
flowchart TB
    JD["JD text"] --> HAIKU["Haiku parse (structure)<br/>+ free-form skills"]
    HAIKU --> REC["reconcile_jd_skills"]
    GAZ["gazetteer extract_skills"] --> REC
    REC --> SKILLS["JD skills = gazetteer set<br/>(same as the search card)"]
    REC --> CAND["growth candidates<br/>(Haiku named, gazetteer doesn't know)"]
    CAND --> Q["Supabase growth_candidates<br/>(frequency-ranked queue)"]
    Q --> CURATE["human curates → new gazetteer entries"]
```

Persistence (`src/growth.py`) is **fire-and-forget and fail-open** — a PostgREST RPC over HTTPS, scheduled off the request path so it never adds latency, and a no-op when Supabase isn't configured. The table stores only anonymous skill terms + an example job title (no user data). It's the first, deliberately tiny brick of a future job-market data platform: a review queue that turns "the gazetteer missed something" into a curation signal instead of a silent gap.
