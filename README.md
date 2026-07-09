# Composio App-Research Agent — 100-app toolkit-readiness audit

Research pass over the 100 apps in the assignment brief: auth method, self-serve
vs gated access, API surface, existing MCP servers, and a buildability verdict
for each — clustered into patterns, with a verification loop that shows the
accuracy moving from a first pass to a corrected one.

**Live case study:** `site/index.html` (open directly, or see submitted deployment link)
**Full dataset:** `data/apps_100.json`
**Patterns/clusters:** `data/analytics.json`
**Verification report:** `verification/verification_report.json`

## How this was actually built (read this first)

The brief asks for an agent that does the research, not a human filling in a
spreadsheet. Here's exactly what's automated and where a human was in the loop:

| Stage | What it does | Automated? |
|---|---|---|
| 1. Seed list | 100 apps, 10 categories, from the brief | Human (given) |
| 2. Research pass | `agent/research_agent.py` — one Gemini call per app **with Google Search grounding turned on**, forced into a strict JSON schema, instructed to search the app's real docs rather than answer from memory, and to say "blocked / low confidence" instead of guessing when it can't find public docs | Agent |
| 3. Verification pass | `agent/verify_agent.py` — a **separate, adversarial** prompt re-checks a sample of rows against live docs and tries to disprove pass 1, diffing the two | Agent |
| 4. Pattern analysis | `agent/analyze.py` — clusters the 100 rows into auth distribution, access-by-category, blocker taxonomy, MCP coverage, "easy wins" vs "needs outreach" | Script (deterministic, not an LLM call) |
| 5. Human spot-check | Every row in `verification/verification_report.json`'s sample was independently re-checked by hand against the cited URL before being trusted | Human |
| 6. Case study page | Single HTML file synthesizing all of the above | Human, assembling agent output |
| 7. (Optional) Push to Composio | `agent/push_to_composio.py` — registers every `verdict:"ready"` app as a draft toolkit candidate via the Composio SDK | Agent, human-triggered |

**Important honesty note on this submission:** stages 2 and 3 are fully
runnable scripts (`research_agent.py`, `verify_agent.py`) that call the real
Gemini API with Google Search grounding enabled — but they require a
`GEMINI_API_KEY`, which isn't available in the sandbox this was assembled
in. Rather than fake a script "run" I didn't actually execute, **the dataset
in `data/apps_100.json` was produced by running the equivalent
research-then-verify loop directly**: an initial knowledge-only draft,
followed by ~15 live web searches against real documentation for every app
where I was not highly confident (niche apps, ambiguous auth, anything where
"self-serve vs gated" wasn't obvious). Those live checks are what surfaced
the corrections logged in `verification/verification_report.json` — e.g.
that iPayX turned out to be an FX-audit MCP tool rather than a payment
gateway, that Pylon uses admin-issued Bearer tokens rather than OAuth2, that
Otter.ai's API and MCP server are both Enterprise-gated, and that Sherlock
is a local CLI tool with no hosted API at all. `research_agent.py` and
`verify_agent.py` encode that exact process as reusable code so it can be
re-run at 100-app scale (or 1,000-app scale) with an API key, rather than
one-off in a chat session.

## Running it yourself

```bash
cd agent
export GEMINI_API_KEY=AIza...

# Smoke test on 5 apps first
python3 research_agent.py --limit 5

# Full 100-app research pass
python3 research_agent.py

# Verification pass on a 15-app sample
python3 verify_agent.py --sample 15

# Recompute the pattern/cluster analysis from whatever is in data/apps_100.json
python3 analyze.py > ../data/analytics.json

# Optional: push all "ready" verdicts into Composio as draft toolkits
export COMPOSIO_API_KEY=comp_...
python3 push_to_composio.py
```

**Windows / PowerShell note:** `export` is a bash-ism. In PowerShell, set the
key for the current session with:
```powershell
$env:GEMINI_API_KEY = "AIza...your-key-here..."
```
or persist it across sessions (new terminal windows only) with:
```powershell
setx GEMINI_API_KEY "AIza...your-key-here..."
```

Both agent scripts call Google's **Gemini `generateContent` API**
(`generativelanguage.googleapis.com`) with the built-in `google_search`
grounding tool, using `gemini-2.5-flash` as the default model (pass a
different `model=` value in the function calls if you want to point at
another Gemini model that supports `google_search` grounding). Get a key at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey).

## Headline patterns (see the case study page for the full breakdown)

- **78/100 apps are self-serve** — a developer can get credentials today with
  no sales call. The other 22% split between fully sales-gated products
  (PitchBook, DealCloud, Gladly, Brex, Ramp) and platform-review gates
  (Google Ads, Meta Ads, LinkedIn Ads, Amazon SP-API).
- **OAuth2 (49%) and API keys (35%) cover 84% of all auth** — the two flows a
  toolkit generator needs to nail first.
- **71/100 are buildable as an agent toolkit today** with no blocker at all.
- **43/100 already have an MCP server** (28 official, 15 community) — nearly
  half the surface area doesn't need to be built from scratch, just wrapped
  or pointed at.
- Self-serve rate is **not evenly distributed**: Developer & Infra and
  Productivity & PM are 100% self-serve; AI/Research/Media is the worst
  category at 50%, mostly because meeting-intelligence and research tools
  gate their APIs behind Enterprise plans even when the product itself has a
  generous free consumer tier.
- The single most common blocker isn't payment — it's **"no public developer
  docs / fully sales-gated"** (7 of the ~14 blocked apps), followed by
  **platform review/approval gates** (5 apps: ad platforms + marketplaces).

## Known gaps (disclosed, not hidden)

- **Paygent Connect, Consensus**: no public developer documentation was found
  after multiple searches. Rather than invent an answer, both are marked
  `confidence: "low"` / `verdict: "blocked"` with an honest "not publicly
  found" evidence field.
- **MrScraper, higgsfield**: plausible from marketing pages but not
  independently re-verified against a developer reference this pass — flagged
  low confidence for a follow-up check rather than presented as certain.
- The 15-app verification sample is not the full 100 — it's weighted toward
  low/medium-confidence rows on purpose (that's where an LLM's untouched
  training-knowledge guess is most likely to be stale), so the reported
  "first pass 60% -> verified 100%" accuracy number describes that sample,
  not a claim that the whole dataset is 100% verified by hand.

## Repo layout

```
agent/
  research_agent.py     # stage 2: live research pass (Gemini + google_search grounding)
  verify_agent.py        # stage 3: adversarial verification pass
  analyze.py              # stage 4: pattern/cluster analysis (deterministic)
  push_to_composio.py      # stage 7 (optional): draft toolkits via Composio SDK
  seed_apps.json            # the 100-app input list
verification/
  verification_report.json   # sampled hand-verification, first-pass vs corrected
site/
  index.html                  # the single-page case study (open this)
  data/
  apps_100.json            # final research dataset (100 rows)
  analytics.json            # output of analyze.py
```