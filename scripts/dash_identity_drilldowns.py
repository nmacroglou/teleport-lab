#!/usr/bin/env python3
"""Generate the executive drill-down dashboards under the Unified Identity Layer.

Levels:  L0  tp_identity (hub)  ->  L1  id_* pages  ->  L2  id_actor (one identity)
Writes Simple XML views into splunk/apps/teleport_lab/default/data/ui/views/.
Idempotent: safe to re-run. Does not touch data, only views and the hub links.
"""
import os, re, sys
from xml.sax.saxutils import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VIEWS = os.path.join(ROOT, "splunk/apps/teleport_lab/default/data/ui/views")

PASS = "form.src=$src|u$&amp;form.time.earliest=$time.earliest|u$&amp;form.time.latest=$time.latest|u$"

BASE = r'''
$src$ sourcetype=teleport:audit
| eval actor=coalesce(user, 'identity.user', user_name, "unknown")
| eval actor_type=case(like(actor,"bot-%"),"machine", actor="system","system", like(actor,"%.localhost"),"system", true(),"human")
| eval actor_class=case(actor_type="human","human", match(actor,"^bot-(claude|copilot|lab)"),"ai_agent", actor_type="machine","workload", true(),"system")
| eval outcome=if(success="false" OR like(code,"%W"),"denied","allowed")
| eval src=coalesce('addr.remote','identity.client_ip')
| eval src_ip=replace(src,":\d+$$","")
| eval resource=coalesce(db_service, app_name, server_hostname, kubernetes_cluster)
| eval res_type=case(isnotnull(db_service),"Database",isnotnull(kubernetes_cluster),"Kubernetes",isnotnull(app_name),"App",isnotnull(server_hostname),"Server")
| eval hour_utc=floor((_time%86400)/3600)
| eval ttl_h=if(event="cert.create", round((strptime(substr('identity.expires',1,19)."+0000","%Y-%m-%dT%H:%M:%S%z")-_time)/3600,2), null())
| eval is_write=if(event="db.session.query" AND match(db_query,"(?i)^\s*(create|drop|alter|insert|update|delete|truncate|grant)"),1,0)
| eval cat=case(is_write=1,"write attempt", event="db.session.query","read query", event="db.session.start","database connect", event="db.session.query.failed","database rejected", event="auth" OR event="session.start","ssh", event="kube.request","kubernetes", event="cert.create","credential issued", event="bot.join","bot join", event="user.login","login", true(),event)
| eval verdict=case(outcome="denied","refused", is_write=1,"tried to change data", event="db.session.query","normal read", true(),"other allowed")
| eval why=case(outcome="allowed",null(), code="TDB00W","Role has no admin database user", code="T3007W","SSH account not allowed", code="TDB03W","Read-only database user refused the write", event="user.login","Bad credentials or MFA", event="bot.join","Join token bad or expired", event="kube.request","Kubernetes access rules said no", true(),coalesce(error,"Policy"))
| eval external=if(match(src_ip,"^\d+\.\d+\.\d+\.\d+$$") AND NOT (cidrmatch("10.0.0.0/8",src_ip) OR cidrmatch("172.16.0.0/12",src_ip) OR cidrmatch("192.168.0.0/16",src_ip) OR cidrmatch("127.0.0.0/8",src_ip)),1,0)
| eval what=coalesce(db_query, error, request_path, name)
| fields _time, event, code, user, success, error, method, mfa_device, name, roles, login, sid, uid, db_service, db_name, db_user, db_query, app_name, server_hostname, kubernetes_cluster, verb, request_path, response_code, demo, actor, actor_type, actor_class, outcome, src, src_ip, resource, res_type, hour_utc, ttl_h, is_write, cat, verdict, why, external, what, "identity.roles{}", "identity.expires"
'''

NAV = {  # label, view
    "id_ai_agents":  "AI agents: behavior watch",
    "id_humans":     "Humans",
    "id_workloads":  "Workloads (machines)",
    "id_refusals":   "Refused by policy",
    "id_governance": "Access & governance",
    "id_estate":     "Software & hardware reach",
    "id_trust":      "Root of trust & credentials",
    "id_actor":      "Identity profile (one actor)",
}

def q(s): return "<![CDATA[\n" + s.strip() + "\n]]>"

def link(view, **extra):
    parts = [f"form.{k}={v}" for k, v in extra.items()]
    return view + "?" + "&amp;".join(parts + [PASS])

def crumbs(here, trail):
    """Breadcrumb + hub button so an exec always knows where they are."""
    items = [f'<a href="tp_identity?{PASS}" style="color:#8FB8FF;text-decoration:none">★ Unified Identity Layer</a>']
    for v, label in trail:
        items.append(f'<a href="{v}?{PASS}" style="color:#8FB8FF;text-decoration:none">{escape(label)}</a>')
    items.append(f'<b style="color:#fff">{escape(here)}</b>')
    return ('<row><panel><html><div style="font-size:13px;color:#8b93a7">' +
            "  ›  ".join(items) + "</div></html></panel></row>")

def banner(title, question, why):
    return (f'<row><panel><html><div style="border-left:6px solid #8B6CFF;padding:6px 14px;line-height:1.5">'
            f'<div style="font-size:20px;font-weight:700">{escape(title)}</div>'
            f'<div style="font-size:14px"><b>The question:</b> {escape(question)}</div>'
            f'<div style="font-size:13px;color:#8b93a7"><b>Why an exec cares:</b> {escape(why)}</div></div></html></panel></row>')

NOTES = []
def single(title, query, under, good_zero=False, warn=False, trend=False, unit=None):
    NOTES.append((title, under))
    query = query.replace("timechart span=1d count as x", "stats count as x")
    o = ['<option name="drilldown">none</option>']
    if good_zero:
        o += ['<option name="useColors">1</option>', '<option name="colorBy">value</option>',
              '<option name="rangeValues">[0]</option>', '<option name="rangeColors">["0x3FB68B","0xE5534B"]</option>']
    elif warn:
        o += ['<option name="useColors">1</option>', '<option name="colorBy">value</option>',
              '<option name="rangeValues">[0]</option>', '<option name="rangeColors">["0x3FB68B","0xF59E3F"]</option>']
    else:
        o += ['<option name="colorMode">none</option>']
    if unit: o.append(f'<option name="unit">{escape(unit)}</option>')
    return (f'<panel><title>{escape(title)}</title><single><search base="base"><query>{q(query)}</query></search>'
            + "".join(o) + '</single></panel>')

