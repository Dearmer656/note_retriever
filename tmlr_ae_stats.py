#!/usr/bin/env python3
import csv, json, time, requests
from collections import defaultdict

BASE="https://api2.openreview.net"
S=requests.Session()
S.headers.update({
 "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153.0 Safari/537.36",
 "Accept":"application/json,text/plain,*/*",
 "Referer":"https://openreview.net/"
})

def val(x):
    return x.get("value") if isinstance(x,dict) and "value" in x else x

def fetch_all():
    out=[]; offset=0; limit=25
    while True:
        r=S.get(BASE+"/notes",params={
            "invitation":"TMLR/-/Submission",
            "details":"replies",
            "limit":limit,
            "offset":offset,
            "sort":"id"
        },timeout=60)
        print("GET",offset,r.status_code,flush=True)
        if r.status_code!=200:
            print(r.text[:2000],flush=True); r.raise_for_status()
        batch=r.json().get("notes",[])
        out.extend(batch)
        if len(batch)<limit: break
        offset += len(batch)
        time.sleep(0.5)
    return out

def decision(note):
    ds=[]
    for rep in note.get("details",{}).get("replies",[]):
        invs=rep.get("invitations",[])
        if any(str(i).endswith("/Decision") for i in invs):
            rec=val(rep.get("content",{}).get("recommendation"))
            if rec: ds.append((rep.get("cdate") or 0,str(rec)))
    return sorted(ds)[-1][1] if ds else None

def classify(d):
    if not d:return None
    x=d.lower().strip()
    if x.startswith("accept"):return "accept"
    if x.startswith("reject"):return "reject"
    return None

def main():
    notes=fetch_all()
    stats=defaultdict(lambda:{"accepted":0,"rejected":0})
    missing=0
    for n in notes:
        d=decision(n); c=classify(d)
        if not c: continue
        ae=val(n.get("content",{}).get("assigned_action_editor"))
        if not ae:
            missing+=1; continue
        ae=str(ae).split(",")[0].strip()
        stats[ae]["accepted" if c=="accept" else "rejected"]+=1
    rows=[]
    for ae,s in stats.items():
        N=s["accepted"]+s["rejected"]
        rows.append({"ae_id":ae,**s,"decided_n":N,"accept_rate":s["accepted"]/N if N else None})
    rows.sort(key=lambda r:(-r["decided_n"],r["ae_id"]))
    with open("tmlr_ae_stats.csv","w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=["ae_id","accepted","rejected","decided_n","accept_rate"])
        w.writeheader();w.writerows(rows)
    summary={"submissions":len(notes),"aes":len(rows),"decided_missing_ae":missing}
    with open("summary.json","w") as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary),flush=True)
    print(open("tmlr_ae_stats.csv").read(),flush=True)
if __name__=="__main__":main()
