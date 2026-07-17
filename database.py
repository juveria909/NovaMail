import sqlite3
from contextlib import contextmanager
from datetime import datetime, UTC

DB_Path = "email_automation_campaign_agent.db"

def _now():
    return datetime.now(UTC).isoformat()

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'new',
    tags TEXT DEFAULT '',
    interests TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    preferred_hour INTEGER DEFAULT 10,
    preferred_day INTEGER,
    engagement_score REAL NOT NULL DEFAULT 0,
    last_contacted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    goal TEXT NOT NULL,
    tone TEXT NOT NULL,
    segment TEXT NOT NULL,
    num_variants INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    contact_id INTEGER,
    variant_label TEXT DEFAULT 'A',
    subject TEXT,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT DEFAULT '',
    scheduled_at TEXT,
    sent_at TEXT,
    opened INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT,
    clicked INTEGER NOT NULL DEFAULT 0,
    clicked_at TEXT,
    converted INTEGER NOT NULL DEFAULT 0,
    converted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_status
ON contacts(status);

CREATE INDEX IF NOT EXISTS idx_contacts_email
ON contacts(email);

CREATE INDEX IF NOT EXISTS idx_campaign_status
ON campaigns(status);

CREATE INDEX IF NOT EXISTS idx_campaign_email_campaign
ON campaign_emails(campaign_id);

CREATE INDEX IF NOT EXISTS idx_campaign_email_contact
ON campaign_emails(contact_id);

CREATE INDEX IF NOT EXISTS idx_campaign_email_status
ON campaign_emails(status);

CREATE INDEX IF NOT EXISTS idx_contacts_engagement
ON contacts(engagement_score);

"""

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_Path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_database():
    with get_conn() as conn:
        conn.executescript(SCHEMA)

def add_contact(name,email,status="new",tags="",interests="",notes="",preferred_hour=10,preferred_day=None):
    name = name.strip()
    email = email.strip().lower()
    if not name:
        raise ValueError("Name cannot be empty.")
    if not email:
        raise ValueError("Email cannot be empty.")
    now = _now()
    with get_conn() as conn:
        conn.execute (
            """INSERT INTO contacts (name,email,status,tags,interests,notes,preferred_hour,preferred_day,engagement_score,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,?,?) ON CONFLICT(email)
            DO UPDATE SET 
                name = excluded.name,
                status = excluded.status,
                tags = excluded.tags,
                interests = excluded.interests,
                notes = excluded.notes,
                preferred_hour = excluded.preferred_hour,
                preferred_day = excluded.preferred_day,
                updated_at = excluded.updated_at
            """,
            (name,email,status.lower(),tags,interests,notes,preferred_hour,preferred_day,now,now),
        )

def bulk_add_contacts(rows):
    added = 0
    failed = 0
    errors = []
    for i, row in enumerate(rows,start=1):
        try:
            add_contact(
                name = row.get("name", ""),
                email = row.get("email", ""),
                status = row.get("status", "new"),
                tags = row.get("tags", ""),
                interests = row.get("interests", ""),
                notes = row.get("notes", ""),
                preferred_hour = int(row.get("preferred_hour") or 10),
                preferred_day = row.get("preferred_day"),
            )
            added += 1
        except Exception as e:
            failed += 1
            errors.append(
                {
                    "row": i,
                    "email": row.get("email", ""),
                    "error": str(e),
                }
            )
    return {
        "added": added,
        "failed": failed,
        "errors": errors,
    }

def get_contact(contact_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE id = ?",
            (contact_id,),
        ).fetchone()
    return dict(row) if row else None

def get_contacts(segment = "ALL"):
    query = "SELECT * FROM contacts"
    params = ()
    if segment and segment != "ALL":
        if segment in ("new","active","inactive","high_value") :
            query += " WHERE status = ?"
            params = (segment,)
        else:
            query += " WHERE tags LIKE ?"
            params = (f"%{segment}%",)
    query += " ORDER BY created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(
            query,
            params,
        ).fetchall()
    return [dict(r) for r in rows]

def update_contact(contact_id, **kwargs):
    if not kwargs:
        return
    allowed = {"name","email","status","tags","interests","notes","preferred_hour","preferred_day",}
    fields = []
    values = []
    for key, value in kwargs.items():
        if key not in allowed:
            continue
        if key == "name" and isinstance(value, str):
            value = value.strip()
        if key == "email" and isinstance(value, str):
            value = value.strip().lower()
        if key == "status" and isinstance(value, str):
            value = value.strip().lower()
        fields.append(f"{key} = ?")
        values.append(value)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(contact_id)
    query = f"""UPDATE contacts SET {', '.join(fields)} WHERE id = ?"""
    with get_conn() as conn:
        conn.execute(query,values,)

def delete_contact(contact_id) :
    with get_conn() as conn :
        conn.execute("DELETE FROM contacts WHERE id = ?",(contact_id,))

def contact_count():
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM contacts"
        ).fetchone()["c"]
    
def all_tags() :
    with get_conn() as conn :
        rows = conn.execute("SELECT tags FROM contacts WHERE tags != '' ").fetchall()
    tags = set()
    for r in rows :
        for t in r["tags"].split(",") :
            t = t.strip()
            if t:
                tags.add(t)
    return sorted(tags)

def touch_last_contacted(contact_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE contacts SET last_contacted_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), contact_id),
        )

def update_contact_engagement(contact_id, opened=False, clicked=False, converted=False):
    delta = 0.0
    if opened:
        delta += 1.0
    if clicked:
        delta += 2.0
    if converted:
        delta += 5.0
    if delta == 0.0:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE contacts SET engagement_score = engagement_score + ?, updated_at = ? WHERE id = ?",
            (delta, _now(), contact_id),
        )

def update_preferred_send_time(contact_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT opened_at FROM campaign_emails
               WHERE contact_id = ? AND opened = 1 AND opened_at IS NOT NULL""",
            (contact_id,),
        ).fetchall()
        if not rows:
            return None
        hour_counts = {}
        for r in rows:
            try:
                hour = datetime.fromisoformat(r["opened_at"]).hour
            except ValueError:
                continue
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        if not hour_counts:
            return None
        best_hour = max(hour_counts, key=hour_counts.get)
        conn.execute(
            "UPDATE contacts SET preferred_hour = ?, updated_at = ? WHERE id = ?",
            (best_hour, _now(), contact_id),
        )
        return best_hour

