# ADR-020: Ingestion runs wide, parses PDFs in processes and fits a memory budget

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [ADR-019](ADR-019-tracked-versioned-ingestion.md) (the tracked stages), [content-processing.md](../content-processing.md), [Advanced → Performance tuning](../../5-CONFIGURATION/advanced.md#performance-tuning)

## Context

Re-captioning four courses (29 decks) took about 40 minutes, and the stack sat at 4.8 GB of RAM idle on the PC. The
stage timings and memory readings showed where both went:

- **Two job slots.** The systemd worker ran `--max-tasks 2`; nearly all stage time is waiting on model calls, so two
  slots meant about 80 minutes of job time queued through two lanes.
- **Sequential stages.** Concepts waited for the whole analysis (outline, every section summary, the document
  summary) although they need only the outline; sections and caption pages ran 4 model calls at a time.
- **PDF parsing on one core.** pdfplumber is pure Python. The worker parsed decks in threads, which the GIL runs one
  page at a time: on a 738-page course, extraction was 10 of the 10.4 minutes once everything else ran in parallel.
- **A whole-document prompt per upload.** The default "Dense Summary" transformation sent each deck's full text in
  one call (4.4 minutes for the largest deck) and nothing read its output.
- **Memory held after work.** The worker sat at 2.3 GB idle after the run against 126 MB fresh (glibc keeps freed
  memory in one arena per thread), and SurrealDB's RocksDB sized its block cache from host RAM (2.1 GB).

## Decision

**Ingestion is limited by model latency, so it runs as wide as the provider allows; CPU-bound parsing goes to
processes; and every service has a memory cap that together fit the host (6 GB on the PC).**

- **Concurrency**: 8 worker slots (systemd units; `OPEN_NOTEBOOK_WORKER_MAX_TASKS` elsewhere), 10 sections and 8
  caption pages at a time within a document (`OPEN_NOTEBOOK_SECTION_CONCURRENCY`,
  `OPEN_NOTEBOOK_CAPTION_CONCURRENCY`), 3 embedding batches at a time.
- **Earlier fan-out**: analysis writes sections and metadata first, then queues page images and concepts, then writes
  summaries into the same rows in place (replacing rows would hide them from the concepts job mid-read). Concept
  mentions are replaced in one transaction, since a retried analysis can queue concepts twice.
- **PDF parsing in processes**: `extract_pdf_pages` splits large PDFs into 25-page ranges for a shared spawn-process
  pool (`OPEN_NOTEBOOK_PDF_PROCESSES`, default half the CPU threads, at most 4), shut down when idle; a dead parser
  falls back to parsing in place. The per-page code is unchanged, so output is identical and no stage version moves.
- **No whole-document transformation by default**: migration 33 turns off Dense Summary's "suggest by default".
- **Memory**: `MALLOC_ARENA_MAX=2` and `malloc_trim` after each stage; one LibreOffice conversion at a time; caps API
  1 GB, worker 2.5 GB (including its parsers), UI 512 MB; SurrealDB 1.5 GB with a 512 MB RocksDB block cache
  (`docker-compose.yml`). `deploy_pc.sh` moves existing units from the old defaults.

## Results

On the PC, a 7-deck NLP course (738 pages): 10.4 → 4.5 minutes, parsing about 10 seconds, everything but Dense
Summary done at 4.3 minutes; peaks API 317 MB, worker 969 MB, SurrealDB 695 MB (about 2 GB, from 4.8 GB idle
before). A simulated 7-deck course (477 pages, model latencies taken from the PC's stage times): 13 min 50 s → 2 min 59 s
with identical output.

## Alternatives considered

- **Switch page extraction to PDFium** (10–50× faster than pdfplumber): rejected for now; its text differs, and the
  garbled-math detection and LaTeXiT recovery are tuned to pdfplumber's output, so it needs re-validation on real decks
  and a full reprocess. The process pool gets most of the gain with identical output.
- **Separate worker processes** instead of more slots: each costs a full Python process (about 0.5 GB with the
  libraries), where an extra async slot costs only the job's in-flight data.
- **A pool per extraction**: seven concurrent decks would start seven pools; one shared pool bounds processes and
  memory.

## Consequences

- About 40 model calls can be in flight during a large upload. Rate-limited providers need lower
  `OPEN_NOTEBOOK_SECTION_CONCURRENCY` / `OPEN_NOTEBOOK_WORKER_MAX_TASKS`.
- Work that parses or renders inside the worker's process (not a model call) needs a process, not a thread, to run in
  parallel, and its memory counts against the worker's cap.
- A new service or a heavier stage has to fit the budget: check peaks with `systemctl --user show <unit> -p MemoryPeak`
  during an `ingest_folder.py --wait` run.
