#!/usr/bin/env python3
"""Pilot: Dashboard Studio version of the Unified Identity Layer + 'Why was the AI agent refused?' drill-down.
Writes  splunk/apps/teleport_lab/default/data/ui/views/tp_studio_identity.xml  (a NEW file; existing views untouched).
Reuses PRELUDE and DENY search text straight from the existing builder scripts so the logic stays identical."""
import os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'splunk/apps/teleport_lab/default/data/ui/views/tp_studio_identity.xml')

def grab(fname, var, raw_quote):
    s = open(os.path.join(HERE, fname), encoding='utf-8').read()
    m = re.search(r"^%s = r%s(.*?)%s" % (var, raw_quote, raw_quote), s, re.S | re.M)
    assert m, var
    return m.group(1)

PRELUDE = grab('build_dashboards.py', 'PRELUDE', "'''")
DENY = grab('dash_identity_and_drill.py', 'DENY', '"""')

BG, PANEL = '#0B0F17', '#141B27'
GREEN, RED, AMBER, BLUE, PURPLE, TEAL, GREY = '#3FB68B', '#E5534B', '#F0A030', '#4E9BE0', '#B07CE8', '#3FB6B6', '#7A8699'
CLS_COLORS = {'human': BLUE, 'ai_agent': PURPLE, 'workload': TEAL, 'system': GREY}

TR = {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}
ds = {
 "ds_base": {"type": "ds.search", "options": {"query": PRELUDE, "queryParameters": TR}, "name": "base"},
 "ds_f": {"type": "ds.chain", "options": {"extend": "ds_base", "query": '| search actor_class="$cls$"'}, "name": "filtered"},
 "ds_k_total": {"type": "ds.chain", "options": {"extend": "ds_f", "query": '| eventstats count as total | timechart span=1d count as events, first(total) as total | eventstats max(total) as total'}, "name": "k_total"},
 "ds_k_den": {"type": "ds.chain", "options": {"extend": "ds_f", "query": '| eventstats count(eval(outcome="denied")) as total | timechart span=1d count(eval(outcome="denied")) as events, first(total) as total | eventstats max(total) as total'}, "name": "k_den"},
 "ds_k_ai": {"type": "ds.chain", "options": {"extend": "ds_base", "query": '| eventstats count(eval(actor_class="ai_agent")) as total | timechart span=1d count(eval(actor_class="ai_agent")) as events, first(total) as total | eventstats max(total) as total'}, "name": "k_ai"},
 "ds_k_mfa": {"type": "ds.chain", "options": {"extend": "ds_base", "query": '| search event="user.login" | eventstats count(eval(isnotnull(mfa_device))) as mm, count as tt | eval total=if(tt>0,round(100*mm/tt,0),0) | timechart span=1d count(eval(isnotnull(mfa_device))) as m, count as t, first(total) as total | eval events=if(t>0,round(100*m/t,0),null()) | eventstats max(total) as total | fields _time events total'}, "name": "k_mfa"},
 "ds_k_ttl": {"type": "ds.chain", "options": {"extend": "ds_base", "query": '| search event="cert.create" | eventstats avg(ttl_h) as total | timechart span=1d avg(ttl_h) as events, first(total) as total | eventstats max(total) as total | eval total=round(total,1), events=round(events,1)'}, "name": "k_ttl"},
 "ds_k_ids": {"type": "ds.chain", "options": {"extend": "ds_f", "query": '| eventstats dc(actor) as total | timechart span=1d dc(actor) as events, first(total) as total | eventstats max(total) as total'}, "name": "k_ids"},
 "ds_sankey": {"type": "ds.chain", "options": {"extend": "ds_f", "query":
   '| eval resource=coalesce(resource,"(no resource)") | stats count by actor_class resource outcome '
   '| eval pair=mvappend(actor_class."|".resource, resource."|".outcome) | mvexpand pair '
   '| eval source=mvindex(split(pair,"|"),0), target=mvindex(split(pair,"|"),1) | stats sum(count) as count by source target | sort - count | head 40'}, "name": "sankey"},
 "ds_donut": {"type": "ds.chain", "options": {"extend": "ds_base", "query": '| stats count by actor_class'}, "name": "donut"},
 "ds_time": {"type": "ds.chain", "options": {"extend": "ds_f", "query": '| timechart span=1d count by outcome'}, "name": "time"},
 "ds_l1": {"type": "ds.chain", "options": {"extend": "ds_f", "query": DENY + '\n| where outcome="denied" | stats count as denials, dc(actor) as identities, values(actor_class) as classes, latest(_time) as last_seen by deny_reason, control, meaning | eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - denials | table deny_reason denials identities classes control meaning last_seen'}, "name": "l1"},
 "ds_l2": {"type": "ds.chain", "options": {"extend": "ds_f", "query": DENY + '\n| where outcome="denied" | search deny_reason="$d_reason$" | stats count as denials, values(event) as events, values(resource) as resources, latest(_time) as last_seen by actor, actor_class | eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - denials'}, "name": "l2"},
 "ds_l3": {"type": "ds.chain", "options": {"extend": "ds_f", "query": DENY + '\n| where outcome="denied" | search deny_reason="$d_reason$" actor="$d_actor$" | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S") | table time actor event code resource deny_reason uid | head 100'}, "name": "l3"},
 "ds_l4": {"type": "ds.search", "options": {"query": '$src$ sourcetype=teleport:audit uid="$d_uid$" | eval actor=coalesce(user,\'identity.user\',user_name) | eval evidence=_raw | table _time actor event code evidence',
   "queryParameters": TR}, "name": "l4"},
}

