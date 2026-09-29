#!/usr/bin/env python3
"""Build the Teleport demo dashboards (Splunk Simple XML) into the teleport_lab app.
Run:  python3 scripts/build_dashboards.py      (safe to re-run; only rewrites the files it owns)
Note: '$$' in a query means a literal '$' (Simple XML token syntax)."""
import os
from xml.dom import minidom

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UI = os.path.join(ROOT, 'splunk/apps/teleport_lab/default/data/ui')
os.makedirs(os.path.join(UI, 'views'), exist_ok=True); os.makedirs(os.path.join(UI, 'nav'), exist_ok=True)

GREEN, RED, AMBER, BLUE, PURPLE, GREY = '#3FB68B', '#E5534B', '#F0A030', '#4E9BE0', '#B07CE8', '#7A8699'

# NOTE: post-process panels only see fields the base search names, so PRELUDE ends with a full `| fields` list.
PRELUDE = r'''$src$ sourcetype=teleport:audit
| eval actor=coalesce(user, 'identity.user', user_name, "unknown")
| eval actor_type=case(like(actor,"bot-%"),"machine", actor="system","system", like(actor,"%.localhost"),"system", true(),"human")
| eval actor_class=case(actor_type="human","human", match(actor,"^bot-(claude|copilot|lab)"),"ai_agent", actor_type="machine","workload", true(),"system")
| eval outcome=if(success="false" OR like(code,"%W"),"denied","allowed")
| eval src=coalesce('addr.remote','identity.client_ip')
| eval src_ip=replace(src,":\d+$$","")
| eval resource=coalesce(db_service, app_name, server_hostname, kubernetes_cluster)
| eval hour_utc=floor((_time%86400)/3600)
| eval ttl_h=if(event="cert.create", round((strptime(substr('identity.expires',1,19)."+0000","%Y-%m-%dT%H:%M:%S%z")-_time)/3600,2), null())
| eval is_write=if(event="db.session.query" AND match(db_query,"(?i)^\s*(create|drop|alter|insert|update|delete|truncate|grant)"),1,0)
| fields _time, event, code, user, success, error, method, mfa_device, name, roles, login, sid, uid, db_service, db_name, db_user, db_query, app_name, server_hostname, kubernetes_cluster, verb, request_path, response_code, bot_name, user_name, "identity.user", "identity.roles{}", "identity.expires", "identity.client_ip", "addr.remote", demo, actor, actor_type, actor_class, outcome, src, src_ip, resource, hour_utc, ttl_h, is_write'''

TIME = '<input type="time" token="time"><label>Time range</label><default><earliest>-15d@d</earliest><latest>now</latest></default></input>'
SRC = ('<input type="dropdown" token="src"><label>Data source</label>'
       '<choice value="index=teleport_demo">Demo data (synthetic, 15 days)</choice>'
       '<choice value="index=teleport">Live lab data</choice>'
       '<choice value="(index=teleport OR index=teleport_demo)">Both</choice>'
       '<default>index=teleport_demo</default><initialValue>index=teleport_demo</initialValue></input>')

def q(query): return '<search base="base"><query><![CDATA[\n%s\n]]></query></search>' % query.strip()

def single(title, query, unit=None, ranges=None):
    o = '<option name="drilldown">none</option>'
    if unit: o += '<option name="unit">%s</option>' % unit
    if ranges:
        o += ('<option name="useColors">1</option><option name="colorBy">value</option>'
              '<option name="rangeValues">[%s]</option><option name="rangeColors">[%s]</option>'
              % (','.join(str(v) for v in ranges[0]), ','.join('"0x%s"' % c.lstrip('#') for c in ranges[1])))
    else: o += '<option name="colorMode">none</option>'
    return '<panel><title>%s</title><single>%s%s</single></panel>' % (title, q(query), o)

def chart(title, query, kind='column', stacked=True, colors=None, legend='bottom'):
    o = '<option name="charting.chart">%s</option><option name="charting.legend.placement">%s</option>' % (kind, legend)
    if stacked: o += '<option name="charting.chart.stackMode">stacked</option>'
    if colors: o += '<option name="charting.fieldColors">%s</option>' % colors
    return '<panel><title>%s</title><chart>%s%s</chart></panel>' % (title, q(query), o)