def search_contacts(keyword) :
    keyword = (keyword or "").strip()
    with get_conn() as conn :
        rows = conn.execute(
            """SELECT * FROM contacts WHERE
            name LIKE ? OR email LIKE ? OR tags LIKE ? OR interests LIKE ?
            ORDER BY created_at DESC""",
            (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%",),
        ).fetchall()
    return [dict(r) for r in rows]

#---Campaigns---

def create_campaign(name,goal,tone,segment,num_variants=1) :
    name = name.strip()
    if not name:
        raise ValueError("Campaign name cannot be empty.")
    now = _now()
    with get_conn() as conn :
        curr = conn.execute(
            """INSERT INTO campaigns (name,goal,tone,segment,num_variants,status,created_at,updated_at)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)""",
            (name,goal,tone,segment,num_variants,now,now),
        )
        return curr.lastrowid

def get_campaigns() :
    with get_conn() as conn :
        return [dict(r) for r in conn.execute (
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        ).fetchall()]
    
def get_campaign(campaign_id) :
    with get_conn() as conn :
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if row:
            return dict(row)
        else:
            return None

def update_campaign(campaign_id, **kwargs):
    if not kwargs:
        return
    allowed = {"name","goal","tone","segment","num_variants","status",}
    fields = []
    values = []
    for key, value in kwargs.items():
        if key in allowed:
            fields.append(f"{key} = ?")
            values.append(value)
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(campaign_id)
    query = f"""UPDATE campaigns SET {', '.join(fields)} WHERE id = ?"""
    with get_conn() as conn:
        conn.execute(query, values)

def set_campaign_status(campaign_id, status):
    with get_conn() as conn:
        conn.execute("""UPDATE campaigns SET status = ?,updated_at = ? WHERE id = ?""",
            (status,_now(),campaign_id,),)
        
def delete_campaign(campaign_id):
    with get_conn() as conn:
        conn.execute("""DELETE FROM campaigns WHERE id = ? """,(campaign_id,),)

def campaign_count():
    with get_conn() as conn:
        return conn.execute("""SELECT COUNT(*) AS total FROM campaigns""").fetchone()["total"]
    
def campaigns_by_status(status):
    if not status:
        return []
    with get_conn() as conn:
        rows = conn.execute("""SELECT * FROM campaigns WHERE status = ? ORDER BY created_at DESC""",(status,),).fetchall()
    return [dict(r) for r in rows]

def search_campaigns(keyword):
    keyword = (keyword or "").strip()
    with get_conn() as conn:
        rows = conn.execute("""SELECT * FROM campaigns WHERE
                name LIKE ? OR goal LIKE ? OR tone LIKE ? OR segment LIKE ?
                ORDER BY created_at DESC""",
            (f"%{keyword}%",f"%{keyword}%",f"%{keyword}%",f"%{keyword}%",),).fetchall()
    return [dict(r) for r in rows]

def campaign_summary():
    with get_conn() as conn:
        row = conn.execute("""SELECT COUNT(*) AS total,
                SUM(CASE WHEN status='draft' THEN 1 ELSE 0 END) AS draft,
                SUM(CASE WHEN status='scheduled' THEN 1 ELSE 0 END) AS scheduled,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed
            FROM campaigns"""
        ).fetchone()
    return {
        "total": row["total"],
        "draft": row["draft"] or 0,
        "scheduled": row["scheduled"] or 0,
        "running": row["running"] or 0,
        "completed": row["completed"] or 0,
    }

#---Campaign Emails---

def add_campaign_email(campaign_id,contact_id,variant_label,subject,body,scheduled_at=None) :
    with get_conn() as conn :
        curr = conn.execute(
            """INSERT INTO campaign_emails (campaign_id,contact_id,variant_label,subject,body,status,scheduled_at,created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (campaign_id,contact_id,variant_label,subject,body,scheduled_at,_now()),
        )
        return curr.lastrowid
    
def update_email_contents(email_id,subject,body) :
    with get_conn() as conn :
        conn.execute(
            "UPDATE campaign_emails SET subject = ?, body = ? WHERE id = ?",
            (subject,body,email_id),
        )

def schedule_email(email_id,scheduled_at):
    with get_conn() as conn:
        conn.execute(
            """ UPDATE campaign_emails SET scheduled_at = ?, status = 'scheduled' WHERE id = ? """,
            (scheduled_at, email_id,),
        )

def get_due_emails(now=None):
    now = now or _now()
    with get_conn() as conn:
        rows = conn.execute(""" SELECT ce.*, c.name AS contact_name, c.email AS contact_email, c.interests, c.tags
                             FROM campaign_emails ce
                             LEFT JOIN contacts c ON ce.contact_id = c.id
                             WHERE ce.status
                             IN ('pending','scheduled')
                             AND
                             ( ce.scheduled_at IS NULL OR ce.scheduled_at <= ? )
                             ORDER BY ce.id """,
                             (now,), ).fetchall()
        return [dict(r) for r in rows]

def mark_sent(email_id) :
    with get_conn() as conn :
        conn.execute(
            "UPDATE campaign_emails SET status = 'sent', sent_at = ?, error = '' WHERE id = ?",
            (_now(),email_id),
        )
        row = conn.execute(
            "SELECT contact_id FROM campaign_emails WHERE id = ?", (email_id,)
        ).fetchone()
    if row and row["contact_id"] is not None:
        touch_last_contacted(row["contact_id"])

def mark_failed(email_id,error) :
    with get_conn() as conn :
        conn.execute(
            "UPDATE campaign_emails SET status = 'failed' , error = ? WHERE id = ?",
            (str(error)[:500],email_id),
        )

def mark_opened(email_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT contact_id, opened FROM campaign_emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            "UPDATE campaign_emails SET opened = 1, opened_at = COALESCE(opened_at, ?) WHERE id = ?",
            (_now(), email_id),
        )
    if not row["opened"] and row["contact_id"] is not None:
        update_contact_engagement(row["contact_id"], opened=True)

def mark_clicked(email_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT contact_id, clicked FROM campaign_emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            """UPDATE campaign_emails
               SET clicked = 1, clicked_at = COALESCE(clicked_at, ?),
                   opened = 1, opened_at = COALESCE(opened_at, ?)
               WHERE id = ?""",
            (_now(), _now(), email_id),
        )
    if not row["clicked"] and row["contact_id"] is not None:
        update_contact_engagement(row["contact_id"], clicked=True)

def mark_converted(email_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT contact_id, converted FROM campaign_emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not row:
            return
        conn.execute(
            "UPDATE campaign_emails SET converted = 1, converted_at = COALESCE(converted_at, ?) WHERE id = ?",
            (_now(), email_id),
        )
    if not row["converted"] and row["contact_id"] is not None:
        update_contact_engagement(row["contact_id"], converted=True)

def get_campaign_emails(campaign_id) :
    with get_conn() as conn :
        return [dict(r) for r in conn.execute(
            """SELECT ce.*, c.name as contact_name, c.email as contact_email
            FROM campaign_emails ce JOIN contacts c ON ce.contact_id = c.id
            WHERE ce.campaign_id = ? ORDER BY ce.id""",
            (campaign_id,)).fetchall()]

def search_emails(keyword):
    keyword = (keyword or "").strip()
    with get_conn() as conn:
        rows = conn.execute(""" SELECT ce.*, c.name, c.email FROM campaign_emails ce
                            LEFT JOIN contacts c ON ce.contact_id=c.id
                            WHERE subject LIKE ? OR body LIKE ? OR c.name LIKE ? OR c.email LIKE ? """,
                            ( f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%" ),
                            ).fetchall()
        return [dict(r) for r in rows]

def campaign_status(campaign_id) :
    with get_conn() as conn :
        row = conn.execute(
            """SELECT 
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN status ='sent' THEN 1 ELSE 0 END ),0) AS sent,
                    COALESCE(SUM(CASE WHEN status ='failed' THEN 1 ELSE 0 END ),0) AS failed,
                    COALESCE(SUM(CASE WHEN status IN ('pending','scheduled') THEN 1 ELSE 0 END),0) AS pending,
                    COALESCE(SUM(opened),0) AS opened,
                    COALESCE(SUM(clicked),0) AS clicked,
                    COALESCE(SUM(converted),0) AS converted
                FROM campaign_emails WHERE campaign_id = ?""",
            (campaign_id,)).fetchone()
        return dict(row)
    
def variant_performance(campaign_id):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                 variant_label,
                 COUNT(*) AS total,
                 COALESCE(SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END),0) AS sent,
                 COALESCE(SUM(opened),0) AS opened,
                 COALESCE(SUM(clicked),0) AS clicked,
                 COALESCE(SUM(converted),0) AS converted
               FROM campaign_emails
               WHERE campaign_id = ?
               GROUP BY variant_label
               ORDER BY variant_label""",
            (campaign_id,),
        ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        sent = d["sent"] or 0
        d["open_rate"] = round(d["opened"] / sent, 4) if sent else None
        d["click_rate"] = round(d["clicked"] / sent, 4) if sent else None
        d["conversion_rate"] = round(d["converted"] / sent, 4) if sent else None
        results.append(d)
    return results

def overall_stats() :
    with get_conn() as conn :
        row = conn.execute(
            """SELECT
                    COUNT(*) as total_emails,
                    COALESCE(SUM(CASE WHEN status ='sent' THEN 1 ELSE 0 END ),0) AS total_sent,
                    COALESCE(SUM(CASE WHEN status ='failed' THEN 1 ELSE 0 END),0) AS total_failed,
                    COALESCE(SUM(opened),0) AS total_opened,
                    COALESCE(SUM(clicked),0) AS total_clicked,
                    COALESCE(SUM(converted),0) AS total_converted
                FROM campaign_emails""").fetchone()
        return dict(row)
    
if __name__ == "__main__":
    init_database()
    print("Database initialized successfully.")