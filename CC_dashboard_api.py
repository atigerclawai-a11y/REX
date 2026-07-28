#!/usr/bin/env python3
"""
CC_dashboard_api.py — GOJ Command Center API
Called by n8n webhook to return dashboard data as JSON.
Usage: python3 CC_dashboard_api.py [action]
  action: overview|auths|billing|attendance|drivers|kitchen|plans|progress
  default: overview
"""
import sqlite3, json, sys, os
from datetime import date, datetime
from pathlib import Path

DB = Path.home() / "Documents" / "goj files" / "dashboard" / "auth_tracker.db"
DAY_COLS = {"M": "day_M_actual","T": "day_T_actual","W": "day_W_actual",
            "TH": "day_TH_actual","F": "day_F_actual","Su": "day_Su_actual"}
DAY_NAMES = {"M":"Monday","T":"Tuesday","W":"Wednesday","TH":"Thursday","F":"Friday","Su":"Sunday"}

def q(sql, params=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def overview():
    today = date.today()
    goj_map = {"Mon":"M","Tue":"T","Wed":"W","Thu":"TH","Fri":"F","Sat":"M","Sun":"Su"}
    gd = goj_map.get(today.strftime("%a"), "M")
    dc = DAY_COLS.get(gd, "day_M_actual")

    total = q("SELECT COUNT(*) as c FROM clients")[0]["c"]
    active = q("SELECT COUNT(*) as c FROM clients WHERE active=1")[0]["c"]
    s1 = q(f"SELECT COUNT(*) as c FROM clients WHERE {dc}=1")[0]["c"]
    s2 = q(f"SELECT COUNT(*) as c FROM clients WHERE {dc}=2")[0]["c"]
    tr = q(f"SELECT COUNT(*) as c FROM clients WHERE {dc} IN (1,2) AND transportation='TR'")[0]["c"]
    aa = q("SELECT COUNT(*) as c FROM authorization WHERE service_end_date >= date('now') AND status='ACTIVE'")[0]["c"]
    ae = q("SELECT COUNT(*) as c FROM authorization WHERE service_end_date BETWEEN date('now') AND date('now','+30 days') AND status='ACTIVE'")[0]["c"]

    plans = q("SELECT plan_canonical, COUNT(*) as c FROM clients WHERE active=1 GROUP BY plan_canonical ORDER BY c DESC")

    return {
        "action": "overview", "date": today.isoformat(), "day": DAY_NAMES.get(gd,"Unknown"),
        "clients": {"total":total,"active":active},
        "today": {"shift1":s1,"shift2":s2,"total":s1+s2,"transport":tr},
        "auths": {"active":aa,"expiring":ae},
        "plans": plans,
        "timestamp": datetime.now().isoformat()
    }

def auths():
    rows = q("""
        SELECT a.client_name, a.payer_canonical as plan, a.service_end_date as expires,
               a.authorization_number, a.status, c.transportation,
               CAST(julianday(a.service_end_date) - julianday('now') AS INTEGER) as days_left
        FROM authorization a LEFT JOIN clients c ON c.name=a.client_name
        WHERE a.service_end_date >= date('now','-30 days')
        ORDER BY a.service_end_date LIMIT 200
    """)
    return {"action":"auths","count":len(rows),"auths":rows,"timestamp":datetime.now().isoformat()}

def billing():
    # Read claims_837 table for this week
    claims = q("SELECT * FROM claims_837 ORDER BY created_at DESC LIMIT 100")
    payments = q("SELECT * FROM payments_835 ORDER BY received_at DESC LIMIT 100")
    return {"action":"billing","claims_count":len(claims),"payments_count":len(payments),
            "claims":claims,"payments":payments,"timestamp":datetime.now().isoformat()}

def attendance():
    rows = q("""
        SELECT client_name, log_date, shift, status
        FROM attendance_log WHERE log_date >= date('now','-7 days')
        ORDER BY log_date DESC, shift LIMIT 500
    """)
    return {"action":"attendance","count":len(rows),"records":rows,"timestamp":datetime.now().isoformat()}

def drivers():
    today = date.today()
    goj_map = {"Mon":"M","Tue":"T","Wed":"W","Thu":"TH","Fri":"F","Sat":"M","Sun":"Su"}
    gd = goj_map.get(today.strftime("%a"), "M")
    dc = DAY_COLS.get(gd, "day_M_actual")
    rows = q(f"""
        SELECT name, {dc} as shift, transportation, driver_override, address
        FROM clients WHERE {dc} IN (1,2) AND transportation='TR'
        ORDER BY name
    """)
    return {"action":"drivers","count":len(rows),"drivers":rows,"timestamp":datetime.now().isoformat()}

def kitchen():
    today = date.today()
    goj_map = {"Mon":"M","Tue":"T","Wed":"W","Thu":"TH","Fri":"F","Sat":"M","Sun":"Su"}
    gd = goj_map.get(today.strftime("%a"), "M")
    dc = DAY_COLS.get(gd, "day_M_actual")
    s1 = q(f"SELECT COUNT(*) as c FROM clients WHERE {dc}=1")[0]["c"]
    s2 = q(f"SELECT COUNT(*) as c FROM clients WHERE {dc}=2")[0]["c"]
    flags = q(f"SELECT dietary_flags, COUNT(*) as c FROM clients WHERE {dc} IN (1,2) AND dietary_flags IS NOT NULL AND dietary_flags!='' GROUP BY dietary_flags")
    return {"action":"kitchen","shift1_meals":s1,"shift2_meals":s2,"dietary":flags,"timestamp":datetime.now().isoformat()}

def plans():
    rows = q("SELECT plan_canonical, COUNT(*) as c FROM clients WHERE active=1 GROUP BY plan_canonical ORDER BY c DESC")
    return {"action":"plans","plans":rows,"timestamp":datetime.now().isoformat()}

def progress():
    return {
        "action": "progress",
        "phases": [
            {"id":"p0","name":"Progress Tracker","status":"done"},
            {"id":"p1","name":"n8n Dashboard API Workflow","status":"done"},
            {"id":"p2","name":"Authorization War Room (Gantt)","status":"in_progress"},
            {"id":"p3","name":"Live Attendance Panel","status":"pending"},
            {"id":"p4","name":"Billing Pipeline Panel","status":"pending"},
            {"id":"p5","name":"Payer Scorecard + Schedule","status":"pending"},
            {"id":"p6","name":"Anomaly Detection + Voice","status":"pending"},
            {"id":"p7","name":"Compliance Shield","status":"pending"},
            {"id":"p8","name":"Emergency Response","status":"pending"},
            {"id":"p9","name":"Family Portal Preview","status":"pending"},
            {"id":"p10","name":"Kitchen Command Center","status":"pending"},
            {"id":"p11","name":"Fleet Command (Drivers)","status":"pending"},
            {"id":"p12","name":"Document Intelligence Hub","status":"pending"},
            {"id":"p13","name":"Mobile Field Ops","status":"pending"},
            {"id":"p14","name":"Voice Command Center","status":"pending"},
        ],
        "built_at": datetime.now().isoformat()
    }

ACTIONS = {"overview":overview,"auths":auths,"billing":billing,"attendance":attendance,
           "drivers":drivers,"kitchen":kitchen,"plans":plans,"progress":progress}

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "overview"
    fn = ACTIONS.get(action, overview)
    result = fn()
    print(json.dumps(result, default=str))
