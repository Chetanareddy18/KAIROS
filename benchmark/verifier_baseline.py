"""Baseline for the LLM-Modulo verifier: the earlier tolerance rule (accept a number within 2% of a fact
or with the same integer part), replayed on the same 200 corrupted numbers as evaluate_models.py (D).

    python benchmark/verifier_baseline.py
"""
import sys, os, re, random, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark.evaluate_models import *
rep = NLReporterAgent(); rng = random.Random(7)
caught=n=rok=rn=0
for s in range(1,6):
    tmp=tempfile.mkdtemp(); db=Database(os.path.join(tmp,"v.duckdb")); df=generate(PERIODS,seed=s,end=END)
    c=DataCollectorAgent(db)
    for src,part in df.groupby("source"): c.ingest_dataframe(src,part[["metric_name","value","timestamp"]])
    w=AnomalyWatchmanAgent(db,use_prophet=False); w.detect(); recent=w.recent(24)
    inv=CausalInvestigatorAgent(db,bootstrap=0).investigate(recent)
    top=rep._top_anomalies(recent); allowed=rep._allowed_numbers(top,inv.root_causes,len(recent))
    text=rep._template(top,inv.root_causes,inv.origins,len(recent))
    vals=[float(x) for x in allowed]
    def old_ok(v): return any(abs(v-a)<=0.02*max(abs(a),1e-9) or int(v)==int(a) for a in vals)
    nums=list(re.finditer(r"\d[\d,]*\.\d+",text))
    for _ in range(40):
        m=rng.choice(nums); val=float(m.group(0).replace(",",""))
        bad=val*rng.choice([0.5,0.7,1.3,1.6,2.5])+rng.choice([1.0,3.0,7.0])
        n+=1; caught+= not old_ok(round(bad,2))
        rn+=1; rok+= old_ok(round(val,1))
    known={a.metric_name for a in recent}|{m for rc in inv.root_causes for m in rc.path}; names=sorted(known)
    for _ in range(10):
        real=rng.choice([q for q in names if q in text] or names); rng.choice(FAKE_METRICS)
    db.close()
print("old rule caught", caught/n, "rounding accepted", rok/rn, n)
