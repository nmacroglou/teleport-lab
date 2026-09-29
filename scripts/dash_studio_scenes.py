#!/usr/bin/env python3
"""Dashboard Studio versions of the four demo scenes (onboarding, auditor, AI agent, security).
Writes tp_studio_onboarding/auditor/agent/security.xml (new files; Simple XML scenes untouched)."""
import os, json, re
import dash_studio_identity as I
from dash_studio_identity import (PRELUDE, BG, PANEL, GREEN, RED, AMBER, BLUE, PURPLE, TEAL, GREY, TR, kpi, text, bar, card, blk, tok, tokv, CLS_BG)

UI = os.path.join(I.HERE, '..', 'splunk/apps/teleport_lab/default/data/ui/views')
X0, W, G = 40, 1840, 22
def cols(n): return (W - (n - 1) * G) // n
def chain(q, ext="ds_base"): return {"type": "ds.chain", "options": {"extend": ext, "query": q}}
def spark(cond, ext="ds_base"):
    c = 'count(eval(%s))' % cond
    return chain('| eventstats %s as total | timechart span=1d %s as events, first(total) as total | eventstats max(total) as total' % (c, c), ext)
def plain(q, ext="ds_base"): return chain(q, ext)
def pk(ds_id, title, color, unit=None, alert=None):
    v = kpi(ds_id, title, color, unit=unit)
    if alert:
        v["options"]["majorColor"] = "> majorValue | rangeValue(majorColorCfg)"
        v["context"] = {"majorColorCfg": [{"to": 1, "value": GREEN}, {"from": 1, "value": alert}]}
    return v
def plainkpi(ds_id, title, color, unit=None):
    o = {"majorColor": color, "sparklineDisplay": "off", "trendDisplay": "off", "backgroundColor": PANEL, "majorFontSize": 56}
    if unit: o["unit"] = unit
    return {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": ds_id}, "options": o}
def mtable(ds_id, title, count=6, colcol=None, colors=None, handlers=None):
    v = {"type": "splunk.table", "title": title, "dataSources": {"primary": ds_id},
         "options": {"count": count, "backgroundColor": PANEL, "dataOverlayMode": "none", "showRowNumbers": False, "wrap": True}}
    if colcol:
        v["options"]["columnFormat"] = {colcol: {"rowBackgroundColors": "> table | seriesByName(\"%s\") | matchValue(%sBg)" % (colcol, colcol)}}
        v["context"] = {colcol + "Bg": [{"match": k, "value": c} for k, c in colors.items()]}
    if handlers: v["eventHandlers"] = handlers
    return v
def col(ds_id, title, colors=None, stack=True, kind="splunk.column"):
    o = {"backgroundColor": PANEL, "legendDisplay": "bottom"}
    if stack: o["stackMode"] = "stacked"
    if colors: o["seriesColorsByField"] = colors
    return {"type": kind, "title": title, "dataSources": {"primary": ds_id}, "options": o}
INP_T = I.definition["inputs"]["input_time"]; INP_S = I.definition["inputs"]["input_src"]
def itext(title, token, default="*"): return {"type": "input.text", "title": title, "options": {"token": token, "defaultValue": default}}

def page(slug, title, desc, accent, h1, h2, inputs, ds, viz, structure, height, tokens=None):
    viz = dict(viz); viz["v_bar"] = bar(accent); viz["v_h1"] = text(h1, 34, "#FFFFFF", True); viz["v_h2"] = text(h2, 17, "#9FB3CC")
    structure = [blk("v_bar", X0, 30, 10, 86), blk("v_h1", X0 + 28, 24, 1750, 56), blk("v_h2", X0 + 28, 82, 1750, 34)] + structure
    ins = {"input_time": INP_T, "input_src": INP_S}; ins.update(inputs)
    d = {"title": title, "description": desc, "inputs": ins,
         "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}}}},
                      **({"tokens": {"default": {k: {"value": v} for k, v in tokens.items()}}} if tokens else {})},
         "dataSources": ds, "visualizations": viz,
         "layout": {"type": "absolute", "options": {"width": 1920, "height": height, "display": "auto-scale", "backgroundColor": BG},
                    "structure": structure, "globalInputs": list(ins.keys())}}
    js = json.dumps(d, indent=2, ensure_ascii=False); assert ']]>' not in js
    open(os.path.join(UI, slug + '.xml'), 'w', encoding='utf-8').write(
        '<dashboard version="2" theme="dark">\n  <label>%s</label>\n  <description>%s</description>\n  <definition><![CDATA[\n%s\n]]></definition>\n'
        '  <meta type="hiddenElements"><![CDATA[{"hideEdit": false, "hideOpenInSearch": false, "hideExport": false}]]></meta>\n</dashboard>\n' % (title, desc, js))
    print('wrote', slug)
