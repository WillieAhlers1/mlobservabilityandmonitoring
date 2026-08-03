"""Audit live DB content for data schema investigation."""
import sqlite3
import json
from config_loader import config

conn = sqlite3.connect(config.db_path)
conn.row_factory = sqlite3.Row

# 1. Entity metadata
print("=" * 60)
print("ENTITY REGISTRY - Sample entries with metadata")
print("=" * 60)
rows = conn.execute("SELECT entity_id, name, entity_type, status, metadata FROM entity_registry LIMIT 4").fetchall()
for r in rows:
    eid = r["entity_id"]
    print(f"\n{eid} ({r['entity_type']}): {r['name']}")
    print(f"  status: {r['status']}")
    meta = json.loads(r["metadata"]) if r["metadata"] else {}
    print(f"  metadata keys: {list(meta.keys())}")
    print(f"  metadata: {json.dumps(meta, indent=4)}")

# 2. Table row counts
print("\n" + "=" * 60)
print("TABLE ROW COUNTS")
print("=" * 60)
tables = ['metric_timeseries', 'metric_timeseries_agg', 'drift_snapshots',
           'cohort_metrics', 'feature_importance', 'data_quality',
           'agent_traces', 'agent_trace_steps', 'alerts', 'lineage_events', 'projects']
for table in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {count}")

# 3. Sample metric_timeseries
print("\n" + "=" * 60)
print("METRIC_TIMESERIES - distinct metric names per entity type")
print("=" * 60)
for etype in ['model', 'agent']:
    rows = conn.execute("""
        SELECT DISTINCT mt.metric_name FROM metric_timeseries mt
        JOIN entity_registry er ON mt.entity_id = er.entity_id
        WHERE er.entity_type = ?
    """, (etype,)).fetchall()
    print(f"  {etype} metrics: {[r['metric_name'] for r in rows]}")

# 4. Sample alerts
print("\n" + "=" * 60)
print("ALERTS - Sample (first 3)")
print("=" * 60)
alerts = conn.execute("SELECT * FROM alerts LIMIT 3").fetchall()
for a in alerts:
    print(f"  id={a['id']}, entity_id={a['entity_id']}, type={a['alert_type']}, severity={a['severity']}")
    print(f"    title={a['title']}, resolved={a['resolved']}")

# 5. Projects
print("\n" + "=" * 60)
print("PROJECTS")
print("=" * 60)
projects = conn.execute("SELECT * FROM projects").fetchall()
for p in projects:
    print(f"  {p['id']}: name={p['name']}, owner={p['owner']}, status={p['status']}")

# 6. Lineage events sample
print("\n" + "=" * 60)
print("LINEAGE_EVENTS - Sample (first 3)")
print("=" * 60)
rows = conn.execute("SELECT * FROM lineage_events LIMIT 3").fetchall()
for r in rows:
    print(f"  entity={r['entity_id']}, version={r['version']}, trigger={r['trigger']}")
    meta = json.loads(r["metadata"]) if r["metadata"] else {}
    print(f"    metadata: {json.dumps(meta)}")

# 7. Agent traces sample
print("\n" + "=" * 60)
print("AGENT_TRACES - Sample (first 2)")
print("=" * 60)
rows = conn.execute("SELECT * FROM agent_traces LIMIT 2").fetchall()
for r in rows:
    print(f"  trace_id={r['trace_id']}, entity_id={r['entity_id']}")
    print(f"    query={r['query'][:60]}...")
    print(f"    voice_score={r['voice_score']}, policy_pass={r['policy_pass']}, total_latency={r['total_latency']}")

# 8. Data quality sample
print("\n" + "=" * 60)
print("DATA_QUALITY - Sample (first 3)")
print("=" * 60)
rows = conn.execute("SELECT * FROM data_quality LIMIT 3").fetchall()
for r in rows:
    print(f"  entity={r['entity_id']}, feature={r['feature']}, missing={r['missing_rate']}, outlier={r['outlier_rate']}, row_count={r['row_count']}")

conn.close()