def table(title, query, drill=None, count=8, colors="", wrap=True, note=None, depends=None, base=True, extra=""):
    dr = f'<drilldown>{drill}</drilldown>' if drill else '<option name="drilldown">none</option>'
    dep = f' depends="{depends}"' if depends else ""
    n = f'<html><div style="font-size:12px;color:#8b93a7;margin-bottom:4px">{note}</div></html>' if note else ""
    return (f'<panel{dep}><title>{escape(title)}</title>{n}<table><search base="base"><query>{q(query)}</query></search>'
            f'<option name="count">{count}</option><option name="wrap">{"true" if wrap else "false"}</option>'
            f'<option name="rowNumbers">false</option>{dr}{colors}{extra}</table></panel>')

def chart(title, query, kind="column", stacked=False, colors=None, legend="bottom", note=None, extra=""):
    o = [f'<option name="charting.chart">{kind}</option>', f'<option name="charting.legend.placement">{legend}</option>',
         '<option name="charting.drilldown">none</option>']
    if stacked: o.append('<option name="charting.chart.stackMode">stacked</option>')
    if colors: o.append(f'<option name="charting.fieldColors">{colors}</option>')
    n = f'<html><div style="font-size:12px;color:#8b93a7">{note}</div></html>' if note else ""
    return (f'<panel><title>{escape(title)}</title>{n}<chart><search base="base"><query>{q(query)}</query></search>'
            + "".join(o) + extra + '</chart></panel>')

def html(title, body, depends=None):
    dep = f' depends="{depends}"' if depends else ""
    t = f"<title>{escape(title)}</title>" if title else ""
    return f'<panel{dep}>{t}<html><div style="line-height:1.55;font-size:14px">{body}</div></html></panel>'

def row(*panels):
    r = "<row>" + "".join(panels) + "</row>"
    if NOTES:
        cells = "".join(f'<div style="flex:1 1 150px;min-width:140px"><b style="color:#c9d1e6">{escape(t)}</b><br/>{escape(u)}</div>' for t, u in NOTES)
        NOTES.clear()
        r += ('<row><panel><html><div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;line-height:1.4;color:#8b93a7">'
              + cells + '</div></html></panel></row>')
    return r

WATCH = ('<format type="color" field="watch"><colorPalette type="map">{"Investigate":#E5534B,"Watch":#F59E3F,"Normal":#3FB68B}</colorPalette></format>')
CLASS = ('<format type="color" field="class"><colorPalette type="map">{"human":#4E9BE0,"ai_agent":#B07CE8,"workload":#3FB6B6,"system":#7A8699}</colorPalette></format>')
VERDICT = '{"refused":0xE5534B,"tried to change data":0xF59E3F,"normal read":0x3FB68B,"other allowed":0x5C6B85}'

def profile_drill(field="actor"):
    return f'<link target="_self">{link("id_actor", actor="$row."+field+"|u$")}</link>'

def form(label, desc, inputs, body, extra_search=""):
    src_input = ('<input type="dropdown" token="src"><label>Data source</label>'
        '<choice value="index=teleport_demo">Demo data (synthetic, 15 days)</choice><choice value="index=teleport">Live lab data</choice>'
        '<choice value="(index=teleport OR index=teleport_demo)">Both</choice>'
        '<default>(index=teleport OR index=teleport_demo)</default><initialValue>(index=teleport OR index=teleport_demo)</initialValue></input>')
    time_input = ('<input type="time" token="time"><label>Time range</label><default><earliest>-15d@d</earliest><latest>now</latest></default></input>')
    return ('<form version="1.1" theme="dark">'
            f'<label>{escape(label)}</label><description>{escape(desc)}</description>'
            f'<fieldset submitButton="false" autoRun="true">{time_input}{src_input}{inputs}</fieldset>'
            f'<search id="base"><query>{q(BASE)}</query><earliest>$time.earliest$</earliest><latest>$time.latest$</latest></search>'
            f'{extra_search}{body}</form>')

AGENT = '| search actor_class="ai_agent" actor="$agent$"'

