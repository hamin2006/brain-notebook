"""Score vision models on reading neural-network diagrams (edges, branches, counts).

Each image is sent once per model per run with all of its questions; answers come
back as JSON and are graded against ground_truth.json. Stdlib only.

Usage:
  OPENROUTER_API_KEY=... python3 run_diagram_eval.py [--runs 2] [--models a,b,c]
  python3 run_diagram_eval.py --key-file ~/path/.env   # reads OPENROUTER_API_KEY= from it
"""

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = [
    "qwen/qwen3.8-flash",
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
    "minimax/minimax-m3",
    "moonshotai/kimi-k2.5",
    "google/gemini-3.8-flash",
    "anthropic/claude-sonnet-5.5",
]

PROMPT = """You are reading a lecture slide that contains neural-network diagrams.
Trace the arrows carefully: every answer must follow the edges actually drawn.

Answer each question below. Reply with ONE JSON object and nothing else, with
exactly these keys plus a "mermaid" key holding a Mermaid `graph TD` of the
main block/module diagram(s) on the slide.

Answer formats:
- paths: list of lists of operation names, e.g. [["1x1 conv"], ["1x1 conv", "3x3 conv"]]
- layers: list of strings like "3x3, 64"
- int: a number. bool: true/false. op: an operation name.

Questions:
{questions}
"""


def norm_op(value) -> str:
    s = str(value).lower()
    kernel = re.search(r"(\d)\s*[x×]\s*(\d)", s)
    k = f"{kernel.group(1)}x{kernel.group(2)}" if kernel else ""
    if "pool" in s:
        return f"maxpool{k or '3x3'}"
    return f"conv{k}" if k else s.strip()


def parse_layers(value) -> list:
    out = []
    for item in value or []:
        s = " ".join(map(str, item)) if isinstance(item, (list, tuple)) else str(item)
        m = re.search(r"(\d)\s*[x×]\s*(\d)\D+(\d+)", s)
        out.append((f"{m.group(1)}x{m.group(2)}", int(m.group(3))) if m else (s, None))
    return out


def first_int(value):
    m = re.search(r"-?\d+", str(value))
    return int(m.group()) if m else None


def as_bool(value):
    if isinstance(value, bool):
        return value
    return {"true": True, "yes": True, "false": False, "no": False}.get(
        str(value).strip().lower()
    )


def grade(qtype: str, expected, got) -> bool:
    if got is None:
        return False
    if qtype == "paths":
        want = {tuple(p) for p in expected}
        have = {
            tuple(norm_op(op) for op in p) for p in got if isinstance(p, (list, tuple))
        }
        return have == want
    if qtype == "layers":
        return parse_layers(got) == [tuple(x) for x in expected]
    if qtype == "int":
        return first_int(got) == expected
    if qtype == "bool":
        return as_bool(got) is expected
    if qtype == "op":
        return norm_op(got) == expected
    raise ValueError(qtype)


def extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


def ask(model: str, image: Path, questions: dict, key: str) -> dict:
    qtext = "\n".join(
        f'- "{qid}" ({q["type"]}): {q["ask"]}' for qid, q in questions.items()
    )
    b64 = base64.b64encode(image.read_bytes()).decode()
    body = {
        "model": model,
        "max_tokens": 16000,
        "usage": {"include": True},
        "provider": {"require_parameters": True},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": PROMPT.format(questions=qtext)},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        return {
            "error": f"HTTP {e.code}: {e.read().decode()[:300]}",
            "seconds": time.time() - start,
        }
    except Exception as e:  # network errors, timeouts
        return {"error": repr(e), "seconds": time.time() - start}

    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    usage = data.get("usage", {})
    result = {
        "text": text,
        "seconds": time.time() - start,
        "cost": usage.get("cost"),
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
    }
    try:
        result["answers"] = extract_json(text)
    except (json.JSONDecodeError, ValueError) as e:
        result["error"] = f"unparseable JSON: {e}"
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--key-file", help="dotenv file containing OPENROUTER_API_KEY=")
    args = ap.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY")
    if args.key_file:
        for line in Path(args.key_file).expanduser().read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("no OPENROUTER_API_KEY (set it or pass --key-file)")
    truth = json.loads((HERE / "ground_truth.json").read_text())
    models = [m for m in args.models.split(",") if m]

    outdir = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True)
    jobs = [(m, img, run) for m in models for img in truth for run in range(args.runs)]
    print(f"{len(jobs)} calls queued -> {outdir}", flush=True)
    summary: dict = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(ask, m, HERE / img, truth[img]["questions"], key): (m, img, run)
            for m, img, run in jobs
        }
        for done, future in enumerate(as_completed(futures), 1):
            model, img, run = futures[future]
            res = future.result()
            qs = truth[img]["questions"]
            answers = res.get("answers", {})
            checks = {
                qid: grade(q["type"], q["answer"], answers.get(qid))
                for qid, q in qs.items()
            }
            status = (
                res.get("error", "")[:80]
                or f"{sum(checks.values())}/{len(checks)} correct"
            )
            print(
                f"[{done:2d}/{len(jobs)}] {model:30s} {Path(img).stem[9:]:20s} run{run} "
                f"{res['seconds']:5.1f}s ${res.get('cost') or 0:.4f}  {status}",
                flush=True,
            )
            record(summary, outdir, model, img, run, res, checks)

    rows = sorted(
        summary.items(),
        key=lambda kv: (-kv[1]["correct"] / kv[1]["total"], kv[1]["cost"]),
    )
    print(f"\n{'model':32s} {'score':>9s} {'cost/img':>9s} {'sec/img':>8s} err  missed")
    for model, s in rows:
        n = len(s["seconds"])
        missed = ", ".join(f"{q}x{c}" for q, c in sorted(s["misses"].items()))
        print(
            f"{model:32s} {s['correct']:3d}/{s['total']:<3d}  ${s['cost'] / n:8.5f} {sum(s['seconds']) / n:8.1f} {s['errors']:3d}  {missed}"
        )
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nraw responses: {outdir}")


def record(summary, outdir, model, img, run, res, checks):
    """Accumulate one call's grades into the per-model summary and save the raw response."""
    s = summary.setdefault(
        model,
        {
            "correct": 0,
            "total": 0,
            "cost": 0.0,
            "seconds": [],
            "errors": 0,
            "misses": {},
        },
    )
    s["correct"] += sum(checks.values())
    s["total"] += len(checks)
    s["cost"] += res.get("cost") or 0
    s["seconds"].append(res["seconds"])
    s["errors"] += "error" in res
    for qid, ok in checks.items():
        if not ok:
            s["misses"][qid] = s["misses"].get(qid, 0) + 1
    safe = model.replace("/", "__")
    (outdir / f"{safe}__{Path(img).stem}__run{run}.json").write_text(
        json.dumps(
            {"model": model, "image": img, "run": run, "checks": checks, **res},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
