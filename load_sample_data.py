"""Load two weeks of synthetic multi-source metrics (known causal structure + incidents) into DuckDB.

Same data as the dashboard's "Load demo data" button / POST /api/v1/dev/seed.
Run with the API stopped (DuckDB allows one writer process), then start KAIROS and run the pipeline.
"""
from backend.agents.data_collector import DataCollectorAgent
from backend.config import settings
from backend.db import Database
from backend.demo.synthetic import generate

db = Database(settings.db_path)
collector = DataCollectorAgent(db)
df = generate()
for source, part in df.groupby("source"):
    if collector.get_source(source) is None:
        collector.upsert_source(source, "push", {}, description="synthetic demo source", managed_by="demo")
    collector.ingest_dataframe(source, part[["metric_name", "value", "timestamp"]])
db.close()

print(f"Loaded {len(df):,} rows: {df['metric_name'].nunique()} metrics from {df['source'].nunique()} sources "
      f"into {settings.db_path}")
print("Start the API (uvicorn backend.main:app) and click 'Run pipeline now' on the dashboard.")