# --------------------------------------------------------------------------- L1 AI agents
def d_agents():
    inputs = '<input type="text" token="agent"><label>Agent identity (name or *)</label><default>*</default><initialValue>*</initialValue></input>'
    worst = ('<search base="base"><query>' + q(AGENT + r'''
| stats count as actions, count(eval(outcome="denied")) as refused, sum(is_write) as writes by actor
| eval score=refused*2+writes*3 | sort - score | head 1''') + '</query><done><set token="worst">$result.actor$</set><set token="worst_ref">$result.refused$</set><set token="worst_wr">$result.writes$</set></done></search>')
    body = "".join([
        crumbs("AI agents: behavior watch", []),
        banner("Non-deterministic actors: what did the AI agents try, and did policy hold?",
               "Which agent is behaving least like the job it was given, and what stopped it?",
               "An agent chooses its own steps. Its prompt cannot be the safety boundary, so we measure behavior and prove the boundary held."),
        row(html("", '<div style="background:#2A2060;border-radius:10px;padding:12px 16px;color:#fff">'
                     '<b>Start here:</b> <span style="font-size:16px">'
                     f'<a href="id_actor?form.actor=$worst|u$&amp;{PASS}" style="color:#9FD0FF"><b>$worst$</b></a></span> '
                     'ranks highest for off-script behavior: <b>$worst_ref$</b> refusals and <b>$worst_wr$</b> attempts to change data. '
                     'Click its name to open its identity profile (level 2).</div>', depends="$worst$")),
        row(
            single("Agent identities", AGENT + " | stats dc(actor) as n", "Named machine identities, never a person's login."),
            single("Actions taken", AGENT + " | timechart span=1d count as x", "Everything an agent did in the window.", trend=True),
            single("Refused by Teleport", AGENT + ' | where outcome="denied" | timechart span=1d count as x', "Guardrail working. Zero means untested, not safe.", trend=True),
            single("Tried to change data", AGENT + " | where is_write=1 | stats count as n", "Write statements. Read-only DB user must refuse all.", warn=True),
            single("Retried after a no", AGENT + r'''
| sort 0 actor _time | streamstats current=f last(outcome) as prev_out last(_time) as prev_t by actor
| eval again=if(prev_out="denied" AND _time-prev_t<600,1,0) | stats sum(again) as n''', "Attempts within 10 min of a refusal: persistence.", warn=True),
            single("New behavior, last 24h", AGENT + r'''
| eval sig=event."|".coalesce(resource,"-")."|".outcome
| eventstats max(_time) as tmax
| eventstats min(_time) as sig_first by actor sig
| eventstats min(_time) as a_first by actor
| eval recent=if(_time>=tmax-86400,1,0), novel=if(recent=1 AND sig_first>=tmax-86400 AND a_first<tmax-259200,1,0)
| stats sum(novel) as n, sum(recent) as r | eval pct=if(r>0,round(n/r*100,0),0) | fields pct''', "% of last-24h actions never seen before from that identity.", warn=True, unit="%"),
        ),
        row(
            table("Behavior scorecard per agent (click a row to open the profile)", AGENT + r'''
| eval sig=event."|".coalesce(resource,"-")."|".outcome
| eventstats max(_time) as tmax
| eventstats min(_time) as sig_first by actor sig
| eventstats min(_time) as a_first by actor
| eval recent=if(_time>=tmax-86400,1,0), novel=if(recent=1 AND sig_first>=tmax-86400 AND a_first<tmax-259200,1,0)
| stats count as actions, dc(cat) as action_kinds, dc(resource) as resources, count(eval(outcome="denied")) as refused, sum(is_write) as write_attempts, sum(recent) as last_day, sum(novel) as novel_last_day, count(eval(hour_utc<6 OR hour_utc>=19)) as off_hours, latest(_time) as ls by actor
| eval refusal_pct=round(refused/actions*100,1), new_behavior_pct=if(last_day>0,round(novel_last_day/last_day*100,0),0), off_hours_pct=round(off_hours/actions*100,0)
| eval watch=case(refusal_pct>=10 OR new_behavior_pct>=50,"Investigate", write_attempts>0 OR refused>=3 OR new_behavior_pct>=30,"Watch", true(),"Normal")
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M")
| sort - refused
| table actor watch actions action_kinds resources refusal_pct write_attempts new_behavior_pct off_hours_pct last_seen''',
                  drill=profile_drill(), colors=WATCH, count=10,
                  note="Watch level: <b>Investigate</b> = 10%+ of its actions refused, or half its last-day behavior is new · <b>Watch</b> = any write attempt, 3+ refusals, or 30%+ new behavior · <b>Normal</b> otherwise.")),
        row(
            chart("Intent vs outcome, per day", AGENT + " | timechart span=1d count by verdict", stacked=True, colors=VERDICT,
                  note="Most days agents just read. The spikes are the bad days."),
            chart("What agents do (action mix)", AGENT + " | chart count over actor by cat", kind="bar", stacked=True, legend="right",
                  note="A narrow, repetitive mix is healthy. A wide, shifting mix is what non-deterministic looks like.")),
        row(
            table("When they act (UTC, 4-hour blocks, by agent)", AGENT + r'''
| eval blk=printf("%02d-%02d",floor(hour_utc/4)*4,floor(hour_utc/4)*4+3) | chart count over actor by blk''',
                  count=10, drill=profile_drill(),
                  extra='<format type="color"><colorPalette type="minMidMax" minColor="#1B2A41" midColor="#3A6EA5" maxColor="#7FD1FF"></colorPalette><scale type="minMidMax"></scale></format>',
                  note="Agents have no working hours. Bursts at odd hours are a signal, not a schedule."),
            table("Agents vs people vs machines (measured, not assumed)", r'''
| stats count as n by actor actor_class cat
| eventstats sum(n) as tot by actor
| eval p=n/tot, h=-p*log(p,2)
| stats sum(h) as entropy, sum(n) as actions, dc(cat) as kinds by actor actor_class
| stats dc(actor) as identities, avg(kinds) as avg_action_kinds, avg(entropy) as avg_spread_bits by actor_class
| eval avg_action_kinds=round(avg_action_kinds,1), avg_spread_bits=round(avg_spread_bits,2)
| rename actor_class as class''', count=6, colors=CLASS, wrap=False,
                  note="Spread (bits) = how varied an identity's actions are. Low: does the same few things. High: wide mix. Read the class rows against each other.")),
        row(table("Off-script moments, newest first (click a row to open the identity profile)", AGENT + r'''
| where outcome="denied" OR is_write=1
| sort - _time | head 200
| eval time=strftime(_time,"%Y-%m-%d %H:%M:%S")
| table time actor cat resource verdict why what uid''', drill=profile_drill(), count=8,
                 note="Every row is one audit event with a unique ID. The evidence is the log, not a screenshot.")),
        row(html("How to talk about this",
                 "<ul><li><b>Deterministic actors</b> (a cron job, a CI runner) do the same thing every time. Their policy can be written once.</li>"
                 "<li><b>Non-deterministic actors</b> (people, AI agents) can do anything they are allowed to. So the control has to sit outside the actor: its own identity, a read-only role, a credential that lasts about an hour.</li>"
                 "<li><b>What to look at:</b> refusals show the boundary held, retries show persistence, new behavior shows drift, and write attempts show intent.</li></ul>"
                 f'<div style="margin-top:8px">Next: <a href="id_refusals?{PASS}" style="color:#8FB8FF">Refused by policy (L1)</a> · <a href="id_trust?{PASS}" style="color:#8FB8FF">Credential hygiene (L1)</a></div>')),
    ])
    return form("L1 · AI agents: behavior watch",
                "Non-deterministic actors: what each AI agent tried, what policy refused, how its behavior drifts.",
                inputs, body, extra_search=worst)