def label(vid, t, color, x, y, w): return {vid: text(t, 20, color, True)}, [blk(vid, x, y, w, 36)]
def BASE(extra=''): return {"ds_base": {"type": "ds.search", "options": {"query": PRELUDE + extra, "queryParameters": TR}, "name": "base"}}

# ================= 1. ONBOARDING =================
ONB = '''| eval subject=if(in(event,"user.create","reset_password_token.create"), name, actor)
| eventstats count(eval(event="user.create")) as is_new by subject
| where is_new>0 AND subject!="bot-terraform"
| search subject="$newhire$"'''
STEP = '''| eval step=case(event="user.create","1 Account created (as code)",event="reset_password_token.create","2 Invite issued",event="mfa.add","3 MFA enrolled",event="user.login","4 First login",event="cert.create","5 Short-lived certificate issued",event="session.start","6 SSH access",event="db.session.start","6 Database access",event="app.session.start","6 App access")'''
ds = BASE(); ds["ds_onb"] = chain(ONB)
ds["k1"] = chain('| eventstats dc(subject) as total | timechart span=1d dc(subject) as events, first(total) as total | eventstats max(total) as total', "ds_onb")
ds["k2"] = plain('| stats min(eval(if(event="user.create",_time,null()))) as created, min(eval(if(in(event,"session.start","db.session.start","app.session.start"),_time,null()))) as first_access by subject | eval minutes=round((first_access-created)/60,1) | stats avg(minutes) as m | eval m=round(m,1) | fields m', "ds_onb")
ds["k3"] = plain('| search event="user.login" success="true" | stats count(eval(isnotnull(mfa_device))) as w, count as t | eval pct=if(t>0,round(w/t*100,0),0) | fields pct', "ds_base")
ds["t1"] = chain('| where in(event,"user.create","reset_password_token.create","mfa.add","user.login","cert.create","session.start","db.session.start","app.session.start") ' + STEP + ' | where isnotnull(step) | sort 0 subject _time | eval time=strftime(_time,"%Y-%m-%d %H:%M") | table time subject step outcome', "ds_onb")
ds["p1"] = chain('| search event="cert.create" | rename "identity.roles{}" as role | stats count by role', "ds_base")
ds["t2"] = chain('| search event IN ("role.created","user.create","user.update") | sort - _time | eval when=strftime(_time,"%Y-%m-%d %H:%M"), by=actor | table when by event name roles', "ds_base")
v = {"v_k1": pk("k1", "NEW ENGINEERS ONBOARDED", BLUE), "v_k2": plainkpi("k2", "MINUTES: ACCOUNT TO FIRST ACCESS", AMBER, "min"), "v_k3": plainkpi("k3", "LOGINS PROTECTED BY MFA", GREEN, "%"),
     "v_t1": mtable("t1", "The journey, step by step", 8, "outcome", {"allowed": "#1F6B4A", "denied": "#7A2B27"}),
     "v_p1": {"type": "splunk.pie", "title": "Roles handed out (certificates by role)", "dataSources": {"primary": "p1"}, "options": {"backgroundColor": PANEL, "showDonutHole": True, "collapseThreshold": 0}},
     "v_t2": mtable("t2", "Access as code: role and user changes", 6),
     "v_o1": card("### The old way\n1. Open a ticket\n2. Wait for someone to create keys or certificates\n3. Copy files to the laptop and keep them safe forever\n4. Ask again for each new system"),
     "v_o2": card("### The Teleport way\n1. Account and role created **as code** (Terraform or the Kubernetes operator)\n2. Engineer logs in once with SSO and MFA\n3. A short-lived certificate is issued automatically\n4. Access matches the role; every session is audited")}
