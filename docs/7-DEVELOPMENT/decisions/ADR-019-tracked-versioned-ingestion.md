# ADR-019: Ingestion stages are tracked and versioned; the worker recovers and reprocesses on start

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [ADR-015](ADR-015-page-aware-ingestion.md) (the stages), [content-processing.md](../content-processing.md), [ingestion.md](../../2-CORE-CONCEPTS/ingestion.md)

## Context

A PDF goes through six background jobs (extract → caption → embed and analyze → page images and concepts). Ingesting
three courses (22 decks) exposed how little of that was observable or recoverable:

- **No progress.** The source's status covered only the first job; a card said "completed" while captions, the
  outline and concepts were still running for another ten minutes. Timing a course needed an ad-hoc script polling
  the job queue.
- **Deploys lost work.** surreal-commands only picks up `new` jobs on start, so a job running when the worker
  restarted stayed `running` forever (eight such jobs had accumulated). Deploys had to wait for ingestion to finish.
- **Improvements didn't reach existing notebooks.** A better caption rule or prompt applied only to new uploads;
  every fix needed a hand-run backfill script.
- **Re-runs duplicated insights**: re-running extraction added a second copy of each default transformation.

## Decision

**Every stage records its state per source, carries a version, and the worker brings sources up to date when it
starts.**

- **`source_stage`** (one row per source and stage, migration 31): `queued` → `running` → `done` / `skipped` /
  `failed`, timestamps, the stage version that produced the current output, an error and a small detail object.
  Jobs write it through `open_notebook/domain/ingestion.py` (`tracked()`, `stage_queued()`); a failing write is
  logged and never fails the job. A source without rows predates tracking: its stages read as done at version 1.
  When the first row is written for a source that already has output (pages or chunks), its other stages are
  recorded as done at version 1 first, so they stay done once rows exist; a new source has no output yet.
- **Partial failures are failures.** A stage that works per item (pages to caption, sections to outline, summarize or
  extract concepts from) keeps going when one item's model call fails and falls back (page windows for an unreadable
  outline, a plain extract for an empty summary) or leaves the item out. It reports that with `run.partly_failed()`:
  the job succeeds and the pipeline continues with what it has, but the stage is recorded as `failed` with the reason
  and the failed items in `detail`, so the restart rules below retry it. Recording it as done would keep the gap until
  someone bumped the version (captions did this until caption 3).
- **Stage versions** (`STAGE_VERSIONS`): a change that should reach ingested sources bumps its stage's version. On
  start the worker finds sources whose recorded version is older and restarts each from its earliest outdated stage.
  Extraction is redone in place by the caption job (`refresh`: page text and signals updated, captions and page
  embeddings kept), never by re-running `process_source`. A reprocessed stage continues the pipeline only when its
  output changed (new captions or changed text), so a version bump costs model calls only where it matters. Captions
  record the version a page was checked with (`source_page.caption_version`); a page checked at
  `CAPTION_CHECKS_VALID_FROM` or later is not asked again, so a bump that only re-runs the stage costs nothing on
  pages already checked, and one that changes the prompt or page selection raises it too.
- **Worker entrypoint** `python -m commands.worker`: before handing over to surreal-commands it re-queues jobs left
  `running` (single-worker assumption; `OPEN_NOTEBOOK_REQUEUE_INTERRUPTED=false` for shared databases), deletes
  stage rows of deleted sources and restarts the sources that need it (`restart_point`;
  `OPEN_NOTEBOOK_AUTO_REPROCESS=false` turns it off): a **failed** stage is retried (a deploy usually fixes what broke
  it; once per start, so a permanent failure doesn't loop), a **stalled** chain (a stage pending with nothing queued or
  running) is resumed, and an **outdated** stage is re-run. Sources with a live job in the queue are left alone; a
  stage marked queued or running with no live job for its source (its job died, or failed before reaching it) counts
  as pending. When the stages after the restart point already finished, the pipeline continues past it only if its
  output changed. A
  failed extraction of a source without pages needs its content re-read and is left to the user.
- **Visible progress**: `GET /api/sources/{id}/ingestion`, `GET /api/notebooks/{id}/ingestion` and
  `POST /api/sources/{id}/ingestion/retry`; the library shows an indexing strip and per-source stage, the Structure
  tab a stage timeline; `scripts/brain/ingest_folder.py --wait` prints per-stage timing.
- **Idempotent re-runs**: ingestion replaces a transformation's earlier insight (`add_insight(replace=True)`).

## Alternatives considered

- **Derive progress from the job queue** (`command` table): rejected; commands don't record when they finished,
  their arguments differ per job, and they say nothing about skipped stages or versions.
- **A status field on the source**: rejected; six concurrent jobs updating one record conflict, and a single field
  can't show which stage failed.
- **Reprocess everything on a version bump**: rejected; re-analysis and concept extraction cost model calls on every
  source, while most bumps change a few pages.
- **Manual backfill scripts per change** (as before): rejected; they were forgotten, and nothing recorded which
  sources had been upgraded.

## Consequences

- Changing a stage's code or prompt in a way existing notebooks should get means bumping `STAGE_VERSIONS` (with a
  one-line reason in the comment above it); the next worker start does the rest.
- Every stage must stay idempotent: it may run again after a restart or a reprocess.
- New stages get a row in `STAGES`/`STAGE_COMMANDS`, tracking in their command, a `source_delete` cascade line (already
  covers `source_stage`) and a label in the UI.