# --------------------------------------------------------------------------- L1 humans
HUM = '| search actor_class="human"'
def d_humans():
    body = "".join([
        crumbs("Humans", []),
        banner("People: who are they, are they who they say they are, and are they behaving normally?",
               "Are there people logging in from odd places, at odd hours, without a second factor, or guessing passwords?",
               "Humans are predictable in bulk and dangerous in exceptions. The exceptions are what we surface."),
        row(
            single("Human identities", HUM + " | stats dc(actor) as n", "People who did anything in the window."),
            single("Logins with a second factor", HUM + ' | where event="user.login" AND success="true" | stats count as ok, count(eval(isnotnull(mfa_device))) as mfa | eval pct=if(ok>0,round(mfa/ok*100,0),0) | fields pct', "Target 100%. Anything less is a hole.", unit="%"),
            single("Failed logins", HUM + ' | where event="user.login" AND success="false" | timechart span=1d count as x', "Bad password or bad second factor.", trend=True),
            single("Off-hours activity", HUM + " | where hour_utc<6 OR hour_utc>=19 | stats count as n", "Before 06:00 or after 19:00 UTC.", warn=True),
            single("Outside-network addresses", HUM + " | where external=1 | stats dc(src_ip) as n", "People arriving from public IPs.", warn=True),
            single("Password-guessing bursts", HUM + r'''
| where event="user.login" AND success="false" | bin _time span=5m | stats count as f by actor _time | where f>=5 | stats count as n''', "5+ failures in 5 minutes by one person.", good_zero=True),
        ),
        row(table("Who is behaving oddly (click a row to open the profile)", HUM + r'''
| stats count as actions, count(eval(event="user.login" AND success="true")) as logins_ok, count(eval(event="user.login" AND success="false")) as logins_failed,
        count(eval(event="user.login" AND success="true" AND isnotnull(mfa_device))) as mfa_ok,
        count(eval(hour_utc<6 OR hour_utc>=19)) as off_hours, dc(eval(if(external=1,src_ip,null()))) as outside_ips,
        dc(resource) as resources, count(eval(outcome="denied")) as refused by actor
| eval mfa_pct=if(logins_ok>0,round(mfa_ok/logins_ok*100,0),null()), off_hours_pct=round(off_hours/actions*100,0)
| eval watch=case(logins_failed>=10 OR (outside_ips>0 AND logins_failed>=5),"Investigate", logins_failed>=3 OR outside_ips>0 OR off_hours_pct>=50 OR (isnotnull(mfa_pct) AND mfa_pct<100),"Watch", true(),"Normal")
| sort - logins_failed
| table actor watch actions logins_ok logins_failed mfa_pct off_hours_pct outside_ips resources refused''',
                   drill=profile_drill(), colors=WATCH, count=10,
                   note="<b>Investigate</b> = 10+ failed logins, or outside IPs plus 5+ failures · <b>Watch</b> = 3+ failures, outside IP, mostly off-hours, or missing MFA.")),
        row(
            chart("Failed logins per day", HUM + ' | where event="user.login" AND success="false" | timechart span=1d count by actor', stacked=True, legend="right"),
            table("When people work (UTC, 4-hour blocks)", HUM + r'''
| eval blk=printf("%02d-%02d",floor(hour_utc/4)*4,floor(hour_utc/4)*4+3) | chart count over actor by blk''', count=10, drill=profile_drill(),
                  extra='<format type="color"><colorPalette type="minMidMax" minColor="#1B2A41" midColor="#3A6EA5" maxColor="#7FD1FF"></colorPalette><scale type="minMidMax"></scale></format>')),
        row(table("Where they connect from (click a row to open the profile)", HUM + r'''
| where isnotnull(src_ip) | stats count as events, dc(actor) as people, values(actor) as who, count(eval(outcome="denied")) as refused, min(_time) as fs, max(_time) as ls by src_ip external
| eval network=if(external=1,"outside","internal"), first_seen=strftime(fs,"%Y-%m-%d %H:%M"), last_seen=strftime(ls,"%Y-%m-%d %H:%M"), who=mvjoin(mvindex(who,0,2),", ")
| sort - external - refused | table src_ip network people who events refused first_seen last_seen''', count=8)),
        row(html("How to talk about this",
                 "<ul><li>People are predictable as a group: same hours, same places, same tools. Deviation from that is the alert.</li>"
                 "<li>Teleport ties every session to a named person and a second factor, so 'who did this' is never a guess.</li></ul>"
                 f'<div>Next: <a href="id_refusals?cls=human&amp;{PASS}" style="color:#8FB8FF">What was refused for people (L1)</a></div>')),
    ])
    return form("L1 · Humans", "People on the identity layer: MFA, off-hours, unusual networks, password guessing.", "", body)