s = []; k = cols(3)
s += [blk("v_k%d" % (i + 1), X0 + i * (k + G), 140, k, 190) for i in range(3)]
for vid, t, c, x, w in [("v_c1", "①  The journey: no account to working access", BLUE, X0, 1100), ("v_c2", "②  Which roles were handed out", PURPLE, X0 + 1100 + G, W - 1100 - G)]:
    d, b = label(vid, t, c, x, 350, w); v.update(d); s += b
s += [blk("v_t1", X0, 392, 1100, 400), blk("v_p1", X0 + 1100 + G, 392, W - 1100 - G, 400)]
d, b = label("v_c3", "③  Old way vs Teleport way, and the trail it leaves", GREEN, X0, 820, W); v.update(d); s += b
t3 = cols(3); s += [blk("v_t2", X0, 862, t3, 320), blk("v_o1", X0 + t3 + G, 862, t3, 320), blk("v_o2", X0 + 2 * (t3 + G), 862, t3, 320)]
page("tp_studio_onboarding", "1 · Day-One Onboarding (Studio)", "A new engineer goes from no account to working access.", BLUE,
     "Scene 1: day-one onboarding. No ticket queue, no certificate files.", "A new engineer goes from nothing to working access in minutes, with short-lived certificates and a full audit trail.",
     {"input_hire": itext("New hire (name or *)", "newhire")}, ds, v, s, 1220, {"newhire": "*"})

# ================= 2. AUDITOR =================
DBF = '| search event IN ("db.session.start","db.session.query","db.session.end") resource="$res$" actor="$who$"'
ds = BASE(); ds["ds_db"] = chain(DBF)
ds["k1"] = spark('event="db.session.start" AND outcome="allowed"', "ds_db")
ds["k2"] = plain('| search event="db.session.start" outcome="allowed" | stats dc(actor) as ids', "ds_db")
ds["k3"] = spark('event="db.session.query"', "ds_db")
ds["k4"] = spark('event="db.session.start" AND outcome="denied"', "ds_db")
ds["k5"] = spark('is_write=1', "ds_db")
ds["t1"] = chain('| stats count(eval(event="db.session.start" AND outcome="allowed")) as sessions, count(eval(event="db.session.query")) as queries, sum(is_write) as write_attempts, dc(db_user) as db_users, min(_time) as first_seen, max(_time) as last_seen by actor, actor_class | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M"), last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - queries', "ds_db")
ds["c1"] = chain('| search event="db.session.query" | timechart span=1d count by actor limit=8 useother=f', "ds_db")
ds["c2"] = chain('| search event="db.session.start" | eval hr=printf("%02d",hour_utc) | chart count over hr by actor_class', "ds_db")
ds["t2"] = chain('| search event="db.session.query" | eval kind=if(is_write=1,"WRITE","read") | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S") | table time actor db_user kind db_query sid uid', "ds_db")
v = {"v_k1": pk("k1", "DATABASE SESSIONS", BLUE), "v_k2": plainkpi("k2", "IDENTITIES THAT CONNECTED", TEAL), "v_k3": pk("k3", "QUERIES ON RECORD", PURPLE),
     "v_k4": pk("k4", "CONNECTIONS DENIED", GREEN, alert=RED), "v_k5": pk("k5", "WRITE ATTEMPTS", GREEN, alert=AMBER),
     "v_t1": mtable("t1", "Who accessed the database", 8, "actor_class", {"human": "#1F4E79", "ai_agent": "#5B3A8C", "workload": "#1F6B6B", "system": "#3A4352"}),
     "v_c1": col("c1", "Queries per day, by identity"),
     "v_c2": col("c2", "When is the database used? (UTC hour, by identity class)", {"human": BLUE, "ai_agent": PURPLE, "workload": TEAL, "system": GREY}),
     "v_q": card("### Questions an auditor asks, and where the answer lives\n- **Who accessed it?** The \"Who accessed the database\" table\n- **What did they run?** The query log below, with a unique event ID (uid)\n- **Was it allowed?** Connections denied, and Security Watch\n- **Was the credential short-lived?** Trust Scorecard\n- **Can I export it?** Use Export on any panel\n\n*This supports evidence for access-control and logging requirements (for example C5, KRITIS, DORA). It does not certify compliance by itself.*"),
     "v_t2": mtable("t2", "Full query log (the evidence trail)", 8, "kind", {"WRITE": "#7A5A1A", "read": "#1F4E3A"})}
