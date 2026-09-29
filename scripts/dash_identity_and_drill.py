# Part 2 of build_dashboards.py (exec'd by it, shares its helpers): the Command Center drill-down and the Unified Identity Layer.
CLASS_COLORS = '{"human":"%s","ai_agent":"%s","workload":"#3FB6B6","system":"%s"}' % (BLUE, PURPLE, GREY)
CLASS_MAP = {'human': BLUE, 'ai_agent': PURPLE, 'workload': '#3FB6B6', 'system': GREY}
HEAT = '<format type="color"><colorPalette type="minMidMax" minColor="#1B2A41" midColor="#3A6EA5" maxColor="#7FD1FF"></colorPalette><scale type="minMidMax"></scale></format>'

def single_x(title, query, drill_xml, unit=None, ranges=None):
    o = '<option name="drilldown">all</option>' + drill_xml
    if unit: o += '<option name="unit">%s</option>' % unit
    if ranges:
        o += ('<option name="useColors">1</option><option name="colorBy">value</option><option name="rangeValues">[%s]</option><option name="rangeColors">[%s]</option>'
              % (','.join(str(v) for v in ranges[0]), ','.join('"0x%s"' % c.lstrip('#') for c in ranges[1])))
    else: o += '<option name="colorMode">none</option>'
    return '<panel><title>%s</title><single>%s%s</single></panel>' % (title, q(query), o)

def table_x(title, query, drill_xml='', count=8, fmt='', wrap=True):
    o = '<option name="count">%d</option><option name="wrap">%s</option><option name="drilldown">%s</option>%s' % (
        count, 'true' if wrap else 'false', 'row' if drill_xml else 'none', drill_xml)
    return '<panel><title>%s</title><table>%s%s%s</table></panel>' % (title, q(query), o, fmt)

DENY = r"""| eval deny_reason=if(outcome="denied", case(like(error,"%second factor%"),"Bad credentials or MFA", like(error,"%access to db denied%"),"Database access refused by role", like(error,"%valid principals%"),"SSH login not allowed for this identity", like(error,"%token%"),"Join token bad or expired", event="kube.request","Kubernetes request forbidden", true(),"Other policy denial"), null())
| eval control=case(deny_reason="Bad credentials or MFA","Authentication and MFA", deny_reason="Database access refused by role","Role-based access control (RBAC)", deny_reason="SSH login not allowed for this identity","Certificate logins (RBAC)", deny_reason="Join token bad or expired","Machine ID join token (short TTL)", deny_reason="Kubernetes request forbidden","Kubernetes access rules (RBAC)", true(),"Policy")
| eval meaning=case(deny_reason="Bad credentials or MFA","The password or second factor was wrong. Teleport refused before granting any access.", deny_reason="Database access refused by role","The identity asked for a database user its role does not allow. Least privilege held.", deny_reason="SSH login not allowed for this identity","The certificate has no permission to log in as that account on that server.", deny_reason="Join token bad or expired","A bot tried to join with an expired or unknown token, so it received no identity at all.", deny_reason="Kubernetes request forbidden","The role does not allow this cluster action in this environment (for example production).", true(),"Refused by policy.")"""

RESET = '<drilldown><set token="form.d_reason">*</set><set token="form.d_actor">*</set><unset token="d_uid"></unset></drilldown>'
L1 = '<drilldown><set token="form.d_reason">$row.deny_reason$</set><set token="form.d_actor">*</set><unset token="d_uid"></unset></drilldown>'
L2 = '<drilldown><set token="form.d_actor">$row.actor$</set><unset token="d_uid"></unset></drilldown>'
L3 = '<drilldown><set token="d_uid">$row.uid$</set></drilldown>'
CLS = ('<input type="dropdown" token="cls"><label>Identity class</label><choice value="*">All identities</choice><choice value="human">Humans</choice>'
       '<choice value="ai_agent">AI agents</choice><choice value="workload">Workloads (services, CI)</choice><choice value="system">Teleport system</choice>'
       '<default>*</default><initialValue>*</initialValue></input>')
D_REASON = '<input type="text" token="d_reason"><label>Why (drill)</label><default>*</default><initialValue>*</initialValue></input>'
D_ACTOR = '<input type="text" token="d_actor"><label>Who (drill)</label><default>*</default><initialValue>*</initialValue></input>'