def table(title, query, count=10, fmt='', drill=None, wrap=False):
    o = '<option name="count">%d</option>' % count
    o += '<option name="wrap">%s</option>' % ('true' if wrap else 'false')
    o += '<option name="drilldown">%s</option>' % ('row' if drill else 'none')
    if drill: o += '<drilldown><set token="%s">$row.%s$</set></drilldown>' % drill
    return '<panel><title>%s</title><table>%s%s%s</table></panel>' % (title, q(query), o, fmt)

def html(title, body, depends=''):
    # Splunk renders <html> panels only when the markup sits directly inside the tag (NOT in CDATA),
    # so the body must be well-formed XML: self-closed <br/>, escaped &amp;.
    body = body.replace('<br>', '<br/>')
    return '<panel%s><title>%s</title><html>%s</html></panel>' % (depends, title, body)

def row(*p): return '<row>%s</row>' % ''.join(p)

def form(label, desc, inputs, extra, rows, post=''):
    return ('<form version="1.1" theme="dark"><label>%s</label><description>%s</description>'
            '<fieldset submitButton="false" autoRun="true">%s</fieldset>'
            '<search id="base"><query><![CDATA[\n%s\n%s\n]]></query><earliest>$time.earliest$</earliest><latest>$time.latest$</latest></search>'
            '%s%s</form>' % (label, desc, inputs, PRELUDE, extra, post, ''.join(rows)))

OUTCOME_COLORS = '{"allowed":"%s","denied":"%s"}' % (GREEN, RED)
ACTOR_COLORS = '{"human":"%s","machine":"%s","system":"%s"}' % (BLUE, PURPLE, GREY)
def colormap(field, mapping):
    return '<format type="color" field="%s"><colorPalette type="map">{%s}</colorPalette></format>' % (
        field, ','.join('"%s":%s' % (k, v) for k, v in mapping.items()))

views = {}

# =============================== 0. TRUST SCORECARD ===============================
views['tp_scorecard'] = form('0 · Trust Scorecard',
  'Executive view: are credentials short-lived, is every action attributed, and what did policy block? (Demo data is synthetic.)',
  TIME + SRC, '', [
  row(
    single('Credentials issued', '| search event="cert.create" | stats count'),
    single('Short-lived (12h or less)', '| search event="cert.create" | stats count as certs, count(eval(ttl_h<=12)) as short | eval pct=if(certs>0, round(short/certs*100,1), 0) | fields pct', unit='%'),
    single('Long-lived credentials (over 24h)', '| search event="cert.create" | stats count(eval(ttl_h>24)) as long_lived', ranges=([0], [GREEN, RED])),
    single('Average credential lifetime', '| search event="cert.create" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h', unit='hours'),
    single('Actions blocked by policy', '| where outcome="denied" | stats count', ranges=([0], [GREEN, AMBER])),
    single('Machine share of activity', '| stats count as total, count(eval(actor_type="machine")) as m | eval pct=if(total>0, round(m/total*100,0), 0) | fields pct', unit='%'),
  ),
  row(
    chart('Credentials issued per day: people vs machines', '| search event="cert.create" | timechart span=1d count by actor_type', colors=ACTOR_COLORS),
    chart('Average credential lifetime (hours)', '| search event="cert.create" | stats avg(ttl_h) as avg_hours by actor_type | eval avg_hours=round(avg_hours,2)', kind='bar', stacked=False, legend='none', colors=ACTOR_COLORS),
  ),
  row(
    chart('Blocked by policy, per day', '| where outcome="denied" | timechart span=1d count by event', colors='{}'),
    table('What was blocked, and why', '| where outcome="denied" | eval reason=substr(error,1,95) | stats count by actor, event, reason | sort - count', count=6, wrap=True),
  ),
  row(html('How to read this page', '''
<div style="display:flex;gap:28px;flex-wrap:wrap;line-height:1.5">
 <div style="flex:1;min-width:260px"><b>Before (PPI Financial Services, customer story)</b><br>Manual certificate management, complex onboarding, fragmented access workflows.</div>
 <div style="flex:1;min-width:260px"><b>After</b><br>Single sign-on, short-lived access, every session audited, access policy managed as code (Kubernetes operator + Terraform).</div>
 <div style="flex:1;min-width:260px"><b>What this lab shows</b><br>The same idea for humans <i>and</i> machines <i>and</i> AI agents: credentials that expire in hours, each action tied to an identity, denials recorded. Source for the PPI FS points: Teleport customer story.</div>
</div>'''))
])