s = [blk("v_k%d" % (i + 1), X0 + i * (cols(5) + G), 140, cols(5), 190) for i in range(5)]
for vid, t, c, x, y, w in [("v_l1", "①  Who touched the database, and how often", BLUE, X0, 350, W), ("v_l2", "②  When it is used, and what the auditor can ask", AMBER, X0, 800, W), ("v_l3", "③  The evidence trail: every query, with its event ID", GREEN, X0, 1210, W)]:
    d, b = label(vid, t, c, x, y, w); v.update(d); s += b
s += [blk("v_t1", X0, 392, 1000, 380)]; s[-1:] = [blk("v_t1", X0, 392, 1000, 380), blk("v_c1", X0 + 1000 + G, 392, W - 1000 - G, 380)]
s += [blk("v_c2", X0, 842, 700, 340), blk("v_q", X0 + 700 + G, 842, W - 700 - G, 340), blk("v_t2", X0, 1252, W, 380)]
page("tp_studio_auditor", "2 · Auditor Evidence (Studio)", "Who touched the database, when, and what did they run?", TEAL,
     "Scene 2: auditor evidence. Who touched the database, when, and what did they run?", "Every answer comes from the Teleport audit log, tied to an identity and a unique event ID.",
     {"input_who": itext("Identity (name or *)", "who"), "input_res": itext("Database (name or *)", "res")}, ds, v, s, 1680, {"who": "*", "res": "*"})

# ================= 3. AI AGENT =================
ds = BASE(); ds["ds_ag"] = chain('| search actor="$agent$"')
ds["k1"] = spark('event="db.session.start" AND outcome="allowed"', "ds_ag")
ds["k2"] = spark('event="db.session.query" AND is_write=0', "ds_ag")
ds["k3"] = spark('is_write=1', "ds_ag")
ds["k4"] = spark('event="db.session.start" AND outcome="denied"', "ds_ag")
ds["k5"] = plain('| search event="cert.create" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h', "ds_ag")
ds["c1"] = chain('| search event IN ("db.session.query","db.session.start") | eval kind=case(is_write=1,"write attempt",event="db.session.start" AND outcome="denied","blocked by Teleport",event="db.session.query","read (allowed)") | where isnotnull(kind) | timechart span=1d count by kind', "ds_ag")
ds["t1"] = chain('| stats dc(resource) as resources, values(resource) as reaches, values(db_user) as as_db_user, avg(ttl_h) as avg_cert_hours by actor | eval reaches=mvjoin(mvindex(reaches,0,2),", "), as_db_user=mvjoin(mvindex(as_db_user,0,2),", "), avg_cert_hours=round(avg_cert_hours,1)', "ds_ag")
ds["t2"] = chain('| search event IN ("db.session.start","db.session.query") | stats min(_time) as started, count(eval(event="db.session.query")) as queries, sum(is_write) as write_attempts, count(eval(event="db.session.start" AND outcome="denied")) as blocked_connects, values(db_user) as db_user by sid, actor | eval verdict=case(blocked_connects>0 AND write_attempts>0,"Blocked + write attempt", blocked_connects>0,"Blocked at Teleport", write_attempts>0,"Write attempted", true(),"Clean read-only") | sort - started | eval started=strftime(started,"%Y-%m-%d %H:%M") | table started actor verdict queries write_attempts blocked_connects db_user sid', "ds_ag")
ds["t3"] = chain('| search sid="$sel_sid$" | sort 0 _time | eval time=strftime(_time,"%H:%M:%S") | table time event db_user db_query outcome', "ds_base")
VER = {"Clean read-only": "#1F6B4A", "Write attempted": "#7A5A1A", "Blocked at Teleport": "#7A2B27", "Blocked + write attempt": "#7A2B27"}
v = {"v_k1": pk("k1", "AGENT DATABASE SESSIONS", BLUE), "v_k2": pk("k2", "READ QUERIES", GREEN), "v_k3": pk("k3", "WRITE ATTEMPTS", GREEN, alert=AMBER), "v_k4": pk("k4", "BLOCKED AT TELEPORT", GREEN, alert=RED),
     "v_k5": plainkpi("k5", "CREDENTIAL LIFETIME (HOURS)", AMBER),
     "v_c1": col("c1", "Intent vs outcome, per day", {"read (allowed)": GREEN, "write attempt": AMBER, "blocked by Teleport": RED}),
     "v_t1": mtable("t1", "Blast radius: what can each identity reach?", 6),
     "v_t2": mtable("t2", "Agent sessions (click a row to replay it)", 6, "verdict", VER, tok(("sel_sid", "row.sid.value"))),
     "v_t3": mtable("t3", "Session replay: exactly what this session ran", 8),
     "v_n": card("**Say it like this:** Claude decides. Teleport decides what Claude is allowed to do. Splunk records what actually happened. The agent has its own machine identity (not a human admin), a read-only role, and a credential that lives about an hour.  \n"
                 "*Honest detail:* a write attempt shown as allowed means Teleport forwarded and logged the query; the read-only database user is what refuses the change. Teleport itself blocks the request when the agent asks for a database user its role does not allow (the red rows).")}
