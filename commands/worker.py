"""Worker entrypoint: recover, bring ingested sources up to date, then work.

    uv run --env-file .env python -m commands.worker --max-tasks 2

Before handing over to the surreal-commands worker it:

1. Re-queues jobs a stopped worker left `running` (a deploy or crash killed
   them mid-job). The library only picks up `new` jobs, so these would stay
   `running` forever. Stages are idempotent, so running one again is safe.
   This assumes a single worker process, which is how this project runs; set
   OPEN_NOTEBOOK_REQUEUE_INTERRUPTED=false when several workers share a DB.
2. Removes stage rows of deleted sources.
3. Queues outdated sources for reprocessing from their earliest outdated stage
   (see open_notebook/domain/ingestion.py). OPEN_NOTEBOOK_AUTO_REPROCESS=false
   turns this off.

A failure in these steps is logged and never keeps the worker from starting.
"""

import argparse
import asyncio
import os

from loguru import logger


def _enabled(name: str) -> bool:
    return os.environ.get(name, "true").strip().lower() not in ("0", "false", "no")


async def requeue_interrupted() -> int:
    from open_notebook.database.repository import repo_query

    rows = await repo_query(
        "UPDATE command SET status = 'new' WHERE status = 'running' RETURN id"
    )
    return len(rows)


async def remove_orphan_stages() -> int:
    from open_notebook.database.repository import repo_query

    rows = await repo_query("DELETE source_stage WHERE source.id = NONE RETURN BEFORE")
    return len(rows)


async def reprocess_outdated() -> int:
    from open_notebook.domain.ingestion import plan_reprocessing, reprocess

    plan = await plan_reprocessing()
    for source_id, stage in plan.items():
        logger.info(f"Reprocessing {source_id} from its {stage} stage (outdated)")
        await reprocess(source_id, stage)
    return len(plan)


async def prepare() -> None:
    steps = []
    if _enabled("OPEN_NOTEBOOK_REQUEUE_INTERRUPTED"):
        steps.append(("re-queue interrupted jobs", requeue_interrupted))
    steps.append(("remove stage rows of deleted sources", remove_orphan_stages))
    if _enabled("OPEN_NOTEBOOK_AUTO_REPROCESS"):
        steps.append(("reprocess outdated sources", reprocess_outdated))
    for label, step in steps:
        try:
            count = await step()
            if count:
                logger.info(f"Worker startup: {label}: {count}")
        except Exception as e:
            logger.error(f"Worker startup step failed ({label}): {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=int(os.environ.get("OPEN_NOTEBOOK_WORKER_MAX_TASKS", "5")),
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    import commands  # noqa: F401  (registers the commands; sets no_proxy)

    asyncio.run(prepare())

    from surreal_commands.core.worker import run_worker

    run_worker(args.debug, args.max_tasks, ["commands"])


if __name__ == "__main__":
    main()
