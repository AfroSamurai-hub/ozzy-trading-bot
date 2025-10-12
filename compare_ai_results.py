"""
Compare conservative AI vs ambitious AI outcomes from SQLite DB.
Shows daily summary side-by-side and a quick delta.
"""
import sqlite3
from datetime import datetime

DB = 'ozzy_simple.db'

def fetch_one(cur, q):
    cur.execute(q)
    return cur.fetchone()

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    print("\n=== Conservative AI (ai_analysis) - Today ===")
    cur.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN ai_recommendation='APPROVE' THEN 1 ELSE 0 END) as approvals,
               SUM(CASE WHEN ai_recommendation='REJECT' THEN 1 ELSE 0 END) as rejections,
               SUM(CASE WHEN ai_recommendation='MODIFY' THEN 1 ELSE 0 END) as modifies,
               ROUND(AVG(ai_confidence),1) as avg_conf
        FROM ai_analysis
        WHERE DATE(timestamp)=DATE('now')
        """
    )
    cons = cur.fetchone() or (0,0,0,0,0)
    c_total, c_app, c_rej, c_mod, c_avg = cons
    c_rate = (c_app / c_total * 100.0) if c_total else 0.0
    print(f"Analyzed: {c_total} | Approve: {c_app} ({c_rate:.1f}%) | Modify: {c_mod} | Reject: {c_rej} | Avg conf: {c_avg}")

    print("\n=== Ambitious AI (ai_agent_analysis) - Today ===")
    cur.execute(
        """
        SELECT COUNT(*) as total,
               SUM(CASE WHEN ai_action='APPROVE' THEN 1 ELSE 0 END) as approvals,
               SUM(CASE WHEN ai_action='IMPROVE' THEN 1 ELSE 0 END) as improves,
               SUM(CASE WHEN ai_action='CHALLENGE' THEN 1 ELSE 0 END) as challenges,
               SUM(CASE WHEN ai_action='REJECT' THEN 1 ELSE 0 END) as rejections,
               SUM(CASE WHEN ai_action='COUNTER' THEN 1 ELSE 0 END) as counters,
               ROUND(AVG(ai_confidence),1) as avg_conf,
               ROUND(AVG(opportunity_score),1) as avg_opp,
               ROUND(AVG(alignment_with_goals),1) as avg_goal
        FROM ai_agent_analysis
        WHERE DATE(timestamp)=DATE('now')
        """
    )
    amb = cur.fetchone()
    if not amb:
        amb = (0, 0, 0, 0, 0, 0, None, None, None)
    a_total = amb[0] or 0
    a_app = amb[1] or 0
    a_imp = amb[2] or 0
    a_chal = amb[3] or 0
    a_rej = amb[4] or 0
    a_cnt = amb[5] or 0
    a_avg = amb[6]
    a_opp = amb[7]
    a_goal = amb[8]
    a_rate = (a_app / a_total * 100.0) if a_total else 0.0
    print(
        "Analyzed: {} | Approve: {} ({:.1f}%) | Improve: {} | Challenge: {} | Reject: {} | Counter: {} | Avg conf: {} | Avg opp: {} | Goal: {}".format(
            a_total, a_app, a_rate, a_imp, a_chal, a_rej, a_cnt, a_avg, a_opp, a_goal
        )
    )

    print("\n=== Delta (Ambitious - Conservative) ===")
    print(f"Approvals: {int(a_app) - int(c_app)} | Approval rate: {a_rate - c_rate:.1f} pp | Analyses: {int(a_total) - int(c_total)}")

    print("\nTip: run this again later today to see how approval rate climbs with ambitious AI.")

if __name__ == '__main__':
    main()
