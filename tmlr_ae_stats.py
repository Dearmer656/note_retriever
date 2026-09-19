#!/usr/bin/env python3
import csv
import json
from collections import defaultdict
import openreview

BASE = "https://api2.openreview.net"
VENUE = "TMLR"

def value(x):
    if isinstance(x, dict) and "value" in x:
        return x["value"]
    return x

def get_all_submissions():
    client = openreview.api.OpenReviewClient(baseurl=BASE)
    notes = client.get_all_notes(invitation=f"{VENUE}/-/Submission", details="replies")
    print(f"fetched {len(notes)} submissions", flush=True)
    return client, notes

def decision_of(note):
    replies = (note.details or {}).get("replies", [])
    decisions = []
    for reply in replies:
        invitations = reply.get("invitations", [])
        if any(str(inv).endswith("/Decision") for inv in invitations):
            rec = value(reply.get("content", {}).get("recommendation"))
            if rec:
                decisions.append((reply.get("cdate", 0) or 0, str(rec)))
    if not decisions:
        return None
    decisions.sort()
    return decisions[-1][1]

def classify(decision):
    if not decision:
        return None
    d = decision.strip().lower()
    if d.startswith("accept"):
        return "accept"
    if d.startswith("reject"):
        return "reject"
    return None

def ae_of(note):
    ae = value((note.content or {}).get("assigned_action_editor"))
    if not ae:
        return None
    return str(ae).split(",")[0].strip()

def profile_name(client, ae_id, cache):
    if ae_id in cache:
        return cache[ae_id]
    name = ae_id
    try:
        p = client.get_profile(ae_id)
        content = p.content or {}
        names = content.get("names", [])
        preferred = next((n for n in names if n.get("preferred")), None)
        preferred = preferred or (names[0] if names else None)
        if preferred:
            name = preferred.get("fullname") or preferred.get("username") or ae_id
    except Exception as e:
        print(f"profile lookup failed for {ae_id}: {e}", flush=True)
    cache[ae_id] = name
    return name

def main():
    client, notes = get_all_submissions()
    stats = defaultdict(lambda: {"accept": 0, "reject": 0, "other_decision": 0})
    missing_ae = 0
    no_decision = 0
    decision_labels = defaultdict(int)

    for note in notes:
        decision = decision_of(note)
        if not decision:
            no_decision += 1
            continue
        decision_labels[decision] += 1
        cls = classify(decision)
        ae = ae_of(note)
        if not ae:
            missing_ae += 1
            continue
        if cls in ("accept", "reject"):
            stats[ae][cls] += 1
        else:
            stats[ae]["other_decision"] += 1

    cache = {}
    rows = []
    for ae, s in stats.items():
        n = s["accept"] + s["reject"]
        rows.append({
            "ae_id": ae,
            "ae_name": profile_name(client, ae, cache),
            "accepted": s["accept"],
            "rejected": s["reject"],
            "decided_n": n,
            "accept_rate": (s["accept"] / n) if n else None,
            "other_decision": s["other_decision"],
        })

    rows.sort(key=lambda x: (-x["decided_n"], x["ae_name"]))
    fields = ["ae_id","ae_name","accepted","rejected","decided_n","accept_rate","other_decision"]
    with open("tmlr_ae_stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    summary = {
        "submissions_fetched": len(notes),
        "ae_rows": len(rows),
        "no_decision": no_decision,
        "decisions_missing_ae": missing_ae,
        "decision_labels": dict(sorted(decision_labels.items())),
    }
    with open("summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2), flush=True)
    print("\nTop AE rows:")
    for row in rows[:30]:
        print(row)

if __name__ == "__main__":
    main()
