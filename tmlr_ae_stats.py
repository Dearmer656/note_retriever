#!/usr/bin/env python3
import csv
import json
import time
from collections import defaultdict
import requests

BASE = "https://api2.openreview.net"
VENUE = "TMLR"

def get_all_submissions():
    out = []
    offset = 0
    limit = 1000
    sess = requests.Session()
    while True:
        r = sess.get(
            f"{BASE}/notes",
            params={
                "invitation": f"{VENUE}/-/Submission",
                "details": "replies",
                "limit": limit,
                "offset": offset,
            },
            timeout=120,
        )
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("notes", [])
        out.extend(batch)
        print(f"fetched {len(out)} submissions", flush=True)
        if len(batch) < limit:
            break
        offset += len(batch)
        time.sleep(0.2)
    return out

def value(x):
    if isinstance(x, dict) and "value" in x:
        return x["value"]
    return x

def decision_of(note):
    replies = note.get("details", {}).get("replies", [])
    # Some API responses use directReplies instead.
    if not replies:
        replies = note.get("details", {}).get("directReplies", [])
    decisions = []
    for reply in replies:
        invitations = reply.get("invitations", [])
        invitation = reply.get("invitation")
        if invitation:
            invitations = list(invitations) + [invitation]
        if any(str(inv).endswith("/Decision") for inv in invitations):
            c = reply.get("content", {})
            rec = value(c.get("recommendation"))
            if rec:
                decisions.append((reply.get("cdate", 0), str(rec)))
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
    c = note.get("content", {})
    ae = value(c.get("assigned_action_editor"))
    if not ae:
        return None
    # Historical journal code sometimes stores comma-separated IDs.
    return str(ae).split(",")[0].strip()

def profile_name(ae_id, sess, cache):
    if ae_id in cache:
        return cache[ae_id]
    name = ae_id
    try:
        r = sess.get(f"{BASE}/profiles", params={"id": ae_id}, timeout=30)
        if r.ok:
            ps = r.json().get("profiles", [])
            if ps:
                p = ps[0]
                content = p.get("content", {})
                names = content.get("names", [])
                preferred = None
                for n in names:
                    if n.get("preferred"):
                        preferred = n
                        break
                preferred = preferred or (names[0] if names else None)
                if preferred:
                    name = preferred.get("fullname") or preferred.get("username") or ae_id
    except Exception as e:
        print(f"profile lookup failed for {ae_id}: {e}", flush=True)
    cache[ae_id] = name
    return name

def main():
    notes = get_all_submissions()
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

    sess = requests.Session()
    cache = {}
    rows = []
    for ae, s in stats.items():
        n = s["accept"] + s["reject"]
        ar = s["accept"] / n if n else None
        rows.append({
            "ae_id": ae,
            "ae_name": profile_name(ae, sess, cache),
            "accepted": s["accept"],
            "rejected": s["reject"],
            "decided_n": n,
            "accept_rate": ar,
            "other_decision": s["other_decision"],
        })

    rows.sort(key=lambda x: (-x["decided_n"], x["ae_name"]))
    with open("tmlr_ae_stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "ae_id","ae_name","accepted","rejected","decided_n","accept_rate","other_decision"
        ])
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
    for row in rows[:20]:
        print(row)

if __name__ == "__main__":
    main()