LEVEL4 = ('<panel depends="$d_uid$"><title>Level 4 · Evidence card: the raw audit event</title><table><search><query><![CDATA[\n'
          '$src$ sourcetype=teleport:audit uid="$d_uid$" | eval actor=coalesce(user,\'identity.user\',user_name) | eval evidence=_raw | table _time actor event code evidence\n'
          ']]></query><earliest>$time.earliest$</earliest><latest>$time.latest$</latest></search>'
          '<option name="wrap">true</option><option name="drilldown">none</option><option name="count">1</option></table></panel>')

# =============================== COMMAND CENTER (with denied/failed drill-down) ===============================
views['teleport_overview'] = form('Command Center (all events)',
  'Everything in one place. Click "Denied / failed" to drill into WHY, then WHO, then the exact events. Your filters stay applied at every level.',
  TIME + SRC + CLS + D_REASON + D_ACTOR,
  '| search actor_class="$cls$"\n' + DENY, [
  row(
    single('Total events', '| stats count'),
    single_x('Denied / failed: click to drill', '| where outcome="denied" | stats count', RESET, ranges=([0], [GREEN, RED])),
    single('Failed logins', '| search event="user.login" success="false" | stats count', ranges=([0], [GREEN, AMBER])),
    single('AI-agent actions', '| search actor_class="ai_agent" | stats count'),
    single('Workload (service) actions', '| search actor_class="workload" | stats count'),
    single('Distinct identities', '| stats dc(actor) as identities'),
  ),
  row(
    chart('Allowed vs denied over time', '| timechart count by outcome', colors=OUTCOME_COLORS),
    chart('Activity by identity class', '| timechart count by actor_class', kind='area', colors=CLASS_COLORS),
  ),
  row(html('Denied / failed: why? (guided drill-down)', '''
<div style="line-height:1.6">
<b>Use case: "Why was the AI agent refused?"</b> Click a reason in Level 1, then an identity in Level 2, then an event in Level 3. Level 4 shows the raw evidence.<br/>
<b>Filters that stay applied at every level:</b> Identity class, Why and Who (the boxes at the top; edit or clear them any time), plus the time range and data source. Tip: set <i>Identity class</i> to <b>AI agents</b> first to keep the whole story about non-deterministic actors.<br/>
Now showing: class = <b>$cls$</b> · why = <b>$d_reason$</b> · who = <b>$d_actor$</b> (an asterisk means "all")
</div>''')),
  row(
    table_x('Level 1 · Why were requests denied?', '''
| where outcome="denied"
| stats count as denials, dc(actor) as identities, values(actor_class) as classes, latest(_time) as last_seen by deny_reason, control, meaning
| eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M")
| sort - denials
| table deny_reason denials identities classes control meaning last_seen''', L1, count=6),
  ),
  row(
    table_x('Level 2 · Who was denied? (for the reason chosen above)', '''
| where outcome="denied"
| search deny_reason="$d_reason$"
| stats count as denials, values(event) as events, values(resource) as resources, latest(_time) as last_seen by actor, actor_class
| eval last_seen=strftime(last_seen,"%Y-%m-%d %H:%M")
| sort - denials''', L2, count=6, fmt=colormap('actor_class', CLASS_MAP)),
    chart('Denials by identity class, per day', '| where outcome="denied" | search deny_reason="$d_reason$" | timechart span=1d count by actor_class', colors=CLASS_COLORS),
  ),
  row(
    table_x('Level 3 · The events (click one for the evidence card)', '''
| where outcome="denied"
| search deny_reason="$d_reason$" actor="$d_actor$"
| eval why=substr(error,1,140)
| sort - _time
| table _time actor actor_class event code resource src why uid''', L3, count=6, fmt=colormap('actor_class', CLASS_MAP)),
    chart('This identity: allowed vs denied over time', '| search actor="$d_actor$" | timechart span=1d count by outcome', colors=OUTCOME_COLORS),
  ),
  '<row>%s%s</row>' % (LEVEL4, html('What the evidence card proves', '''
<div style="line-height:1.6"><b>Who</b> (identity), <b>what</b> (event and code), <b>when</b> (timestamp), <b>from where</b> (source address) and <b>which control refused it</b> (Level 1).<br/>
Every event has a unique ID (<i>uid</i>) so it can be found again.<br/>
<a href="tp_auditor?form.who=$d_actor|u$&amp;form.src=$src|u$&amp;form.time.earliest=$time.earliest|u$&amp;form.time.latest=$time.latest|u$">Open this identity in Auditor Evidence →</a></div>''', depends=' depends="$d_uid$"')),
  row(
    table_x('Machine and agent activity', '''
| search actor_class IN ("ai_agent","workload") event IN ("db.session.start","db.session.query","auth","bot.join","kube.request")
| eval detail=substr(coalesce(db_query, error, request_path, method), 1, 100)
| sort - _time
| table _time actor actor_class event outcome resource detail''', count=8, fmt=colormap('outcome', {'allowed': GREEN, 'denied': RED})),
    table_x('Write-attempt detector', '''
| search event="db.session.query"
| stats count(eval(is_write=1)) as write_attempts, count as total_queries by actor, actor_class
| sort - write_attempts''', count=8, fmt=colormap('actor_class', CLASS_MAP)),
  ),
  row(
    chart('Resources touched', '| where isnotnull(resource) | chart count over resource by actor_class', colors=CLASS_COLORS),
    chart('Event types', '| stats count by event | sort - count | head 12', kind='bar', stacked=False, legend='none'),
  ),
  row(table_x('Live event stream (click a row to open the raw event in Search)', '| sort - _time | head 100 | table _time actor actor_class event outcome code resource src uid',
    '<drilldown><link target="_blank">/en-US/app/search/search?q=search%20$src|u$%20uid%3D%22$row.uid|u$%22&amp;earliest=$time.earliest|u$&amp;latest=$time.latest|u$</link></drilldown>', count=8, wrap=False)),
])