# --------------------------------------------------------------------------- L1 workloads
WL = '| search actor_class="workload"'
def d_workloads():
    body = "".join([
        crumbs("Workloads (machines)", []),
        banner("Machines and pipelines: are they doing what they were built to do, on schedule?",
               "Which machine identities joined, how long do their credentials live, and does anything look off its rhythm?",
               "Workloads are the deterministic actors. If one goes erratic, something changed: a bug, a leak or a takeover."),
        row(
            single("Workload identities", WL + " | stats dc(actor) as n", "CI, ETL, backup, monitoring bots."),
            single("Bot joins", WL + ' | where event="bot.join" AND outcome="allowed" | stats count as n', "A join is how a bot earns an identity."),
            single("Failed joins", WL + ' | where event="bot.join" AND outcome="denied" | stats count as n', "Expired or unknown token: no identity issued.", warn=True),
            single("Avg credential lifetime", "| search event=\"cert.create\" actor_class=\"workload\" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h", "Hours. Short, renewed, never permanent.", unit="hours"),
            single("Machine share of activity", '| stats count as t, count(eval(actor_class="workload")) as w | eval pct=round(w/t*100,0) | fields pct', "How much of the estate is not a person.", unit="%"),
        ),
        row(table("Machine rhythm: how regular is each bot? (click a row to open the profile)", WL + r'''
| where event="cert.create" | sort 0 actor _time
| streamstats current=f last(_time) as prev by actor | eval gap=_time-prev
| stats count as renewals, avg(gap) as avg_gap, stdev(gap) as sd, avg(ttl_h) as ttl_hours, latest(_time) as ls by actor
| eval avg_gap_min=round(avg_gap/60,0), cv=if(avg_gap>0,round(sd/avg_gap,2),null()), ttl_hours=round(ttl_hours,1)
| eval rhythm=case(isnull(cv),"n/a", cv<0.3,"Clockwork", cv<1,"Mostly regular", true(),"Erratic"), last_seen=strftime(ls,"%Y-%m-%d %H:%M")
| table actor rhythm renewals avg_gap_min cv ttl_hours last_seen''', drill=profile_drill(), count=10,
                   colors='<format type="color" field="rhythm"><colorPalette type="map">{"Clockwork":#3FB68B,"Mostly regular":#F59E3F,"Erratic":#E5534B}</colorPalette></format>',
                   note="cv = spread of the gap between credential renewals divided by the average gap. Near 0 is a metronome.")),
        row(
            chart("Credentials issued per day, by bot", WL + ' | where event="cert.create" | timechart span=1d count by actor', stacked=True, legend="right"),
            table("What each bot can reach", WL + r'''
| stats values(resource) as reaches, dc(resource) as resources, values(db_user) as as_db_user, count(eval(outcome="denied")) as refused by actor
| eval reaches=mvjoin(mvindex(reaches,0,3),", "), as_db_user=mvjoin(as_db_user,", ") | sort - refused''', drill=profile_drill(), count=8)),
        row(table("Failed joins (no identity was issued)", WL + r'''
| where event="bot.join" AND outcome="denied" | sort - _time | head 100
| eval time=strftime(_time,"%Y-%m-%d %H:%M:%S") | table time actor why src_ip uid''', count=6)),
        row(html("How to talk about this",
                 "<ul><li>Bots authenticate with short-lived certificates issued to a bot identity, not a shared key in a config file.</li>"
                 "<li>Their behavior is a rhythm. A break in the rhythm is a stronger signal than any single event.</li></ul>"
                 f'<div>Next: <a href="id_trust?{PASS}" style="color:#8FB8FF">Credential hygiene (L1)</a> · <a href="id_ai_agents?{PASS}" style="color:#8FB8FF">AI agents (L1)</a></div>')),
    ])
    return form("L1 · Workloads (machines)", "Machine identities: joins, credential lifetime, rhythm and reach.", "", body)

# --------------------------------------------------------------------------- L1 refusals
def d_refusals():
    inputs = ('<input type="dropdown" token="cls"><label>Identity class</label><choice value="*">All identities</choice>'
              '<choice value="human">Humans</choice><choice value="ai_agent">AI agents</choice><choice value="workload">Workloads</choice>'
              '<default>*</default><initialValue>*</initialValue></input>')
    D = '| search outcome="denied" actor_class="$cls$"'
    body = "".join([
        crumbs("Refused by policy", []),
        banner("What did policy stop, who tried, and why?",
               "Is the guardrail firing on the right things, and is anyone hammering on a closed door?",
               "A refusal is the system working. An exec wants to know it fires, who it fires on, and whether they come back."),
        row(
            single("Refusals", D + " | timechart span=1d count as x", "Requests Teleport said no to.", trend=True),
            single("Refusal rate", '| search actor_class="$cls$" | stats count as t, count(eval(outcome="denied")) as d | eval pct=if(t>0,round(d/t*100,1),0) | fields pct', "Refused as a share of all activity.", unit="%"),
            single("Identities refused", D + " | stats dc(actor) as n", "How many distinct identities hit a wall."),
            single("Repeat offenders", D + " | stats count as c by actor | where c>=5 | stats count as n", "Identities refused 5+ times.", warn=True),
            single("Retried after a no", '| search actor_class="$cls$"' + r'''
| sort 0 actor _time | streamstats current=f last(outcome) as prev_out last(_time) as prev_t by actor
| eval again=if(outcome="denied" AND prev_out="denied" AND _time-prev_t<600,1,0) | stats sum(again) as n''', "Refused again within 10 minutes.", warn=True),
        ),
        row(chart("Refusals per day, by identity class", D + " | timechart span=1d count by actor_class", stacked=True,
                  colors='{"human":0x4E9BE0,"ai_agent":0xB07CE8,"workload":0x3FB6B6,"system":0x7A8699}'),
            chart("Refusals by control", D + " | stats count by why | sort - count", kind="bar", legend="none")),
        row(table("① Why were requests refused? (click a reason to filter the next table)", D + r'''
| stats count as refusals, dc(actor) as identities, values(actor_class) as classes, latest(_time) as ls by why
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M"), classes=mvjoin(classes,", ") | sort - refusals | table why refusals identities classes last_seen''',
                   drill='<set token="sel_why">$row.why$</set>', count=8)),
        row(table("② Who was refused for that reason? (click an identity to open the profile)", D + r'''
| search why="$sel_why$"
| stats count as refusals, values(cat) as actions, values(resource) as resources, latest(_time) as ls by actor actor_class
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M"), actions=mvjoin(actions,", "), resources=mvjoin(resources,", ") | rename actor_class as class
| sort - refusals | table actor class refusals actions resources last_seen''', drill=profile_drill(), colors=CLASS, count=8, depends="$sel_why$")),
        row(html("How to talk about this",
                 "<ul><li>Refusals are evidence, not failure: each row is Teleport enforcing a rule that a person wrote down.</li>"
                 "<li>What matters is the shape: one identity refused once is a typo. One refused fifty times, or refused again seconds later, is intent.</li></ul>"
                 f'<div>Next: <a href="id_ai_agents?{PASS}" style="color:#8FB8FF">AI agents (L1)</a></div>')),
    ])
    init = '<init><set token="sel_why">*</set></init>'
    return form("L1 · Refused by policy", "Everything Teleport said no to, and to whom.", inputs, body).replace("<fieldset", init + "<fieldset", 1)

