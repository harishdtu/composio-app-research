"""
analyze.py
Second stage of the pipeline: takes the raw per-app research (apps_100.json)
and clusters it into the patterns Composio actually cares about — this is
the part that turns 100 rows into a decision-making artifact instead of a
spreadsheet.

Run: python3 analyze.py > ../data/analytics.json
"""
import json
from collections import Counter, defaultdict

with open("../data/apps_100.json") as f:
    apps = json.load(f)

N = len(apps)

def pct(n):
    return round(100 * n / N, 1)

# --- Auth method distribution (an app can have multiple auth methods; we count primary = first listed) ---
primary_auth = Counter()
for a in apps:
    first = a["auth"][0]
    if "OAuth2" in first:
        key = "OAuth2"
    elif "API key" in first or "api key" in first.lower():
        key = "API key"
    elif "Basic" in first:
        key = "Basic auth"
    elif "Bearer" in first:
        key = "Bearer token"
    elif "none" in first.lower():
        key = "None (local tool)"
    elif "unknown" in first.lower():
        key = "Unknown / undisclosed"
    else:
        key = first
    primary_auth[key] += 1

# --- Access level distribution ---
access_dist = Counter(a["access"] for a in apps)

# --- Buildability verdict distribution ---
verdict_dist = Counter(a["verdict"] for a in apps)

# --- MCP availability ---
mcp_dist = Counter(a["mcp"] for a in apps)

# --- Access by category (self-serve % per category) ---
by_cat = defaultdict(list)
for a in apps:
    by_cat[a["category"]].append(a)

cat_selfserve_rate = {}
for cat, items in by_cat.items():
    ss = sum(1 for i in items if i["access"] == "self-serve")
    cat_selfserve_rate[cat] = {
        "total": len(items),
        "self_serve": ss,
        "self_serve_pct": round(100 * ss / len(items), 1),
        "gated": sum(1 for i in items if i["access"] == "gated"),
        "mixed": sum(1 for i in items if i["access"] == "mixed"),
        "ready_verdict": sum(1 for i in items if i["verdict"] == "ready"),
    }

# --- Blocker taxonomy: bucket the free-text blocker reasons ---
blocker_buckets = Counter()
for a in apps:
    b = a.get("blocker")
    if not b:
        continue
    bl = b.lower()
    if "developer token" in bl or "app review" in bl or "partner program" in bl or "review" in bl:
        blocker_buckets["Platform review / approval gate (OAuth app review, dev token, partner program)"] += 1
    elif "enterprise" in bl or "existing customer" in bl or "active" in bl and "account" in bl:
        blocker_buckets["Existing paid/enterprise account required"] += 1
    elif "paid plan" in bl or "paid subscription" in bl or "free-tier" in bl or "free tier" in bl:
        blocker_buckets["Paid-plan-only API (no free tier includes API access)"] += 1
    elif "no public" in bl or "not publicly" in bl or "could not locate" in bl or "no discoverable" in bl:
        blocker_buckets["No public developer docs / fully sales-gated"] += 1
    elif "local tool" in bl or "hosted endpoint" in bl or "cli" in bl.lower() or "self-hosted" in bl:
        blocker_buckets["Not a hosted API at all (CLI/local-only tool)"] += 1
    else:
        blocker_buckets["Other"] += 1

# --- Confidence distribution (verification signal) ---
confidence_dist = Counter(a["confidence"] for a in apps)

# --- MCP-ready apps (official or community) ---
mcp_ready_apps = [a["app"] for a in apps if a["mcp"] in ("official", "community")]

# --- "Easy win" list: self-serve + ready + high/medium confidence ---
easy_wins = [a["app"] for a in apps if a["access"] == "self-serve" and a["verdict"] == "ready"]

# --- "Needs outreach" list: gated + blocked ---
needs_outreach = [a["app"] for a in apps if a["access"] == "gated" and a["verdict"] == "blocked"]

output = {
    "total_apps": N,
    "primary_auth_distribution": dict(primary_auth.most_common()),
    "access_distribution": {k: {"count": v, "pct": pct(v)} for k, v in access_dist.most_common()},
    "verdict_distribution": {k: {"count": v, "pct": pct(v)} for k, v in verdict_dist.most_common()},
    "mcp_distribution": {k: {"count": v, "pct": pct(v)} for k, v in mcp_dist.most_common()},
    "confidence_distribution": {k: {"count": v, "pct": pct(v)} for k, v in confidence_dist.most_common()},
    "self_serve_rate_by_category": cat_selfserve_rate,
    "blocker_taxonomy": dict(blocker_buckets.most_common()),
    "mcp_ready_count": len(mcp_ready_apps),
    "mcp_ready_apps": mcp_ready_apps,
    "easy_win_count": len(easy_wins),
    "easy_wins": easy_wins,
    "needs_outreach_count": len(needs_outreach),
    "needs_outreach": needs_outreach,
}

print(json.dumps(output, indent=2))