s = [blk("v_k%d" % (i + 1), X0 + i * (cols(5) + G), 140, cols(5), 190) for i in range(5)]
for vid, t, c, y in [("v_l1", "①  What the agent tried, and what happened", PURPLE, 350), ("v_l2", "②  Every session: click one to replay it", AMBER, 800), ("v_l3", "③  The replay, then how to say it", GREEN, 1170)]:
    d, b = label(vid, t, c, X0, y, W); v.update(d); s += b
s += [blk("v_c1", X0, 392, 1000, 380), blk("v_t1", X0 + 1000 + G, 392, W - 1000 - G, 380), blk("v_t2", X0, 842, W, 300),
      blk("v_t3", X0, 1212, W, 300), blk("v_n", X0, 1532, W, 130)]
page("tp_studio_agent", "3 · AI Agent Governance (Studio)", "Claude decides. Teleport decides what is allowed. Splunk records what happened.", PURPLE,
     "Scene 3: AI agent governance. Claude decides. Teleport decides. Splunk proves.", "A separate machine identity, a read-only role, a one-hour credential, and every attempt on the record.",
     {"input_agent": itext("Machine identity (name or bot-*)", "agent", "bot-*")}, ds, v, s, 1700, {"agent": "bot-*", "sel_sid": "__none__"})

