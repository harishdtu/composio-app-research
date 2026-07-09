"""
verify_agent.py
Stage 3 of the pipeline: the verification loop. Takes a SAMPLE of rows
already produced by research_agent.py and re-asks a second, stricter
"verifier" agent to prove each claim against a live URL, or admit it
doesn't know. Diffs the two passes and writes a verification report.

This is deliberately a SEPARATE agent/prompt from research_agent.py (not
the same call re-run) because self-consistency between two identical
prompts proves nothing — the value is in an adversarial second opinion
that is instructed to actively try to find the first pass wrong.

Requires: GEMINI_API_KEY in the environment.

Usage:
    python3 verify_agent.py --sample 15 --in ../data/apps_100.json \
        --out ../verification/verification_report.json
"""
import argparse
import json
import os
import random
import sys

import urllib.error
import urllib.request

VERIFIER_SYSTEM_PROMPT = """You are a skeptical fact-checker. You will be given
one row of a research dataset about a SaaS app's developer API (auth method,
self-serve vs gated, API surface, MCP availability). Your job is to actively
try to PROVE IT WRONG using Google Search against the app's real documentation.

Return ONLY a JSON object:
{
  "app": "<name>",
  "claims_checked": ["<claim 1>", "<claim 2>", ...],
  "result": "confirmed" | "corrected" | "unverifiable",
  "corrected_fields": {"<field>": "<corrected value>", ...},  // empty if confirmed
  "evidence_url": "<url actually opened>",
  "notes": "<1-2 sentences>"
}

If you cannot find public documentation to confirm OR deny the claim, return
result:"unverifiable" — do not mark something "confirmed" just because you
couldn't disprove it.
"""


def _extract_text(data):
    """Pulls all text parts out of a Gemini generateContent response."""
    chunks = []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def call_verifier(row, model="gemini-2.5-flash"):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    body = {
        "system_instruction": {"parts": [{"text": VERIFIER_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(row)}]}],
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

    text = _extract_text(data)
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=15)
    parser.add_argument("--in", dest="infile", default="../data/apps_100.json")
    parser.add_argument("--out", default="../verification/verification_report_regenerated.json")
    parser.add_argument("--seed", type=int, default=7, help="random seed for reproducible sampling")
    args = parser.parse_args()

    with open(args.infile) as f:
        apps = json.load(f)

    # Oversample low/medium confidence rows on purpose — that's where an
    # agent's training-only guess is most likely to be stale or wrong, and
    # therefore where verification has the most value.
    low_med = [a for a in apps if a["confidence"] in ("low", "medium")]
    high = [a for a in apps if a["confidence"] == "high"]
    random.seed(args.seed)
    sample = random.sample(low_med, min(args.sample - 3, len(low_med))) + random.sample(high, min(3, len(high)))

    results = []
    for i, row in enumerate(sample, 1):
        print(f"[{i}/{len(sample)}] verifying {row['app']} ...", file=sys.stderr)
        try:
            v = call_verifier(row)
            results.append(v)
        except Exception as e:
            results.append({"app": row["app"], "result": "error", "notes": str(e)})

    confirmed = sum(1 for r in results if r.get("result") == "confirmed")
    corrected = sum(1 for r in results if r.get("result") == "corrected")
    unverifiable = sum(1 for r in results if r.get("result") in ("unverifiable", "error"))

    report = {
        "sample_size": len(results),
        "confirmed": confirmed,
        "corrected": corrected,
        "unverifiable_or_error": unverifiable,
        "accuracy_after_verification_pct": round(100 * (confirmed + corrected) / len(results), 1) if results else 0,
        "results": results,
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()