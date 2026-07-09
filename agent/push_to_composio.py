"""
push_to_composio.py
Optional closing stage: for every app whose verdict is "ready", register it
as a draft toolkit candidate in a Composio project using the Composio SDK.
This is the "so what" step — the research isn't just a report, it directly
seeds Composio's own toolkit backlog with the apps that are provably
buildable today, tagged with their auth method so the toolkit scaffolding
can pick the right auth flow automatically.

Requires: COMPOSIO_API_KEY in the environment, and the `composio` Python
package (`pip install composio_client --break-system-packages`).

This script was written to the current public Composio SDK surface as
documented at docs.composio.dev; if the SDK has moved on by the time this
is run, treat this file as the intent/spec and adjust the client calls —
the research data in ../data/apps_100.json is the actual deliverable, this
script is the "what we'd do next" glue.
"""
import json
import os
import sys

def main():
    api_key = os.environ.get("COMPOSIO_API_KEY")
    if not api_key:
        print("COMPOSIO_API_KEY not set — skipping push, this stage is optional.", file=sys.stderr)
        return

    try:
        from composio_client import Composio
    except ImportError:
        print("composio_client not installed. Run: pip install composio_client --break-system-packages", file=sys.stderr)
        return

    client = Composio(api_key=api_key)

    with open("../data/apps_100.json") as f:
        apps = json.load(f)

    ready = [a for a in apps if a["verdict"] == "ready"]
    pushed, failed = 0, 0
    for a in ready:
        try:
            # Indicative call shape — see docs.composio.dev for the current
            # toolkit-draft / custom-tool creation endpoint.
            client.toolkits.drafts.create(
                name=a["app"],
                category=a["category"],
                description=a["desc"],
                auth_methods=a["auth"],
                docs_url=a["evidence"],
                notes=f"Auto-drafted from research agent. Confidence: {a['confidence']}.",
            )
            pushed += 1
        except Exception as e:
            print(f"  failed to push {a['app']}: {e}", file=sys.stderr)
            failed += 1

    print(f"Pushed {pushed} draft toolkits to Composio, {failed} failed.", file=sys.stderr)


if __name__ == "__main__":
    main()