# =============================== UNIFIED IDENTITY LAYER ===============================
def _tile(cls, num, label, icon):
    href = 'teleport_overview?form.cls=%s&amp;form.src=$src|u$&amp;form.time.earliest=$time.earliest|u$&amp;form.time.latest=$time.latest|u$' % cls
    return ('<a href="%s" style="text-decoration:none;color:#fff;background:rgba(255,255,255,.14);border-radius:10px;padding:10px 16px;margin:4px;display:inline-block;min-width:118px;text-align:center">'
            '<div style="font-size:28px;font-weight:700">%s</div><div style="font-size:12px;letter-spacing:1px">%s %s</div></a>') % (href, num, icon, label)
def _plain(num, label, icon):
    return ('<div style="color:#fff;background:rgba(255,255,255,.14);border-radius:10px;padding:10px 16px;margin:4px;display:inline-block;min-width:118px;text-align:center">'
            '<div style="font-size:28px;font-weight:700">%s</div><div style="font-size:12px;letter-spacing:1px">%s %s</div></div>') % (num, icon, label)
BAR = 'background:#2A2060;border-radius:10px;padding:14px 18px;text-align:center;color:#fff;'
ARROW = '<div style="text-align:center;color:#8b93a7;font-size:20px;line-height:24px">↑</div>'
LBL = 'font-size:12px;font-weight:700;letter-spacing:2px;margin-bottom:6px;'
STACK = ('<div style="max-width:980px;margin:0 auto">'
  '<div style="' + BAR + '"><div style="' + LBL + '">IDENTITY SECURITY</div><span style="font-size:24px;font-weight:700">$n_den$</span> requests refused by policy · <b>$n_pct$%</b> of all activity</div>' + ARROW +
  '<div style="' + BAR + '"><div style="' + LBL + '">ACCESS &amp; GOVERNANCE</div><b>$n_roles$</b> roles defined as code · <b>$n_ppl$</b> access changes made by people instead of code</div>' + ARROW +
  '<div style="background:linear-gradient(120deg,#3D6BB3,#5B3E96);border-radius:10px;padding:16px 18px;color:#fff">'
  '<div style="' + LBL + 'text-align:center">UNIFIED IDENTITY LAYER</div><div style="display:flex;flex-wrap:wrap;justify-content:space-around;gap:12px;border-top:1px solid rgba(255,255,255,.35);padding-top:12px">'
  '<div style="text-align:center"><div style="' + LBL + '">NON-DETERMINISTIC ACTORS</div>' + _tile('human', '$n_h$', 'HUMANS', '👤') + _tile('ai_agent', '$n_a$', 'AI AGENTS', '🤖') + _tile('workload', '$n_w$', 'WORKLOADS', '⚙️') + '</div>'
  '<div style="text-align:center"><div style="' + LBL + '">SOFTWARE</div>' + _plain('$n_k8s$', 'K8S CLUSTERS', '☸') + _plain('$n_app$', 'APPS', '▭') + _plain('$n_db$', 'DATABASES', '🛢') + '</div>'
  '<div style="text-align:center"><div style="' + LBL + '">HARDWARE</div>' + _plain('$n_srv$', 'SERVERS', '🖥') + _plain('$n_ip$', 'CLIENT ADDRESSES', '💻') + '</div>'
  '</div></div>' + ARROW +
  '<div style="' + BAR + '"><div style="' + LBL + '">HARDWARE ROOT-OF-TRUST</div><b>$n_mfa$%</b> of successful logins used a registered MFA device · HSM / TPM attestation is not modelled in this lab (production would bind keys to hardware)</div>'
  '<div style="text-align:center;color:#8b93a7;font-size:12px;margin-top:8px">Click Humans, AI agents or Workloads to open the Command Center filtered to that class.</div></div>')