# --------------------------------------------------------------------------- L1 governance
CHG = '| where in(event,"user.update","role.created","user.create","role.updated","role.deleted")'
def d_governance():
    body = "".join([
        crumbs("Access & governance", []),
        banner("Who can do what, and who changed that?",
               "Is access defined as code and reviewed, or granted by hand?",
               "Access as code has an author, a review and a history. Access granted by hand has none of the three."),
        row(
            single("Roles defined as code", '| where event="role.created" | stats count as n', "Roles created through the pipeline."),
            single("Access changes by code", CHG + ' | where actor_class!="human" | stats count as n', "Made by a bot/pipeline identity."),
            single("Access changes by people", CHG + ' | where actor_class="human" | stats count as n', "Made by hand. Each needs a reason.", warn=True),
            single("As-code share", CHG + ' | stats count as t, count(eval(actor_class!="human")) as c | eval pct=if(t>0,round(c/t*100,0),0) | fields pct', "Higher is better.", unit="%"),
            single("Roles in use", '| where event="cert.create" | rename "identity.roles{}" as role | mvexpand role | stats dc(role) as n', "Distinct roles behind issued credentials."),
        ),
        row(chart("Access changes per day: code vs people", CHG + ' | eval by=if(actor_class="human","made by people","made by code") | timechart span=1d count by by', stacked=True,
                  colors='{"made by code":0x3FB68B,"made by people":0xF59E3F}'),
            table("Which roles do credentials carry, and for whom?", '| where event="cert.create" | rename "identity.roles{}" as role | mvexpand role | where isnotnull(role) | chart count over role by actor_class', count=10, wrap=False)),
        row(table("Access changes, newest first (click a row to open the person or bot who made it)", CHG + r'''
| sort - _time | head 200 | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S"), made_by=if(actor_class="human","person","code")
| table time actor made_by event name roles uid''', drill=profile_drill(), count=8)),
        row(html("How to talk about this",
                 "<ul><li>Roles and users live in Git and are applied by an operator or Terraform, so every change has an author and a review.</li>"
                 "<li>Changes by a person are allowed but visible, and the gap between the two lines is the governance KPI.</li></ul>"
                 f'<div>Next: <a href="id_estate?{PASS}" style="color:#8FB8FF">What the roles can reach (L1)</a></div>')),
    ])
    return form("L1 · Access & governance", "Roles, access changes, and how much of it is code.", "", body)

# --------------------------------------------------------------------------- L1 estate
def d_estate():
    body = "".join([
        crumbs("Software & hardware reach", []),
        banner("What is reachable, and by which kind of identity?",
               "If one identity is compromised, what could it touch?",
               "Blast radius is the exec question behind every access decision."),
        row(
            single("Kubernetes clusters", '| stats dc(kubernetes_cluster) as n', "Reached through Teleport."),
            single("Apps", '| stats dc(app_name) as n', "Web apps behind the proxy."),
            single("Databases", '| stats dc(db_service) as n', "Sessions are per user, per query, logged."),
            single("Servers", '| stats dc(server_hostname) as n', "SSH through Teleport, no open port 22."),
            single("Client addresses", '| stats dc(src_ip) as n', "Where connections came from."),
            single("Outside addresses", '| where external=1 | stats dc(src_ip) as n', "Public IPs among them.", warn=True),
        ),
        row(table("① Resource inventory (click a resource to see who touched it)", r'''
| where isnotnull(res_type)
| stats count as actions, dc(actor) as identities, dc(eval(if(actor_class="human",actor,null()))) as humans, dc(eval(if(actor_class="ai_agent",actor,null()))) as agents,
        dc(eval(if(actor_class="workload",actor,null()))) as workloads, count(eval(outcome="denied")) as refused, latest(_time) as ls by res_type resource
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M") | sort - actions | table resource res_type identities humans agents workloads actions refused last_seen''',
                   drill='<set token="sel_res">$row.resource$</set>', count=10)),
        row(table("② Who touched it? (click an identity to open the profile)", r'''
| search resource="$sel_res$"
| stats count as actions, count(eval(outcome="denied")) as refused, values(cat) as did, latest(_time) as ls by actor actor_class resource
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M"), did=mvjoin(did,", ") | rename actor_class as class | sort - actions
| table actor class resource actions refused did last_seen''', drill=profile_drill(), colors=CLASS, count=8)),
        row(chart("Reach by identity class and resource type", r'''
| where isnotnull(res_type) | chart count over res_type by actor_class''', stacked=True,
                  colors='{"human":0x4E9BE0,"ai_agent":0xB07CE8,"workload":0x3FB6B6,"system":0x7A8699}'),
            table("Client addresses", r'''
| where isnotnull(src_ip) | stats count as events, dc(actor) as identities, count(eval(outcome="denied")) as refused by src_ip external
| eval network=if(external=1,"outside","internal") | sort - external - refused | table src_ip network identities events refused''', count=8)),
        row(html("How to talk about this",
                 "<ul><li>Each row is a door. The columns say what kind of identity walks through it.</li>"
                 "<li>An AI agent that reaches one database is a small risk. One that reaches everything is a headline.</li></ul>"
                 f'<div>Next: <a href="id_trust?{PASS}" style="color:#8FB8FF">Credential hygiene (L1)</a></div>')),
    ])
    init = '<init><set token="sel_res">*</set></init>'
    return form("L1 · Software & hardware reach", "Clusters, apps, databases, servers and addresses, and who touched them.", "", body).replace("<fieldset", init + "<fieldset", 1)

