#!/usr/bin/env python3
"""Pack 3: ONE clear incident, "the agent went off-script" (SYNTHETIC, demo=true).

Yesterday, business hours. The AI agent identity bot-claude-agent (role bot-lab-readonly):
  1. joins and gets a 1-hour certificate, runs 3 harmless reads
  2. asks for the admin database user 'postgres' 3 times -> Teleport refuses (TDB00W)
  3. sends 3 write statements as its read-only user -> forwarded and logged, then the
     database refuses each one (TDB03W: shape APPROXIMATED, verify against your live audit log)
  4. tries SSH as root and labuser to linux-server-1 -> Teleport refuses (T3007W)
Nothing changes. Output: demo-data/<day>.pack3.log -> index=teleport_demo.
Refuses to overwrite. Fake names and documentation-range IPs only. No secrets."""
import json, os, random, sys, uuid
from datetime import datetime, timedelta, timezone
random.seed(20260930)
NOW = datetime.now(timezone.utc)
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
CL = 'localhost'; IP = '10.40.0.7'; E = []
DENY_DB = 'access to db denied. User does not have permissions. Confirm database user and name.'
def iso(t): return t.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (t.microsecond // 1000)
def rid(): return str(uuid.UUID(int=random.getrandbits(128), version=4))
def sec(t, lo=2, hi=40): return t + timedelta(seconds=random.randint(lo, hi))
def add(t, event, code, **kw):
    if t > NOW: return
    d = {'cluster_name': CL, 'code': code, 'ei': random.randint(0, 6), 'event': event, 'time': iso(t), 'uid': rid(), 'demo': True}
    d.update(kw); E.append((t, d))

BOT = {'bot_name': 'claude-agent', 'bot_instance_id': rid()}
def dbbase(sid, dbu): return dict(user='bot-claude-agent', sid=sid, db_service='lab-postgres', db_name='labdb', db_user=dbu, db_protocol='postgres', db_type='self-hosted', **BOT)

t = TODAY - timedelta(days=1) + timedelta(hours=10, minutes=41, seconds=7)
add(t, 'bot.join', 'TJ001I', bot_name='claude-agent', method='token', success=True, user_name='bot-claude-agent', **{'addr.remote': IP + ':40022'}, bot_instance_id=BOT['bot_instance_id']); t = sec(t, 1, 3)
add(t, 'cert.create', 'TC000I', cert_type='user', certificate_authority={'type': 'user', 'domain': CL},
    identity={'user': 'bot-claude-agent', 'roles': ['bot-lab-readonly'], 'expires': iso(t + timedelta(hours=1)), 'client_ip': IP, 'bot_internal': True, 'teleport_cluster': CL, 'private_key_policy': 'none'}); t = sec(t, 3, 8)

# 1) normal reads
sid = rid(); b = dbbase(sid, 'labreader')
add(t, 'db.session.start', 'TDB00I', success=True, **b)
for q in ['select name, role from servers order by id', 'select count(*) as servers from servers', 'select role, count(*) from servers group by role']:
    t = sec(t, 3, 12); add(t, 'db.session.query', 'TDB02I', success=True, db_query=q, **b)
t = sec(t, 3, 10); add(t, 'db.session.end', 'TDB01I', **b); t = sec(t, 20, 40)

# 2) asks for the admin database user, three times: Teleport refuses at connect time
for _ in range(3):
    add(t, 'db.session.start', 'TDB00W', success=False, error=DENY_DB, **dbbase(rid(), 'postgres')); t = sec(t, 8, 20)

# 3) write attempts as the read-only user: forwarded and logged, then refused by the database
sid = rid(); b = dbbase(sid, 'labreader')
add(t, 'db.session.start', 'TDB00I', success=True, **b)
for q, err in [('drop table servers;', 'ERROR: must be owner of table servers (SQLSTATE 42501)'),
               ("update servers set role='admin';", 'ERROR: permission denied for table servers (SQLSTATE 42501)'),
               ('create table hack (id int);', 'ERROR: permission denied for schema public (SQLSTATE 42501)')]:
    t = sec(t, 4, 15); add(t, 'db.session.query', 'TDB02I', success=True, db_query=q, **b)
    t = sec(t, 1, 2); add(t, 'db.session.query.failed', 'TDB03W', success=False, db_query=q, error=err, **b)
t = sec(t, 3, 10); add(t, 'db.session.end', 'TDB01I', **b); t = sec(t, 15, 30)

# 4) tries SSH it has no role for
for who in ['root', 'labuser']:
    add(t, 'auth', 'T3007W', user='bot-claude-agent', success=False, login=who,
        error='ssh: principal "%s" not in the set of valid principals for given certificate' % who, **{'addr.remote': IP + ':50411'}); t = sec(t, 4, 12)

E.sort(key=lambda x: x[0]); by = {}
for tt, d in E: by.setdefault(tt.strftime('%Y-%m-%d'), []).append(d)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'demo-data'); out = os.path.abspath(out)
files = {k: os.path.join(out, k + '.pack3.log') for k in by}
if any(os.path.exists(f) for f in files.values()): sys.exit('pack3 files already exist; refusing to overwrite (they may already be indexed).')
for k, evs in by.items():
    with open(files[k], 'w') as fh:
        for d in evs: fh.write(json.dumps(d, separators=(',', ':')) + '\n')
print('pack3: wrote %d events -> %s' % (len(E), ', '.join(files.values())))
