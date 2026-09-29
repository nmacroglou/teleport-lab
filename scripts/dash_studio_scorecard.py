#!/usr/bin/env python3
"""Dashboard Studio version of the Trust Scorecard (opening screen). Writes tp_studio_scorecard.xml (new file; the Simple XML scorecard is untouched).
Shares constants/helpers with dash_studio_identity.py (importing it also rewrites that view, which is harmless)."""
import os, json
import dash_studio_identity as I
from dash_studio_identity import PRELUDE, DENY, BG, PANEL, GREEN, RED, AMBER, BLUE, PURPLE, TEAL, GREY, TR, kpi, text, bar, card, blk, table, tok, tokv

OUT = os.path.join(I.HERE, '..', 'splunk/apps/teleport_lab/default/data/ui/views/tp_studio_scorecard.xml')

def chain(q): return {"type": "ds.chain", "options": {"extend": "ds_base", "query": q}}
def kds(cond_events, cond_total_expr):
    pass

CERT = '| search event="cert.create" '
ds = {
 "ds_base": {"type": "ds.search", "options": {"query": PRELUDE, "queryParameters": TR}, "name": "base"},
 "k1": chain(CERT + '| eventstats count as total | timechart span=1d count as events, first(total) as total | eventstats max(total) as total'),
 "k2": chain(CERT + '| eventstats count as c, count(eval(ttl_h<=12)) as s | eval total=if(c>0,round(s/c*100,1),0) | timechart span=1d count as n, count(eval(ttl_h<=12)) as sh, first(total) as total | eval events=if(n>0,round(sh/n*100,1),null()) | eventstats max(total) as total | fields _time events total'),
 "k3": chain(CERT + '| eventstats count(eval(ttl_h>24)) as total | timechart span=1d count(eval(ttl_h>24)) as events, first(total) as total | eventstats max(total) as total'),
 "k4": chain(CERT + '| eventstats avg(ttl_h) as total | timechart span=1d avg(ttl_h) as events, first(total) as total | eventstats max(total) as total | eval events=round(events,1), total=round(total,1)'),
 "k5": chain('| eventstats count(eval(outcome="denied")) as total | timechart span=1d count(eval(outcome="denied")) as events, first(total) as total | eventstats max(total) as total'),
 "k6": chain('| eventstats count as c, count(eval(actor_type="machine")) as m | eval total=if(c>0,round(m/c*100,0),0) | timechart span=1d count as n, count(eval(actor_type="machine")) as mm, first(total) as total | eval events=if(n>0,round(mm/n*100,0),null()) | eventstats max(total) as total | fields _time events total'),
 "c1": chain(CERT + '| timechart span=1d count by actor_type'),
 "c2": chain(CERT + '| stats avg(ttl_h) as avg_hours by actor_type | eval avg_hours=round(avg_hours,2)'),
 "c3": chain('| where outcome="denied" | stats count as blocked by event | sort - blocked'),
 "b1": chain(DENY + '\n| where outcome="denied" | stats count as blocked, dc(actor) as identities, values(actor_class) as classes, latest(_time) as last_seen by deny_reason, event | eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - blocked | table deny_reason event blocked identities classes last_seen'),
 "b2": chain(DENY + '\n| where outcome="denied" | search deny_reason="$b_reason$" event="$b_event$" | stats count as blocked, values(event) as events, values(resource) as resources, latest(_time) as last_seen by actor, actor_class | eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - blocked'),
 "b3": chain(DENY + '\n| where outcome="denied" | search deny_reason="$b_reason$" event="$b_event$" actor="$b_actor$" | sort - _time | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S") | table time actor event code resource deny_reason uid | head 100'),
 "b4": {"type": "ds.search", "options": {"query": '$src$ sourcetype=teleport:audit uid="$b_uid$" | eval actor=coalesce(user,\'identity.user\',user_name) | eval evidence=_raw | table _time actor event code evidence', "queryParameters": TR}, "name": "evidence"},
}
ACT = {"human": BLUE, "machine": TEAL, "system": GREY}
def rng(color_hi): return {"majorColor": "> majorValue | rangeValue(majorColorCfg)"}
def k(ds_id, title, color, unit=None, alert=None):
    v = kpi(ds_id, title, color, unit=unit)
    if alert:  # green at zero, alert colour above zero
        v["options"]["majorColor"] = "> majorValue | rangeValue(majorColorCfg)"
        v["context"] = {"majorColorCfg": [{"to": 1, "value": GREEN}, {"from": 1, "value": alert}]}
    return v