OWN_IAC = ('<panel><title>Access as code: role and user changes</title><table><search><query><![CDATA[\n'
  '$src$ sourcetype=teleport:audit event IN ("role.created","user.create","user.update") | sort - _time '
  '| eval by=user | table _time by event name roles\n]]></query><earliest>$time.earliest$</earliest><latest>$time.latest$</latest></search>'
  '<option name="count">8</option><option name="drilldown">none</option></table></panel>')

# =============================== 1. DAY-ONE ONBOARDING ===============================
NEWHIRE = ('<input type="dropdown" token="newhire"><label>New hire</label><choice value="*">All new hires</choice>'
           '<default>*</default><initialValue>*</initialValue>'
           '<fieldForLabel>name</fieldForLabel><fieldForValue>name</fieldForValue>'
           '<search><query>$src$ sourcetype=teleport:audit event="user.create" | stats count by name</query><earliest>-30d@d</earliest><latest>now</latest></search></input>')
ONB = '''| eval subject=if(in(event,"user.create","reset_password_token.create"), name, actor)
| eventstats count(eval(event="user.create")) as is_new by subject
| where is_new>0 AND subject!="bot-terraform"
| search subject="$newhire$"'''
STEP = '''| eval step=case(event="user.create","1 Account created (as code)",event="reset_password_token.create","2 Invite issued",event="mfa.add","3 MFA enrolled",event="user.login","4 First login",event="cert.create","5 Short-lived certificate issued",event="session.start","6 SSH access",event="db.session.start","6 Database access",event="app.session.start","6 App access")'''
views['tp_onboarding'] = form('1 · Day-One Onboarding',
  'Scene 1: a new engineer goes from no account to working access. No certificate files, no ticket queue.',
  TIME + SRC + NEWHIRE, ONB, [
  row(
    single('New engineers onboarded', '| stats dc(subject) as hires'),
    single('Minutes: account created to first access', '| stats min(eval(if(event="user.create",_time,null()))) as created, min(eval(if(in(event,"session.start","db.session.start","app.session.start"),_time,null()))) as first_access by subject | eval minutes=round((first_access-created)/60,1) | stats avg(minutes) as m | eval m=round(m,1) | fields m', unit='min'),
    single('Logins protected by MFA', '| search event="user.login" success="true" | stats count(eval(isnotnull(mfa_device))) as with_mfa, count as total | eval pct=if(total>0, round(with_mfa/total*100,0), 0) | fields pct', unit='%'),
  ),
  row(
    table('The journey, step by step', '| where in(event,"user.create","reset_password_token.create","mfa.add","user.login","cert.create","session.start","db.session.start","app.session.start") ' + STEP + ' | where isnotnull(step) | sort 0 subject _time | table _time subject step outcome', count=12),
    chart('Roles handed out (certificates by role)', '| search event="cert.create" | rename "identity.roles{}" as role | stats count by role', kind='pie', stacked=False, legend='right'),
  ),
  row(
    OWN_IAC,
    html('The old way vs the Teleport way', '''
<div style="display:flex;gap:28px;flex-wrap:wrap;line-height:1.6">
 <div style="flex:1;min-width:280px"><b>The old way</b><ol><li>Open a ticket</li><li>Wait for someone to create keys or certificates</li><li>Copy files to the laptop, keep them safe forever</li><li>Ask again for each new system</li></ol></div>
 <div style="flex:1;min-width:280px"><b>The Teleport way</b><ol><li>Account and role created <i>as code</i> (Terraform / operator)</li><li>Engineer logs in once with SSO/MFA</li><li>Short-lived certificate is issued automatically</li><li>Access matches the role; every session is audited</li></ol></div>
</div>'''),
  ),
])