STACK_STATS = '''
| stats dc(eval(if(actor_class="human",actor,null()))) as humans, dc(eval(if(actor_class="ai_agent",actor,null()))) as agents, dc(eval(if(actor_class="workload",actor,null()))) as workloads,
        dc(kubernetes_cluster) as k8s, dc(app_name) as apps, dc(db_service) as dbs, dc(server_hostname) as servers, dc(src_ip) as addrs,
        count as total, count(eval(outcome="denied")) as denied, count(eval(event="role.created")) as roles,
        count(eval(in(event,"user.update","role.created","user.create") AND actor_class="human")) as by_people,
        count(eval(event="user.login" AND success="true" AND isnotnull(mfa_device))) as mfa_ok, count(eval(event="user.login" AND success="true")) as logins_ok
| fillnull value=0
| eval pct=if(total>0, round(denied/total*100,1), 0), mfa_pct=if(logins_ok>0, round(mfa_ok/logins_ok*100,0), 0)'''
DONE = ''.join('<set token="%s">$result.%s$</set>' % (t, f) for t, f in [('n_h','humans'),('n_a','agents'),('n_w','workloads'),('n_k8s','k8s'),('n_app','apps'),('n_db','dbs'),
        ('n_srv','servers'),('n_ip','addrs'),('n_den','denied'),('n_pct','pct'),('n_roles','roles'),('n_ppl','by_people'),('n_mfa','mfa_pct')])
POST = '<search base="base"><query><![CDATA[%s]]></query><done>%s</done></search>' % (STACK_STATS, DONE)

views['tp_identity'] = form('★ Unified Identity Layer',
  'No shared secrets, no standing privilege, no anonymity: one identity layer for humans, machines and AI agents.',
  TIME + SRC, '', [
  row(html('One identity layer, live from the audit log', STACK, depends=' depends="$n_h$"')),
  row(
    single('Standing privilege: credentials living over 24h', '| search event="cert.create" | stats count(eval(ttl_h>24)) as long_lived', ranges=([0], [GREEN, RED])),
    single('Anonymous actions (no identity attached)', '| stats count(eval(actor="unknown")) as anonymous', ranges=([0], [GREEN, RED])),
    single('Average credential lifetime', '| search event="cert.create" | stats avg(ttl_h) as h | eval h=round(h,1) | fields h', unit='hours'),
  ),
  row(
    chart('Why agents matter: denial rate by identity class (%)', '| stats count as events, count(eval(outcome="denied")) as denied by actor_class | eval denial_rate=round(denied/events*100,1) | sort - denial_rate | fields actor_class denial_rate', kind='bar', stacked=False, legend='none'),
    chart('Credential lifetime by class (hours)', '| search event="cert.create" | stats avg(ttl_h) as avg_hours by actor_class | eval avg_hours=round(avg_hours,2)', kind='bar', stacked=False, legend='none'),
  ),
  row(
    table_x('Who touches what (actions by identity class and resource type)', '| eval rtype=case(isnotnull(db_service),"Databases",isnotnull(kubernetes_cluster),"Kubernetes",isnotnull(app_name),"Apps",isnotnull(server_hostname),"Servers") | where isnotnull(rtype) | chart count over actor_class by rtype', count=6, fmt=HEAT, wrap=False),
    table_x('Identity roster', '| stats values(actor_class) as class, dc(resource) as resources, values(resource) as reaches, count(eval(outcome="denied")) as denials, avg(ttl_h) as avg_cert_hours by actor | eval reaches=mvjoin(mvindex(reaches,0,2),", "), avg_cert_hours=round(avg_cert_hours,1) | sort - denials', count=8, fmt=colormap('class', CLASS_MAP)),
  ),
  row(html('The story in one paragraph', '''
<div style="line-height:1.6"><b>Humans are predictable. AI agents are not.</b> An agent will try things nobody scripted, so its prompt cannot be the safety boundary. Teleport gives every human, machine and agent its own short-lived identity and decides what that identity may do; Splunk records every attempt. The denial-rate chart is the point: agents are refused more often than people, and that is the system working, not failing.</div>''')),
], post=POST)
