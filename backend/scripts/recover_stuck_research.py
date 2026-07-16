#!/usr/bin/env python3
"""Mark stuck research as failed so user can re-run."""
import sqlite3
import sys
from datetime import datetime, timedelta

DB_PATH = "/root/workspace/ai-research-workspace/backend/storage/airw.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Find running research with last event > 5 min ago
    cur.execute("""
        SELECT r.id, r.title, r.status, r.created_at, r.updated_at,
               (SELECT MAX(ts) FROM timeline_events WHERE research_id = r.id) as last_event
        FROM researches r
        WHERE r.status = 'running'
    """)
    
    stuck = []
    for row in cur.fetchall():
        d = dict(row)
        if d['last_event']:
            last = datetime.fromisoformat(d['last_event'])
            idle = datetime.utcnow() - last
            if idle.total_seconds() > 300:  # 5 min
                d['idle_seconds'] = int(idle.total_seconds())
                stuck.append(d)
        else:
            # No events at all - probably died during task tree creation
            d['idle_seconds'] = None
            stuck.append(d)
    
    print(f"Found {len(stuck)} stuck research(es):")
    for s in stuck:
        title = s['title'][:40]
        idle = f"{s['idle_seconds']}s" if s['idle_seconds'] else "no events"
        print(f"  {s['id']} {title:40s} idle={idle}")
    
    if not stuck:
        print("Nothing to clean up.")
        return
    
    # Mark them as failed
    print(f"\nMarking {len(stuck)} research(es) as failed...")
    for s in stuck:
        cur.execute(
            "UPDATE researches SET status='failed', error_message=?, updated_at=? WHERE id=?",
            (f"自动恢复: 研究卡住超过 5 分钟（idle {s.get('idle_seconds', 'N/A')}s），已标记为 failed，请重新运行", datetime.utcnow().isoformat(), s['id'])
        )
    conn.commit()
    print(f"✓ Updated {len(stuck)} research(es)")
    conn.close()

if __name__ == "__main__":
    main()