# --------------------------------------------------------------------------- L1 trust
def d_trust():
    C = '| where event="cert.create"'
    body = "".join([
        crumbs("Root of trust & credentials", []),
        banner("Can we trust the credentials in use?",
               "Do credentials expire, is a second factor always present, and is every action tied to a name?",
               "No shared secrets, no standing privilege, no anonymity. These three KPIs are the promise."),
        row(
            single("Standing privilege", C + " | stats count(eval(ttl_h>24)) as n", "Credentials living over 24h. Target 0.", good_zero=True),
            single("Anonymous actions", '| stats count(eval(actor="unknown")) as n', "No identity attached. Target 0.", good_zero=True),
            single("Logins with a second factor", '| where event="user.login" AND success="true" | stats count as ok, count(eval(isnotnull(mfa_device))) as m | eval pct=if(ok>0,round(m/ok*100,0),0) | fields pct', "Target 100%.", unit="%"),
            single("Average lifetime", C + " | stats avg(ttl_h) as h | eval h=round(h,1) | fields h", "Hours.", unit="hours"),
            single("Longest lifetime", C + " | stats max(ttl_h) as h | eval h=round(h,1) | fields h", "Hours. The worst case is the KPI.", unit="hours"),
            single("Credentials issued", C + " | timechart span=1d count as x", "Each one is a short-lived certificate.", trend=True),
        ),
        row(chart("Credential lifetime by class (hours)", C + " | stats avg(ttl_h) as avg_hours by actor_class | eval avg_hours=round(avg_hours,2)", kind="bar", legend="none"),
            table("Lifetime buckets by class (how many credentials)", C + r'''
| eval bucket=case(ttl_h<=1,"a: up to 1h", ttl_h<=12,"b: 1-12h", ttl_h<=24,"c: 12-24h", true(),"d: over 24h") | chart count over bucket by actor_class''', count=6, wrap=False)),
        row(table("Second factor by person (click a row to open the profile)", r'''
| where actor_class="human" AND event="user.login" AND success="true"
| stats count as logins, count(eval(isnotnull(mfa_device))) as with_mfa by actor
| eval without=logins-with_mfa, mfa_pct=round(with_mfa/logins*100,0) | sort mfa_pct | table actor logins with_mfa without mfa_pct''', drill=profile_drill(), count=8),
            table("Anonymous or unattributed events", r'''
| where actor="unknown" | sort - _time | head 100 | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S") | table time event resource src_ip uid''', count=8)),
        row(html("Honest note", "Hardware root of trust (HSM / TPM key binding) is not modelled in this lab. In production the private key would live in hardware, so a stolen laptop image could not replay it. What this page proves is the software half: short life, second factor, named identity.")),
        row(html("How to talk about this", "<ul><li>Three numbers carry the identity story: standing privilege 0, anonymous 0, MFA 100%.</li><li>Any non-zero is a specific list below it, with a name attached.</li></ul>")),
    ])
    return form("L1 · Root of trust & credentials", "Credential lifetime, second factor, and attribution.", "", body)

# --------------------------------------------------------------------------- L2 actor
def d_actor():
    A = '| search actor="$actor$"'
    inputs = '<input type="text" token="actor"><label>Identity (exact name)</label><default>bot-claude-agent</default><initialValue>bot-claude-agent</initialValue></input>'
    body = "".join([
        crumbs("Identity profile", []),
        banner("Everything one identity did, in the order it makes sense.",
               "Who is this, what is normal for it, and what was different?",
               "This is where an exec gets from a number to a name and then to the raw event."),
        row(
            single("Identity class", A + ' | stats latest(actor_class) as class', "human, ai_agent or workload."),
            single("Actions", A + " | timechart span=1d count as x", "In the window.", trend=True),
            single("Refused", A + ' | where outcome="denied" | stats count as n', "Policy said no.", warn=True),
            single("Tried to change data", A + " | where is_write=1 | stats count as n", "Write statements.", warn=True),
            single("Resources reached", A + " | stats dc(resource) as n", "Distinct."),
            single("Avg credential life", A + ' | where event="cert.create" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h', "Hours.", unit="hours"),
        ),
        row(chart("Daily activity by verdict", A + " | timechart span=1d count by verdict", stacked=True, colors=VERDICT),
            table("Behavior fingerprint: what is normal for this identity?", A + r'''
| eventstats max(_time) as tmax
| stats count as times, min(_time) as fs, max(_time) as ls, max(tmax) as tmax, count(eval(outcome="denied")) as refused by cat
| eventstats sum(times) as tot
| eval share_pct=round(times/tot*100,0), first_seen=strftime(fs,"%Y-%m-%d %H:%M"), last_seen=strftime(ls,"%Y-%m-%d %H:%M"), new_last_24h=if(fs>=tmax-86400,"NEW","")
| sort - times | table cat times share_pct refused new_last_24h first_seen last_seen''', count=8,
                  note="Rows first seen in the last day are new behavior for this identity.")),
        row(table("What it reached", A + r'''
| where isnotnull(resource) | stats count as actions, count(eval(outcome="denied")) as refused, values(cat) as did, latest(_time) as ls by resource res_type
| eval last_seen=strftime(ls,"%Y-%m-%d %H:%M"), did=mvjoin(did,", ") | sort - actions | table resource res_type actions refused did last_seen''', count=6),
            table("Refusals by reason", A + r'''
| where outcome="denied" | stats count as refusals, latest(_time) as ls by why | eval last_seen=strftime(ls,"%Y-%m-%d %H:%M") | sort - refusals''', count=6)),
        row(table("The event trail, newest first (click a row to open the raw event in Search)", A + r'''
| sort - _time | head 300 | eval time=strftime(_time,"%Y-%m-%d %H:%M:%S")
| table time cat resource verdict why what uid''',
                  drill='<link target="_blank">search?q=search%20$src|u$%20sourcetype%3Dteleport%3Aaudit%20uid%3D%22$row.uid|u$%22&amp;earliest=$time.earliest|u$&amp;latest=$time.latest|u$</link>', count=10,
                  note="Every row has a unique event ID: that is the evidence an auditor asks for.")),
        row(html("", f'<div>Back to: <a href="id_ai_agents?{PASS}" style="color:#8FB8FF">AI agents</a> · <a href="id_humans?{PASS}" style="color:#8FB8FF">Humans</a> · <a href="id_workloads?{PASS}" style="color:#8FB8FF">Workloads</a> · <a href="id_refusals?{PASS}" style="color:#8FB8FF">Refused by policy</a></div>')),
    ])
    return form("L2 · Identity profile (one actor)", "One identity end to end: class, fingerprint, reach, refusals, event trail.", inputs, body)