def tok(*pairs): return [{"type": "drilldown.setToken", "options": {"tokens": [{"token": t, "key": k} for t, k in pairs]}}]
def tokv(**kv): return [{"type": "drilldown.setToken", "options": {"tokens": [{"token": t, "value": v} for t, v in kv.items()]}}]


def kpi(ds_id, title, color, handlers=None, unit=None):
    o = {"majorColor": color, "sparklineDisplay": "below", "trendDisplay": "off", "majorValue": "> primary | seriesByName('total') | lastPoint()",
         "sparklineValues": "> primary | seriesByName('events')", "showSparklineAreaGraph": True, "sparklineStrokeColor": color,
         "sparklineAreaColor": color, "backgroundColor": PANEL, "majorFontSize": 56}
    if unit: o["unit"] = unit
    v = {"type": "splunk.singlevalue", "title": title, "dataSources": {"primary": ds_id}, "options": o}
    if handlers: v["eventHandlers"] = handlers
    return v

CLS_BG = [{"match": k, "value": c} for k, c in [("ai_agent", "#5B3A8C"), ("human", "#1F4E79"), ("workload", "#1F6B6B"), ("system", "#3A4352")]]
def table(ds_id, title, handlers, count=5, cls_col=False):
    v = {"type": "splunk.table", "title": title, "dataSources": {"primary": ds_id},
         "options": {"count": count, "backgroundColor": PANEL, "dataOverlayMode": "none", "showRowNumbers": False, "wrap": True}}
    if cls_col:
        v["options"]["columnFormat"] = {"actor_class": {"rowBackgroundColors": "> table | seriesByName(\"actor_class\") | matchValue(actor_classBgConfig)",
                                                        "rowColors": "> table | seriesByName(\"actor_class\") | matchValue(actor_classFgConfig)"}}
        v["context"] = {"actor_classBgConfig": CLS_BG, "actor_classFgConfig": [{"match": k, "value": "#FFFFFF"} for k in CLASS_KEYS]}
    if handlers: v["eventHandlers"] = handlers
    return v
CLASS_KEYS = ["ai_agent", "human", "workload", "system"]

def text(t, size=16, color="#E6EDF7", bold=False, align="left"):
    pre = "# " if size >= 30 else ("## " if size >= 20 else "")
    return {"type": "splunk.markdown", "options": {"markdown": pre + t, "fontColor": color, "backgroundColor": "transparent"}}
def bar(color): return {"type": "splunk.rectangle", "options": {"fillColor": color, "strokeColor": color, "rx": 4}}
def card(md): return {"type": "splunk.markdown", "options": {"backgroundColor": PANEL, "fontColor": "#E6EDF7", "markdown": md}}

