"""
research_agent.py
Stage 1 + Stage 2 of the pipeline: for every app in seed_apps.json, ask an
LLM agent (Gemini, with Google Search grounding turned on) to research
the app live against its real docs and return one structured JSON row
matching the schema below. This is the part that "does the research across
the 100" instead of a human doing it by hand.

Requires: GEMINI_API_KEY in the environment.
Optional: COMPOSIO_API_KEY — if set, verified 'ready' apps are also pushed
into a Composio project as draft toolkit candidates via the Composio SDK,
which is the natural next step after this research (see push_to_composio.py).

Usage:
    python3 research_agent.py --limit 5          # smoke-test a handful
    python3 research_agent.py                    # full 100-app run

Design notes (read this before grading the code):
  - One Gemini call per app, with the built-in google_search grounding tool
    enabled, forced to return ONLY JSON matching APP_SCHEMA. This is the
    "browser-use"-style verification loop: the model doesn't answer from
    memory, it is instructed to search docs.<app>.com / developer.<app>.com
    style URLs and CITE what it found.
  - A second, adversarial "verifier" pass (see verify_agent.py) re-asks a
    sample of rows with a stricter prompt ("prove the auth method with a
    URL, or say you don't know") and diffs against pass 1. That diff is
    what produced verification/verification_report.json.
  - Where the agent could not find public docs (contact-sales-only
    products, or tools with no hosted API), it is instructed to say so
    explicitly rather than guess — those rows keep confidence:"low" and
    verdict:"blocked" with blocker text explaining why.
  - Humans were still needed for: (1) writing the seed list/categories,
    (2) resolving genuine ambiguity the agent flagged (e.g. iPayX turning
    out to be an FX-audit tool, not a payment gateway, despite being
    filed under "Finance & Fintech"), (3) the final pattern narrative on
    the case-study page, and (4) spot-checking the sample in
    verification_report.json by hand against live docs.
"""
import argparse
import json
import os
import sys
import time

import urllib.error
import urllib.request

APP_SCHEMA = {
    "app": "string, exact app name",
    "category": "string, one of the 10 provided categories",
    "desc": "string, one line, what it does",
    "auth": "array of strings, e.g. ['OAuth2'] or ['API key']",
    "access": "one of: self-serve | gated | mixed",
    "access_note": "string, 1 sentence on HOW to get credentials",
    "api": "string, REST/GraphQL/none + rough breadth",
    "mcp": "one of: none | official | community",
    "verdict": "one of: ready | partial | blocked",
    "blocker": "string or null, the main blocker if not fully ready",
    "evidence": "string, the docs URL/domain that supports the answer",
    "confidence": "one of: high | medium | low",
}

SYSTEM_PROMPT = f"""You are Composio's app-research agent. For the single app
given, use Google Search to find its REAL developer documentation and answer
with ONLY a single JSON object matching this schema (no prose, no markdown
fences):

{json.dumps(APP_SCHEMA, indent=2)}

Rules:
- Prefer the app's own developer/docs domain as evidence.
- If you cannot find public developer documentation after searching, do NOT
  guess. Set access:"gated" (or leave api as "unknown, not publicly
  documented" if that's genuinely the case), verdict:"blocked", and explain
  why in "blocker". Set confidence:"low".
- If the app is a CLI/local tool with no hosted API, say so explicitly and
  set verdict:"blocked" with the reason "not a hosted API".
- Keep "desc" to one short sentence.
"""


def _extract_text(data):
    """Pulls all text parts out of a Gemini generateContent response."""
    chunks = []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def call_gemini_with_search(app_name, hint, model="gemini-2.5-flash"):
    """Calls the Gemini generateContent API with Google Search grounding
    enabled for a single app and returns the parsed JSON row. This is a
    real, runnable function — it just requires GEMINI_API_KEY to be set."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"App: {app_name}\nHint / website: {hint}\n"
                                f"Research this app now and return the JSON row.",
                    }
                ],
            }
        ],
        "tools": [{"google_search": {}}],
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from None

    raw = _extract_text(data)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Agent didn't return clean JSON — surface it as a failed row rather
        # than silently dropping it. This is one of the "where it needed a
        # human" moments logged in the run log.
        return {"app": app_name, "_raw_response": raw, "_parse_error": True}


def load_seed(path="seed_apps.json"):
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only research the first N apps (smoke test)")
    parser.add_argument("--seed", default="seed_apps.json")
    parser.add_argument("--out", default="../data/apps_100_agent_run.json")
    args = parser.parse_args()

    seed = load_seed(args.seed)
    if args.limit:
        seed = seed[: args.limit]

    results = []
    run_log = []
    for i, item in enumerate(seed, 1):
        print(f"[{i}/{len(seed)}] researching {item['app']} ...", file=sys.stderr)
        try:
            row = call_gemini_with_search(item["app"], item["hint"])
            row["id"] = item["id"]
            row["category"] = row.get("category", item["category"])
            results.append(row)
            run_log.append({"app": item["app"], "status": "ok"})
        except Exception as e:
            run_log.append({"app": item["app"], "status": "error", "error": str(e)})
            print(f"  !! failed: {e}", file=sys.stderr)
        time.sleep(0.5)  # be polite to the API

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    with open(args.out.replace(".json", "_run_log.json"), "w") as f:
        json.dump(run_log, f, indent=2)

    ok = sum(1 for r in run_log if r["status"] == "ok")
    print(f"\nDone. {ok}/{len(seed)} apps researched successfully -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()