PAGES = {"id_ai_agents": d_agents, "id_humans": d_humans, "id_workloads": d_workloads, "id_refusals": d_refusals,
         "id_governance": d_governance, "id_estate": d_estate, "id_trust": d_trust, "id_actor": d_actor}


# --------------------------------------------------------------------------- hub + nav wiring
def patch_hub(x):
    """Make every tile on the Unified Identity Layer a door into a drill-down. Idempotent."""
    if "id_ai_agents" in x: return x
    P = PASS
    for old, new in (("teleport_overview?form.cls=human&amp;", "id_humans?"),
                     ("teleport_overview?form.cls=ai_agent&amp;", "id_ai_agents?"),
                     ("teleport_overview?form.cls=workload&amp;", "id_workloads?")):
        x = x.replace(old, new)
    def wrap_block(x, head_text, tail_text, view):
        """Turn the dark banner div that contains head_text into a clickable anchor."""
        opener = '<div style="background:#2A2060;border-radius:10px;padding:14px 18px;text-align:center;color:#fff;"><div style="font-size:12px;font-weight:700;letter-spacing:2px;margin-bottom:6px;">' + head_text
        anchor = f'<a href="{view}?{P}" style="display:block;text-decoration:none;background:#2A2060;border-radius:10px;padding:14px 18px;text-align:center;color:#fff;"><div style="font-size:12px;font-weight:700;letter-spacing:2px;margin-bottom:6px;">' + head_text
        if opener not in x or tail_text + "</div>" not in x: return x
        return x.replace(opener, anchor, 1).replace(tail_text + "</div>", tail_text + "</a>", 1)
    x = wrap_block(x, "IDENTITY SECURITY", "<b>$n_pct$%</b> of all activity", "id_refusals")
    x = wrap_block(x, "ACCESS &amp; GOVERNANCE", "access changes made by people instead of code", "id_governance")
    x = wrap_block(x, "HARDWARE ROOT-OF-TRUST", "(production would bind keys to hardware)", "id_trust")
    x = re.sub(r'<div style="(color:#fff;background:rgba\(255,255,255,\.14\);[^"]*)">(<div style="font-size:28px;font-weight:700">\$n_(?:k8s|app|db|srv|ip)\$</div><div[^>]*>[^<]*</div>)</div>',
               lambda m: f'<a href="id_estate?{P}" style="text-decoration:none;{m.group(1)}">{m.group(2)}</a>', x)
    x = x.replace("Click Humans, AI agents or Workloads to open the Command Center filtered to that class.",
                  "Every tile is a door. Click any actor, resource, or band to drill down (L1), then click a name for its profile (L2).")
    # map of the drill-down, right after the diagram row
    chips = "".join(f'<a href="{v}?{P}" style="text-decoration:none;color:#fff;background:#3D3480;border-radius:16px;padding:6px 14px;margin:4px;display:inline-block;font-size:13px">{escape(l)}</a>' for v, l in NAV.items() if v != "id_actor")
    mapp = ('<row><panel><html><div style="text-align:center"><div style="font-size:12px;letter-spacing:2px;color:#8b93a7;margin-bottom:4px">DRILL-DOWN MAP · L0 THIS PAGE → L1 → L2 IDENTITY PROFILE</div>' + chips + '</div></html></panel></row>')
    x = x.replace("</row>", "</row>" + mapp, 1)
    # KPI singles and charts/tables
    parts = x.split("<panel>")
    def swap(title, old, new):
        for k, p in enumerate(parts):
            if p.startswith("<title>" + title):
                parts[k] = p.replace(old, new, 1)
    NONE = '<option name="drilldown">none</option>'
    L = lambda v, e="": f'<drilldown><link target="_self">{v}?{e}{P}</link></drilldown>'
    swap("Standing privilege", NONE, L("id_trust"))
    swap("Anonymous actions", NONE, L("id_trust"))
    swap("Average credential lifetime", NONE, L("id_trust"))
    swap("Who touches what", NONE, L("id_estate"))
    swap("Identity roster", NONE, L("id_actor", "form.actor=$row.actor|u$&amp;"))
    for k, p in enumerate(parts):
        if p.startswith("<title>Why agents matter"):
            parts[k] = p.replace('<option name="charting.legend.placement">none</option>',
                                 '<option name="charting.legend.placement">none</option>' + f'<drilldown><link target="_self">id_refusals?form.cls=$click.value$&amp;{P}</link></drilldown>', 1)
        if p.startswith("<title>Credential lifetime by class"):
            parts[k] = p.replace('<option name="charting.legend.placement">none</option>',
                                 '<option name="charting.legend.placement">none</option>' + f'<drilldown><link target="_self">id_trust?{P}</link></drilldown>', 1)
    return "<panel>".join(parts)

def patch_nav(x):
    if "id_ai_agents" in x: return x
    coll = '  <collection label="Identity drill-down (L1 / L2)">\n' + "".join(f'    <view name="{v}" />\n' for v in NAV) + '  </collection>\n'
    return x.replace('  <view name="tp_studio_identity" />\n', '  <view name="tp_studio_identity" />\n' + coll, 1)

if __name__ == "__main__":
    import xml.etree.ElementTree as ET
    outdir = sys.argv[1] if len(sys.argv) > 1 else VIEWS
    os.makedirs(outdir, exist_ok=True)
    for name, fn in PAGES.items():
        xml = fn(); ET.fromstring(xml)
        with open(os.path.join(outdir, name + ".xml"), "w") as f: f.write(xml)
        print("wrote", name, len(xml))
    hub = os.path.join(outdir, "tp_identity.xml")
    if os.path.exists(hub):
        h = open(hub).read(); n = patch_hub(h); ET.fromstring(n)
        if n != h: open(hub, "w").write(n); print("patched hub links")
        else: print("hub already patched")
    navp = os.path.join(outdir, "..", "nav", "default.xml")
    if os.path.exists(navp):
        h = open(navp).read(); n = patch_nav(h); ET.fromstring(n)
        if n != h: open(navp, "w").write(n); print("patched nav")
        else: print("nav already patched")