viz = {
 "v_bar": bar(PURPLE),
 "v_h1": text("Identity is the new perimeter: humans, machines and AI agents on one layer", 34, "#FFFFFF", True),
 "v_h2": text("Claude decides what it wants to do  ·  Teleport decides what it is allowed to do  ·  Splunk proves what actually happened", 17, "#9FB3CC"),
 "v_k1": kpi("ds_k_total", "EVENTS SEEN", BLUE),
 "v_k2": kpi("ds_k_den", "DENIED / FAILED  ·  click to reset drill", RED, tokv(d_reason="*", d_actor="*", d_uid="__none__")),
 "v_k3": kpi("ds_k_ai", "AI-AGENT ACTIONS", PURPLE),
 "v_k4": kpi("ds_k_mfa", "LOGINS PROTECTED BY MFA", GREEN, unit="%"),
 "v_k5": kpi("ds_k_ttl", "AVG CERTIFICATE LIFETIME (HOURS)", AMBER),
 "v_k6": kpi("ds_k_ids", "DISTINCT IDENTITIES", TEAL),
 "v_c1": text("①  WHO is acting", 20, PURPLE, True),
 "v_c2": text("②  WHAT they reached, and Teleport's verdict", 20, TEAL, True),
 "v_c3": text("③  WHAT was stopped", 20, RED, True),
 "v_donut": {"type": "splunk.pie", "title": "Click a slice to filter the whole page", "dataSources": {"primary": "ds_donut"},
             "options": {"backgroundColor": PANEL, "showDonutHole": True, "collapseThreshold": 0, "seriesColors": [PURPLE, BLUE, TEAL, GREY],
                         "labelDisplay": "valuesAndPercentage"},
             "eventHandlers": [{"type": "drilldown.setToken", "options": {"tokens": [{"token": "cls", "key": "name"}]}}]},
 "v_sankey": {"type": "splunk.sankey", "title": "Identity class  →  resource  →  outcome", "dataSources": {"primary": "ds_sankey"}, "options": {"backgroundColor": PANEL}},
 "v_time": {"type": "splunk.column", "title": "Allowed vs denied, per day", "dataSources": {"primary": "ds_time"},
            "options": {"backgroundColor": PANEL, "stackMode": "stacked", "seriesColorsByField": {"allowed": GREEN, "denied": RED}, "legendDisplay": "bottom"}},
 "v_c4": text("④  WHY it was stopped: click a row at each level, the filters follow you down", 20, AMBER, True),
 "v_guide": card("**Where you are now**   class `$cls$`  ·  why `$d_reason$`  ·  who `$d_actor$`  ·  event `$d_uid$`  \n"
                 "An asterisk means all. Level 1 = the reason and the control that refused. Level 2 = which identity. Level 3 = which events. Level 4 = the raw audit evidence."),
 "v_l1": table("ds_l1", "Level 1 · Why were requests denied?", tok(("d_reason", "row.deny_reason.value")) + tokv(d_actor="*", d_uid="__none__"), count=6),
 "v_l2": table("ds_l2", "Level 2 · Who was denied?", tok(("d_actor", "row.actor.value")) + tokv(d_uid="__none__"), count=6, cls_col=True),
 "v_l3": table("ds_l3", "Level 3 · The exact events (click one for the evidence)", tok(("d_uid", "row.uid.value")), count=6),
 "v_l4": table("ds_l4", "Level 4 · Evidence card: the raw audit event", None, count=1),
 "v_c5": text("⑤  HOW I would run this with a team  (operating model, a proposal)", 20, GREEN, True),
 "v_m1": card("### Detect\nSplunk watches every Teleport audit event. Denials, new identities and write attempts are triaged **daily**, with a named owner and a response-time goal."),
 "v_m2": card("### Decide\nAccess is **policy as code**: roles and bots live in Git, change by pull request, and every change is reviewed. No one gets standing access; agents start read-only."),
 "v_m3": card("### Prove\nEach denial can be traced to an identity, a role and a raw event in seconds. A **weekly access review** turns that into evidence for auditors and for engineering."),
}