# =============================== 2. AUDITOR EVIDENCE ===============================
WHO = '<input type="text" token="who"><label>Identity (name or *)</label><default>*</default><initialValue>*</initialValue></input>'
RES = '<input type="text" token="res"><label>Database (name or *)</label><default>*</default><initialValue>*</initialValue></input>'
HEAT = '<format type="color"><colorPalette type="minMidMax" minColor="#1B2A41" midColor="#3A6EA5" maxColor="#7FD1FF"></colorPalette><scale type="minMidMax"></scale></format>'
views['tp_auditor'] = form('2 · Auditor Evidence',
  'Scene 2: "Who touched the database, when, and what did they run?" Every answer comes from the audit log.',
  TIME + SRC + WHO + RES,
  '| search in(event,"db.session.start","db.session.query","db.session.end") resource="$res$" actor="$who$"'.replace('in(event,"db.session.start","db.session.query","db.session.end")', 'event IN ("db.session.start","db.session.query","db.session.end")'), [
  row(
    single('Database sessions', '| search event="db.session.start" outcome="allowed" | stats count'),
    single('Identities that connected', '| search event="db.session.start" outcome="allowed" | stats dc(actor) as ids'),
    single('Queries on record', '| search event="db.session.query" | stats count'),
    single('Connections denied', '| search event="db.session.start" outcome="denied" | stats count', ranges=([0], [GREEN, RED])),
    single('Write attempts', '| stats sum(is_write) as writes', ranges=([0], [GREEN, AMBER])),
  ),
  row(
    table('Who accessed the database', '| stats count(eval(event="db.session.start" AND outcome="allowed")) as sessions, count(eval(event="db.session.query")) as queries, sum(is_write) as write_attempts, dc(db_user) as db_users, min(_time) as first_seen, max(_time) as last_seen by actor, actor_type | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M"), last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - queries', count=8),
    chart('Database activity per day', '| search event="db.session.query" | timechart span=1d count by actor limit=8 useother=f'),
  ),
  row(
    table('When is the database used? (UTC hour, by identity)', '| search event="db.session.start" | eval hr=printf("%02d",hour_utc) | chart count over actor by hr', count=10, fmt=HEAT),
  ),
  row(
    table('Full query log (evidence trail)', '| search event="db.session.query" | eval kind=if(is_write=1,"WRITE","read") | sort - _time | table _time actor actor_type db_user kind db_query sid uid', count=10, wrap=True,
          fmt=colormap('kind', {'WRITE': AMBER, 'read': GREEN})),
  ),
  row(html('Questions an auditor asks, and where the answer lives', '''
<table style="width:100%;line-height:1.7"><tr><td><b>Who accessed it?</b></td><td>"Who accessed the database" table</td></tr>
<tr><td><b>What did they run?</b></td><td>"Full query log", including the unique event ID (uid)</td></tr>
<tr><td><b>Was it allowed?</b></td><td>Connections denied and the Security Watch dashboard</td></tr>
<tr><td><b>Was the credential short-lived?</b></td><td>Trust Scorecard: credential lifetime</td></tr>
<tr><td><b>Can I export it?</b></td><td>Use the Export button on any table or search</td></tr></table>
<i>This supports evidence for access-control and logging requirements (for example C5, KRITIS, DORA). It does not certify compliance by itself.</i>'''))
])

# =============================== 3. AI AGENT GOVERNANCE ===============================
AGENT = ('<input type="dropdown" token="agent"><label>Machine identity</label><choice value="bot-*">All machine identities</choice>'
         '<default>bot-*</default><initialValue>bot-*</initialValue><fieldForLabel>a</fieldForLabel><fieldForValue>a</fieldForValue>'
         '<search><query>$src$ sourcetype=teleport:audit | eval a=coalesce(user,\'identity.user\') | where like(a,"bot-%") | stats count by a</query><earliest>-30d@d</earliest><latest>now</latest></search></input>')