CLS_BG = I.CLS_BG
viz = {
 "v_bar": bar(GREEN),
 "v_h1": text("Trust Scorecard: credentials that expire, actions that are attributed, policy that holds", 34, "#FFFFFF", True),
 "v_h2": text("The board-level answer to: can we prove who did what, with what access, and what was refused?", 17, "#9FB3CC"),
 "v_k1": k("k1", "CREDENTIALS ISSUED", BLUE),
 "v_k2": k("k2", "SHORT-LIVED (12 HOURS OR LESS)", GREEN, unit="%"),
 "v_k3": k("k3", "LONG-LIVED CREDENTIALS (OVER 24H)", GREEN, alert=RED),
 "v_k4": k("k4", "AVERAGE LIFETIME (HOURS)", AMBER),
 "v_k5": kpi("k5", "ACTIONS BLOCKED  ·  click to reset", AMBER, tokv(b_reason="*", b_event="*", b_actor="*", b_uid="__none__")),
 "v_k6": k("k6", "MACHINE SHARE OF ACTIVITY", TEAL, unit="%"),
 "v_c1": text("①  Credentials issued: people vs machines", 20, BLUE, True),
 "v_c2": text("②  How long they live", 20, AMBER, True),
 "v_c3": text("③  What policy blocked, by action", 20, RED, True),
 "v_p1": {"type": "splunk.column", "title": "Certificates per day", "dataSources": {"primary": "c1"},
          "options": {"backgroundColor": PANEL, "stackMode": "stacked", "seriesColorsByField": ACT, "legendDisplay": "bottom"}},
 "v_p2": {"type": "splunk.bar", "title": "Average lifetime by identity type (hours)", "dataSources": {"primary": "c2"},
          "options": {"backgroundColor": PANEL, "seriesColors": [AMBER], "legendDisplay": "off"}},
 "v_p3": {"type": "splunk.column", "title": "Blocked by action  (click a bar to drill in)", "dataSources": {"primary": "c3"},
          "options": {"backgroundColor": PANEL, "seriesColors": [RED], "legendDisplay": "off"},
          "eventHandlers": tok(("b_event", "row.event.value")) + tokv(b_reason="*", b_actor="*", b_uid="__none__")},
 "v_c4": text("④  What was blocked, and by whom: click a row to go deeper", 20, PURPLE, True),
 "v_t1": table("b1", "Level 1 · What actions were blocked, and why?", tok(("b_reason", "row.deny_reason.value"), ("b_event", "row.event.value")) + tokv(b_actor="*", b_uid="__none__"), count=6),
 "v_t2": table("b2", "Level 2 · Who was blocked?  (click an identity)", tok(("b_actor", "row.actor.value")) + tokv(b_uid="__none__"), count=6, cls_col=True),
 "v_t3": table("b3", "Level 3 · The exact events  (click one for the raw evidence)", tok(("b_uid", "row.uid.value")), count=6),
 "v_t4": table("b4", "Level 4 · Evidence card: the raw audit event", None, count=1),
 "v_c5": text("⑤  The customer story: before and after", 20, GREEN, True),
 "v_b1": card("### Before  (PPI Financial Services)\nManual certificate management, complex onboarding, fragmented access workflows."),
 "v_b2": card("### After\nSingle sign-on, short-lived access, every session audited, access policy managed as code (Kubernetes operator and Terraform)."),
 "v_b3": card("### What this lab shows\nThe same idea for humans, machines **and** AI agents: credentials that expire in hours, each action tied to an identity, denials recorded. "
              "Next: [Unified Identity Layer](/app/teleport_lab/tp_studio_identity) · [Command Center drill-down](/app/teleport_lab/teleport_overview)"),
}
X0, W, G = 40, 1840, 22
kw = (W - 5 * G) // 6; tw = (W - 2 * G) // 3
structure = [blk("v_bar", X0, 30, 10, 86), blk("v_h1", X0 + 28, 24, 1750, 56), blk("v_h2", X0 + 28, 82, 1750, 34)]
structure += [blk("v_k%d" % (i + 1), X0 + i * (kw + G), 140, kw, 190) for i in range(6)]
for i, (c, p) in enumerate([("v_c1", "v_p1"), ("v_c2", "v_p2"), ("v_c3", "v_p3")]):
    structure += [blk(c, X0 + i * (tw + G), 350, tw, 36), blk(p, X0 + i * (tw + G), 392, tw, 380)]
half = (W - G) // 2
structure += [blk("v_c4", X0, 800, W, 36),
              blk("v_t1", X0, 842, half, 340), blk("v_t2", X0 + half + G, 842, half, 340),
              blk("v_t3", X0, 1204, W, 330), blk("v_t4", X0, 1556, W, 190),
              blk("v_c5", X0, 1780, W, 36)]
structure += [blk("v_b%d" % (i + 1), X0 + i * (tw + G), 1822, tw, 170) for i in range(3)]

definition = {
 "title": "Trust Scorecard (Studio)", "description": "Short-lived credentials, attributed actions, and what policy blocked.",
 "inputs": {k_: v for k_, v in I.definition["inputs"].items() if k_ in ("input_time", "input_src")},
 "defaults": {"dataSources": {"ds.search": {"options": {"queryParameters": {"earliest": "$global_time.earliest$", "latest": "$global_time.latest$"}}}},
              "tokens": {"default": {"b_reason": {"value": "*"}, "b_event": {"value": "*"}, "b_actor": {"value": "*"}, "b_uid": {"value": "__none__"}}}},
 "dataSources": ds, "visualizations": viz,
 "layout": {"type": "absolute", "options": {"width": 1920, "height": 2020, "display": "auto-scale", "backgroundColor": BG},
            "structure": structure, "globalInputs": ["input_time", "input_src"]},
}
js = json.dumps(definition, indent=2, ensure_ascii=False); assert ']]>' not in js
open(OUT, 'w', encoding='utf-8').write(
 '<dashboard version="2" theme="dark">\n  <label>Trust Scorecard (Studio)</label>\n  <description>Short-lived credentials, attributed actions, policy that holds</description>\n'
 '  <definition><![CDATA[\n%s\n]]></definition>\n  <meta type="hiddenElements"><![CDATA[{"hideEdit": false, "hideOpenInSearch": false, "hideExport": false}]]></meta>\n</dashboard>\n' % js)
print('wrote', os.path.normpath(OUT))