X0, W, G = 40, 1840, 22
kw = (W - 5 * G) // 6
def blk(item, x, y, w, h): return {"item": item, "type": "block", "position": {"x": x, "y": y, "w": w, "h": h}}
DW, SW = 430, 980; TW = W - DW - SW - 2 * G
structure = [
 blk("v_bar", X0, 30, 10, 86), blk("v_h1", X0 + 28, 24, 1700, 56), blk("v_h2", X0 + 28, 82, 1700, 34),
 *[blk("v_k%d" % (i + 1), X0 + i * (kw + G), 140, kw, 190) for i in range(6)],
 blk("v_c1", X0, 350, DW, 36), blk("v_c2", X0 + DW + G, 350, SW, 36), blk("v_c3", X0 + DW + SW + 2 * G, 350, TW, 36),
 blk("v_donut", X0, 392, DW, 420), blk("v_sankey", X0 + DW + G, 392, SW, 420), blk("v_time", X0 + DW + SW + 2 * G, 392, TW, 420),
 blk("v_c4", X0, 840, W, 36), blk("v_guide", X0, 882, W, 80),
 blk("v_l1", X0, 982, W, 230),
 blk("v_l2", X0, 1232, 700, 300), blk("v_l3", X0 + 700 + G, 1232, W - 700 - G, 300),
 blk("v_l4", X0, 1552, W, 190),
 blk("v_c5", X0, 1770, W, 36),
 blk("v_m1", X0, 1812, (W - 2 * G) // 3, 170), blk("v_m2", X0 + (W - 2 * G) // 3 + G, 1812, (W - 2 * G) // 3, 170), blk("v_m3", X0 + 2 * ((W - 2 * G) // 3 + G), 1812, (W - 2 * G) // 3, 170),
]
definition = {
 "title": "Unified Identity Layer (Studio)",
 "description": "Identity classes, who reached what, and a 4-level why-was-it-refused drill-down, plus an operating model.",
 "inputs": {
  "input_time": {"type": "input.timerange", "title": "Time range", "options": {"token": "global_time", "defaultValue": "-15d@d,now"}},
  "input_src": {"type": "input.dropdown", "title": "Data source", "options": {"token": "src", "defaultValue": "index=teleport_demo", "items": [
      {"label": "Demo data (synthetic, 15 days)", "value": "index=teleport_demo"},
      {"label": "Live lab data", "value": "index=teleport"},
      {"label": "Both", "value": "(index=teleport OR index=teleport_demo)"}]}},
  "input_cls": {"type": "input.dropdown", "title": "Identity class", "options": {"token": "cls", "defaultValue": "*", "items": [
      {"label": "All identities", "value": "*"}, {"label": "Humans", "value": "human"}, {"label": "AI agents", "value": "ai_agent"},
      {"label": "Workloads (services, CI)", "value": "workload"}, {"label": "Teleport system", "value": "system"}]}},
 },
 "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}}}},
              "tokens": {"default": {"d_reason": {"value": "*"}, "d_actor": {"value": "*"}, "d_uid": {"value": "__none__"}}}},
 "dataSources": ds, "visualizations": viz,
 "layout": {"type": "absolute", "options": {"width": 1920, "height": 2020, "display": "auto-scale", "backgroundColor": BG},
            "structure": structure, "globalInputs": ["input_time", "input_src", "input_cls"]},
}
js = json.dumps(definition, indent=2, ensure_ascii=False)
assert ']]>' not in js
xml = ('<dashboard version="2" theme="dark">\n  <label>Unified Identity Layer (Studio)</label>\n'
       '  <description>Identity story: who, what, stopped, why, and how a team runs it</description>\n  <definition><![CDATA[\n%s\n]]></definition>\n'
       '  <meta type="hiddenElements"><![CDATA[{"hideEdit": false, "hideOpenInSearch": false, "hideExport": false}]]></meta>\n</dashboard>\n' % js)
open(OUT, 'w', encoding='utf-8').write(xml)
print('wrote', os.path.normpath(OUT), len(xml), 'bytes')