VERDICTS = {'Clean read-only': GREEN, 'Write attempted': AMBER, 'Blocked at Teleport': RED, 'Blocked + write attempt': RED}
views['tp_agent'] = form('3 · AI Agent Governance',
  'Scene 3: Claude decides what to try. Teleport decides what is allowed. Splunk records what happened.',
  TIME + SRC + AGENT, '| search actor="$agent$"', [
  row(
    single('Agent database sessions', '| search event="db.session.start" outcome="allowed" | stats count'),
    single('Read queries', '| search event="db.session.query" is_write=0 | stats count'),
    single('Write attempts', '| stats sum(is_write) as writes', ranges=([0], [GREEN, AMBER])),
    single('Blocked at Teleport', '| search event="db.session.start" outcome="denied" | stats count', ranges=([0], [GREEN, RED])),
    single('Credential lifetime', '| search event="cert.create" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h', unit='hours'),
  ),
  row(
    chart('Intent vs outcome, per day', '| search event IN ("db.session.query","db.session.start") | eval kind=case(is_write=1,"write attempt",event="db.session.start" AND outcome="denied","blocked by Teleport",event="db.session.query","read (allowed)") | where isnotnull(kind) | timechart span=1d count by kind',
          colors='{"read (allowed)":"%s","write attempt":"%s","blocked by Teleport":"%s"}' % (GREEN, AMBER, RED)),
    table('Blast radius: what can each identity reach?', '| stats dc(resource) as resources, values(resource) as reaches, values(db_user) as as_db_user, avg(ttl_h) as avg_cert_hours by actor | eval avg_cert_hours=round(avg_cert_hours,1)', count=6),
  ),
  row(
    table('Agent sessions (click a row to replay it)', '| search event IN ("db.session.start","db.session.query") | stats min(_time) as started, count(eval(event="db.session.query")) as queries, sum(is_write) as write_attempts, count(eval(event="db.session.start" AND outcome="denied")) as blocked_connects, values(db_user) as db_user by sid, actor | eval verdict=case(blocked_connects>0 AND write_attempts>0,"Blocked + write attempt", blocked_connects>0,"Blocked at Teleport", write_attempts>0,"Write attempted", true(),"Clean read-only") | sort - started | table started actor verdict queries write_attempts blocked_connects db_user sid',
          count=8, drill=('sel_sid', 'sid'), fmt=colormap('verdict', VERDICTS)),
  ),
  row(
    '<panel depends="$sel_sid$"><title>Session replay</title><table>%s<option name="count">15</option><option name="wrap">true</option><option name="drilldown">none</option></table></panel>' % q(
      '| search sid="$sel_sid$" | sort 0 _time | table _time event db_user db_query outcome'),
  ),
  row(html('How to say it in the demo', '''
<div style="line-height:1.6"><b>Claude decides. Teleport decides what Claude is allowed to do. Splunk records what actually happened.</b><br>
The agent has its own machine identity (not a human admin), a read-only role, and a credential that lives about an hour.<br>
<i>Honest detail:</i> a write attempt that shows as "allowed" in Teleport means the query was forwarded and logged. The read-only database user is what refuses the change. Teleport itself blocks the request when the agent asks for a database user its role does not allow (the red "Blocked at Teleport" rows).</div>'''))
])