# ================= 4. SECURITY =================
EXTRA = '''
| eval external=if(isnotnull(src_ip) AND src_ip!="" AND NOT (cidrmatch("10.0.0.0/8",src_ip) OR cidrmatch("172.16.0.0/12",src_ip) OR cidrmatch("192.168.0.0/16",src_ip) OR cidrmatch("127.0.0.0/8",src_ip)),1,0)
| eval offhours=if(actor_type="human" AND (hour_utc<6 OR hour_utc>=19),1,0)
| eval signal=case(event="user.login" AND success="false","Failed login", event="auth" AND outcome="denied","Denied SSH", event="db.session.start" AND outcome="denied","Denied DB connect", event="kube.request" AND outcome="denied","Denied Kubernetes", is_write=1,"Write attempt", in(event,"user.update","role.created","user.create") AND actor_type="human","Change outside code", actor_type="human" AND external=1,"Unusual source IP", offhours=1,"Off-hours access")'''
ds = BASE(EXTRA)
ds["k1"] = spark('event="user.login" AND success="false"'); ds["k3"] = spark('offhours=1'); ds["k5"] = spark('actor_type="machine" AND outcome="denied"')
ds["k6"] = spark('in(event,"user.update","role.created","user.create") AND actor_type="human"')
ds["k2"] = plain('| search event="user.login" success="false" | bin _time span=5m | stats count by _time, actor | where count>=5 | stats count')
ds["k4"] = plain('| search actor_type="human" external=1 | stats dc(src_ip) as ips')
ds["k7"] = plain('| search event="db.session.query" | bin _time span=5m | stats count by _time, actor | where count>=15 | stats count')
ds["c1"] = chain('| where isnotnull(signal) | timechart span=1d count by signal')
ds["t1"] = chain('| where isnotnull(signal) | stats count, min(_time) as first_seen, max(_time) as last_seen, values(src_ip) as from_ip by actor, signal | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M"), last_seen=strftime(last_seen,"%Y-%m-%d %H:%M"), from_ip=mvjoin(mvindex(from_ip,0,1),", ") | sort - count')
ds["t2"] = chain('| search event="user.login" success="false" | bin _time span=5m | stats count, values(src_ip) as from_ip by _time, actor | where count>=5 | sort - _time | eval _time=strftime(_time,"%Y-%m-%d %H:%M"), from_ip=mvjoin(mvindex(from_ip,0,1),", ")')
ds["t3"] = chain('| search actor_type="human" external=1 | stats count, min(_time) as first_seen by actor, src_ip | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M") | sort - first_seen')
ds["t4"] = chain('| search offhours=1 | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M") | table time actor event resource src_ip')
ds["t5"] = chain('| search actor_type="machine" outcome="denied" | eval reason=substr(error,1,110) | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M") | table time actor event resource reason')
ds["t6"] = chain('| search event IN ("user.update","role.created","user.create") actor_type="human" | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M") | table time actor event name roles')
ds["t7"] = chain('| search event="db.session.query" | bin _time span=5m | stats count, values(resource) as resource by _time, actor | where count>=15 | sort - _time | eval _time=strftime(_time,"%Y-%m-%d %H:%M"), resource=mvjoin(resource,", ")')
ds["t8"] = chain('| search event="kube.request" kubernetes_cluster="k8s-prod" (outcome="denied" OR request_path="*exec*") | eval what=if(outcome="denied","DENIED","exec") | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M") | table time actor verb request_path response_code what')
SIGC = {"Failed login": AMBER, "Denied SSH": RED, "Denied DB connect": "#FF7A70", "Write attempt": PURPLE, "Unusual source IP": BLUE, "Off-hours access": GREY, "Change outside code": "#D9A441", "Denied Kubernetes": "#B03A33"}
v = {"v_k1": pk("k1", "FAILED LOGINS", GREEN, alert=AMBER), "v_k2": plainkpi("k2", "BRUTE-FORCE BURSTS (5+ IN 5 MIN)", RED), "v_k3": pk("k3", "OFF-HOURS HUMAN EVENTS", GREEN, alert=AMBER),
     "v_k4": plainkpi("k4", "UNUSUAL SOURCE IPS (PEOPLE)", BLUE), "v_k5": pk("k5", "BOT ACTIONS DENIED", GREEN, alert=RED), "v_k6": pk("k6", "ACCESS CHANGES BY PEOPLE", GREEN, alert=AMBER),
     "v_k7": plainkpi("k7", "BULK READS (15+ IN 5 MIN)", PURPLE),
     "v_c1": col("c1", "Risk signals over time", SIGC), "v_t1": mtable("t1", "Signals by identity", 8),
     "v_t2": mtable("t2", "Brute-force detector", 5), "v_t3": mtable("t3", "Unusual source IPs (people)", 5), "v_t4": mtable("t4", "Off-hours access (before 06:00 or after 19:00 UTC)", 5),
     "v_t5": mtable("t5", "Machine identities denied", 5), "v_t6": mtable("t6", "Access changes made by people, not code", 5), "v_t7": mtable("t7", "Bulk data reads (15+ queries in 5 min)", 5),
     "v_t8": mtable("t8", "Kubernetes: production exec and denials", 6, "what", {"DENIED": "#7A2B27", "exec": "#7A5A1A"})}
s = [blk("v_k%d" % (i + 1), X0 + i * (cols(7) + G), 140, cols(7), 190) for i in range(7)]
for vid, t, c, y in [("v_l1", "①  What is happening right now", AMBER, 350), ("v_l2", "②  The detectors", RED, 800), ("v_l3", "③  Machines, changes and bulk reads", PURPLE, 1170), ("v_l4", "④  Kubernetes production", TEAL, 1530)]:
    d, b = label(vid, t, c, X0, y, W); v.update(d); s += b
t3 = cols(3)
s += [blk("v_c1", X0, 392, 1000, 380), blk("v_t1", X0 + 1000 + G, 392, W - 1000 - G, 380)]
s += [blk("v_t%d" % (i + 2), X0 + i * (t3 + G), 842, t3, 300) for i in range(3)]
s += [blk("v_t%d" % (i + 5), X0 + i * (t3 + G), 1212, t3, 300) for i in range(3)]
s += [blk("v_t8", X0, 1572, W, 260)]
page("tp_studio_security", "4 · Security Watch (Studio)", "Failed logins, denials, odd hours, odd locations and bot misbehavior in one place.", RED,
     "Scene 4: security watch. Something looks wrong: where do you look?", "Failed logins, denials, odd hours, odd places and bot misbehavior, each tied to an identity.",
     {}, ds, v, s, 1870)
