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
  logged and never fails the job. Sources ingested before tracking read as done at version 1.
- **Stage versions** (`STAGE_VERSIONS`): a change that should reach ingested sources bumps its stage's version. On
  start the worker finds sources whose recorded version is older and restarts each from its earliest outdated stage.
  Extraction is redone in place by the caption job (`refresh`: page text and signals updated, captions and page
  embeddings kept), never by re-running `process_source`. A reprocessed stage continues the pipeline only when its
  output changed (new captions or changed text), so a version bump costs model calls only where it matters. Captions
  record the version a page was checked with (`source_page.caption_version`), so pages without visual content are
  re-sent to the model only after the caption version changes.
- **Worker entrypoint** `python -m commands.worker`: before handing over to surreal-commands it re-queues jobs left
  `running` (single-worker assumption; `OPEN_NOTEBOOK_REQUEUE_INTERRUPTED=false` for shared databases), deletes
  stage rows of deleted sources and queues the reprocessing (`OPEN_NOTEBOOK_AUTO_REPROCESS=false` to turn it off).
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