# =============================== 4. SECURITY WATCH ===============================
EXTRA_SEC = r'''| eval external=if(isnotnull(src_ip) AND src_ip!="" AND NOT (cidrmatch("10.0.0.0/8",src_ip) OR cidrmatch("172.16.0.0/12",src_ip) OR cidrmatch("192.168.0.0/16",src_ip) OR cidrmatch("127.0.0.0/8",src_ip)),1,0)
| eval offhours=if(actor_type="human" AND (hour_utc<6 OR hour_utc>=19),1,0)
| eval signal=case(event="user.login" AND success="false","Failed login", event="auth" AND outcome="denied","Denied SSH", event="db.session.start" AND outcome="denied","Denied DB connect", event="kube.request" AND outcome="denied","Denied Kubernetes", is_write=1,"Write attempt", in(event,"user.update","role.created","user.create") AND actor_type="human","Change outside code", actor_type="human" AND external=1,"Unusual source IP", offhours=1,"Off-hours access")'''
views['tp_security'] = form('4 · Security Watch',
  'Scene 4: something looks wrong. One place to see failed logins, denials, odd hours, odd locations and bot misbehavior.',
  TIME + SRC, EXTRA_SEC, [
  row(
    single('Failed logins', '| search event="user.login" success="false" | stats count', ranges=([0], [GREEN, AMBER])),
    single('Brute-force bursts (5+ fails in 5 min)', '| search event="user.login" success="false" | bin _time span=5m | stats count by _time, actor | where count>=5 | stats count', ranges=([0], [GREEN, RED])),
    single('Off-hours human activity (events)', '| search offhours=1 | stats count', ranges=([0], [GREEN, AMBER])),
    single('Unusual source IPs (people)', '| search actor_type="human" external=1 | stats dc(src_ip) as ips', ranges=([0], [GREEN, RED])),
    single('Bot actions denied', '| search actor_type="machine" outcome="denied" | stats count', ranges=([0], [GREEN, RED])),
    single('Access changes made by people', '| search event IN ("user.update","role.created","user.create") actor_type="human" | stats count', ranges=([0], [GREEN, AMBER])),
    single('Bulk reads (15+ queries in 5 min)', '| search event="db.session.query" | bin _time span=5m | stats count by _time, actor | where count>=15 | stats count', ranges=([0], [GREEN, RED])),
  ),
  row(
    chart('Risk signals over time', '| where isnotnull(signal) | timechart span=1d count by signal',
          colors='{"Failed login":"%s","Denied SSH":"%s","Denied DB connect":"%s","Write attempt":"%s","Unusual source IP":"%s","Off-hours access":"%s","Change outside code":"%s","Denied Kubernetes":"%s"}' % (AMBER, RED, RED, PURPLE, BLUE, GREY, AMBER, RED)),
    table('Signals by identity', '| where isnotnull(signal) | stats count, min(_time) as first_seen, max(_time) as last_seen, values(src_ip) as from_ip by actor, signal | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M"), last_seen=strftime(last_seen,"%Y-%m-%d %H:%M") | sort - count', count=8),
  ),
  row(
    table('Brute-force detector', '| search event="user.login" success="false" | bin _time span=5m | stats count, values(src_ip) as from_ip by _time, actor | where count>=5 | sort - _time', count=5),
    table('Unusual source IPs (people)', '| search actor_type="human" external=1 | stats count, min(_time) as first_seen by actor, src_ip | eval first_seen=strftime(first_seen,"%Y-%m-%d %H:%M") | sort - first_seen', count=5),
  ),
  row(
    table('Off-hours access (before 06:00 or after 19:00 UTC)', '| search offhours=1 | sort - _time | table _time actor event resource src_ip', count=6),
    table('Machine identities denied', '| search actor_type="machine" outcome="denied" | eval reason=substr(error,1,110) | sort - _time | table _time actor event resource reason', count=6, wrap=True),
  ),
  row(
    table('Access changes made by people, not code', '| search event IN ("user.update","role.created","user.create") actor_type="human" | sort - _time | table _time actor event name roles', count=5),
    table('Bulk data reads (15+ queries in 5 min)', '| search event="db.session.query" | bin _time span=5m | stats count, values(resource) as resource by _time, actor | where count>=15 | sort - _time', count=5),
    table('Kubernetes: production exec and denials', '| search event="kube.request" kubernetes_cluster="k8s-prod" (outcome="denied" OR request_path="*exec*") | eval what=if(outcome="denied","DENIED","exec") | sort - _time | table _time actor verb request_path response_code what', count=6, fmt=colormap('what', {'DENIED': RED, 'exec': AMBER})),
  ),
])

exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dash_identity_and_drill.py'), encoding='utf-8').read())

# =============================== write files + nav ===============================
for name, xml in views.items():
    minidom.parseString(xml)                                  # fail loudly on bad XML
    with open(os.path.join(UI, 'views', name + '.xml'), 'w', encoding='utf-8') as f: f.write(xml + '\n')
    print('wrote', name, len(xml), 'bytes')

# Patch the original Command Center once: add data-source toggle + 15-day default.
p = os.path.join(UI, 'views', 'teleport_overview.xml'); s = open(p).read()
if '$src$' not in s:
    s = s.replace('index=teleport sourcetype=teleport:audit', '$src$ sourcetype=teleport:audit')
    s = s.replace('</input>\n    <input type="dropdown" token="actor_type">', '</input>\n    ' + SRC + '\n    <input type="dropdown" token="actor_type">', 1)
    s = s.replace('<label>Teleport Command Center</label>', '<label>Command Center (all events)</label>').replace('-7d@d', '-15d@d')
    minidom.parseString(s); open(p, 'w').write(s); print('patched teleport_overview')
else: print('teleport_overview already patched')

nav = '''<nav search_view="search">
  <view name="tp_scorecard" default="true" />
  <view name="tp_studio_scorecard" />
  <view name="tp_identity" />
  <view name="tp_studio_identity" />
  <collection label="Demo scenes (Studio)">
    <view name="tp_studio_onboarding" />
    <view name="tp_studio_auditor" />
    <view name="tp_studio_agent" />
    <view name="tp_studio_security" />
  </collection>
  <collection label="Demo scenes (classic)">
    <view name="tp_onboarding" />
    <view name="tp_auditor" />
    <view name="tp_agent" />
    <view name="tp_security" />
  </collection>
  <view name="teleport_overview" />
  <view name="search" />
</nav>
'''
minidom.parseString(nav); open(os.path.join(UI, 'nav', 'default.xml'), 'w').write(nav); print('wrote nav')
