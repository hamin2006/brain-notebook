"""Run the agent eval set against a running Open Notebook API and grade the answers.

Modes:
  chat   current notebook chat: default context (every source's insights, or full
         text when it has none) pasted into one prompt via /chat/execute
  ask    current Ask: /search/ask/simple scoped to the notebook
  agent  the agentic chat (Phase 2+), /chat/execute on the agent graph

Checks per question (see questions.json): required lectures cited or named, required
facts present, "not found" stated, a note saved. Page accuracy (a cited/named page
inside the evidence range) is reported separately and does not gate pass/fail.

Prints one line per question as it finishes; writes results/<mode>-<timestamp>/.

Usage (on the PC, next to the API):
  uv run python evals/agent/run_eval.py --mode chat --notebook "AI 360 Deep Learning" \
      --key-file ~/workplace/TradingAgents/.env
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
API = "http://127.0.0.1:5055/api"
CITATION = re.compile(
    r"(source_insight|insight|note|source):([a-z0-9]+)(?:#p(\d+)(?:-(\d+))?)?", re.I
)
NOT_FOUND = re.compile(
    r"(not|n't|no)\s+(\w+\s+){0,4}(cover|discuss|mention|address|includ|contain|found|appear|in (the|your|these))"
    r"|no (information|mention|content|material)|outside (the )?(scope|course)",
    re.I,
)
PAGE_MENTION = re.compile(
    r"\b(?:p\.|pp\.|page|pages|slide|slides)\s*(\d+)(?:\s*[-–]\s*(\d+))?", re.I
)


def openrouter_usage(key_file):
    if not key_file:
        return None
    key = next(
        (
            line.split("=", 1)[1].strip().strip("\"'")
            for line in Path(key_file).expanduser().read_text().splitlines()
            if line.startswith("OPENROUTER_API_KEY=")
        ),
        None,
    )
    r = httpx.get(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": f"Bearer {key}"},
        timeout=20,
    )
    return r.json()["data"]["total_usage"]


class Corpus:
    """Maps lecture numbers <-> source ids, and insight ids -> source ids."""

    def __init__(self, client: httpx.Client, notebook_id: str):
        self.sources = (
            client.get("/sources", params={"notebook_id": notebook_id, "limit": 200})
            .raise_for_status()
            .json()
        )
        self.lecture_of: dict = {}
        for s in self.sources:
            m = re.search(r"lecture\s*(\d+)", s.get("title") or "", re.I)
            if m:
                self.lecture_of[s["id"]] = int(m.group(1))
        self.insight_source: dict = {}
        for s in self.sources:
            for ins in (
                client.get(f"/sources/{s['id']}/insights").raise_for_status().json()
            ):
                self.insight_source[ins["id"]] = s["id"]

    def cited(self, answer: str):
        """Lectures cited by id, and (lecture, page) pairs from page-suffixed citations."""
        lectures, pages = set(), set()
        for kind, key, p1, p2 in CITATION.findall(answer):
            kind = "source_insight" if kind.lower() == "insight" else kind.lower()
            full = f"{kind}:{key}"
            sid = full if kind == "source" else self.insight_source.get(full)
            if sid in self.lecture_of:
                lec = self.lecture_of[sid]
                lectures.add(lec)
                if p1:
                    for p in range(int(p1), int(p2 or p1) + 1):
                        pages.add((lec, p))
        return lectures, pages


def named_lectures(answer: str):
    return {int(n) for n in re.findall(r"lecture\s*(\d+)", answer, re.I)}


def named_pages(answer: str):
    pages = set()
    for a, b in PAGE_MENTION.findall(answer):
        for p in range(int(a), int(b or a) + 1):
            pages.add(p)
    return pages


def grade(
    q: dict, answer: str, corpus: Corpus, notes_before: list, notes_after: list
) -> dict:
    checks = {}
    cited_lec, cited_pages = corpus.cited(answer)
    mentioned = cited_lec | named_lectures(answer)
    for lec in q.get("lectures", []):
        checks[f"lecture {lec}"] = lec in mentioned
    for i, group in enumerate(q.get("facts", [])):
        checks[f"fact {i + 1}"] = any(re.search(rx, answer, re.I) for rx in group)
    if q.get("not_found"):
        checks["says not found"] = bool(NOT_FOUND.search(answer))
    if q.get("expects_note"):
        new = [n for n in notes_after if n["id"] not in {m["id"] for m in notes_before}]
        checks["note saved"] = any(
            q["expects_note"] in (n.get("content") or "").lower() for n in new
        )

    page_ok = None
    if q.get("pages"):
        want = {
            (int(lec), p)
            for lec, ranges in q["pages"].items()
            for a, b in ranges
            for p in range(a, b + 1)
        }
        loose = {(lec, p) for lec in mentioned for p in named_pages(answer)}
        page_ok = bool(want & (cited_pages | loose))
    return {
        "checks": checks,
        "passed": all(checks.values()) if checks else False,
        "page_ok": page_ok,
        "cited_lectures": sorted(cited_lec),
    }


def run_chat(client, notebook_id, corpus, q, effort=None):
    session = (
        client.post(
            "/chat/sessions",
            json={"notebook_id": notebook_id, "title": f"eval {q['id']}"},
        )
        .raise_for_status()
        .json()
    )
    config = {
        "sources": {
            s["id"]: ("insights" if s.get("insights_count") else "full content")
            for s in corpus.sources
        },
        "notes": {},
    }
    context = (
        client.post(
            "/chat/context", json={"notebook_id": notebook_id, "context_config": config}
        )
        .raise_for_status()
        .json()["context"]
    )
    answer = ""
    for turn in q.get("turns") or [q["question"]]:
        body = {"session_id": session["id"], "message": turn, "context": context}
        if effort:
            body["effort"] = effort
        resp = client.post("/chat/execute", json=body).raise_for_status().json()
        answer = resp["messages"][-1]["content"]
    client.delete(f"/chat/sessions/{session['id']}")
    return answer


def run_ask(client, notebook_id, chat_model, q):
    answer = ""
    for turn in q.get("turns") or [
        q["question"]
    ]:  # Ask has no memory; follow-ups are asked cold
        resp = (
            client.post(
                "/search/ask/simple",
                json={
                    "question": turn,
                    "strategy_model": chat_model,
                    "answer_model": chat_model,
                    "final_answer_model": chat_model,
                    "notebook_id": notebook_id,
                },
            )
            .raise_for_status()
            .json()
        )
        answer = resp["answer"]
    return answer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["chat", "ask", "agent"], required=True)
    ap.add_argument("--notebook", required=True)
    ap.add_argument(
        "--only",
        help="comma-separated question ids or task types (e.g. T4,adam-defaults)",
    )
    ap.add_argument("--effort", help="agent effort level (agent mode)")
    ap.add_argument(
        "--key-file", help="dotenv with OPENROUTER_API_KEY, to report spend"
    )
    args = ap.parse_args()

    client = httpx.Client(base_url=API, timeout=600)
    notebook = next(
        n
        for n in client.get("/notebooks").raise_for_status().json()
        if n["name"] == args.notebook
    )
    corpus = Corpus(client, notebook["id"])
    chat_model = (
        client.get("/models/defaults").raise_for_status().json()["default_chat_model"]
    )
    questions = json.loads((HERE / "questions.json").read_text())["questions"]
    if args.only:
        wanted = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in wanted or q["task"] in wanted]

    outdir = HERE / "results" / f"{args.mode}-{datetime.now():%Y%m%d-%H%M%S}"
    outdir.mkdir(parents=True)
    spend_before = openrouter_usage(args.key_file)
    print(
        f"{len(questions)} questions, mode={args.mode}, notebook={notebook['id']}",
        flush=True,
    )

    rows = []
    for i, q in enumerate(questions, 1):
        notes_before = (
            client.get("/notes", params={"notebook_id": notebook["id"]}).json()
            if q.get("expects_note")
            else []
        )
        start = time.time()
        try:
            if args.mode == "ask":
                answer = run_ask(client, notebook["id"], chat_model, q)
            else:
                answer = run_chat(client, notebook["id"], corpus, q, effort=args.effort)
            error = None
        except httpx.HTTPError as e:
            answer, error = (
                "",
                f"{type(e).__name__}: {getattr(e, 'response', None) and e.response.text[:200]}",
            )
        seconds = time.time() - start
        notes_after = (
            client.get("/notes", params={"notebook_id": notebook["id"]}).json()
            if q.get("expects_note")
            else []
        )
        result = grade(q, answer, corpus, notes_before, notes_after)
        row = {
            "id": q["id"],
            "task": q["task"],
            "seconds": round(seconds, 1),
            "error": error,
            **result,
            "answer": answer,
        }
        rows.append(row)
        (outdir / f"{q['id']}.json").write_text(json.dumps(row, indent=2))
        failed = [k for k, v in result["checks"].items() if not v]
        status = (
            "PASS"
            if result["passed"]
            else ("ERROR " + error if error else "fail: " + ", ".join(failed))
        )
        print(
            f"[{i:2d}/{len(questions)}] {q['task']:3s} {q['id']:24s} {seconds:5.1f}s page={result['page_ok']}  {status}",
            flush=True,
        )

    spend_after = openrouter_usage(args.key_file)
    by_task: dict = {}
    for r in rows:
        t = by_task.setdefault(r["task"], [0, 0])
        t[0] += r["passed"]
        t[1] += 1
    paged = [r["page_ok"] for r in rows if r["page_ok"] is not None]
    summary = {
        "mode": args.mode,
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
        "page_accuracy": f"{sum(paged)}/{len(paged)}",
        "image_only_passed": f"{sum(r['passed'] for r, q in zip(rows, questions) if q.get('image_only'))}/{sum(1 for q in questions if q.get('image_only'))}",
        "by_task": {
            k: f"{v[0]}/{v[1]}"
            for k, v in sorted(by_task.items(), key=lambda kv: int(kv[0][1:]))
        },
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2]
        if rows
        else None,
        "openrouter_spend_usd": round(spend_after - spend_before, 4)
        if spend_before is not None
        else None,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
