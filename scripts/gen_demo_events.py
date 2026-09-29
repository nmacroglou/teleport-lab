#!/usr/bin/env python3
"""Make SYNTHETIC Teleport-style audit events for demos.

* Every event carries "demo": true. It is NOT real data.
* Output goes to ./demo-data/ and is read by Splunk into index=teleport_demo
  (never into your real index=teleport).
* Uses only fake names and documentation-range IPs (10.x, 198.51.100.x, 203.0.113.x).
* Contains no secrets. Safe to re-read; refuses to overwrite unless --force.
"""
import argparse, json, os, random, sys, uuid
from datetime import datetime, timedelta, timezone

ap = argparse.ArgumentParser()
ap.add_argument('--days', type=int, default=15)
ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'demo-data'))
ap.add_argument('--force', action='store_true')
A = ap.parse_args()

random.seed(20260929)          # same seed = same story every time
NOW = datetime.now(timezone.utc)
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
CL = 'localhost'
E = []
READS = ["select name, role from servers order by id", "select count(*) as servers from servers",
         "select current_user", "select * from servers limit 10;",
         "select role, count(*) from servers group by role",
         "SELECT table_schema, table_name FROM information_schema.tables"]
WRITES = ["create table hack (id int);", "drop table servers;", "delete from servers;",
          "update servers set role='admin';"]
HOSTS = ['linux-server-1', 'k8s-prod-worker-1', 'k8s-stg-worker-1']
DENY_DB = 'access to db denied. User does not have permissions. Confirm database user and name.'

def day(n): return TODAY - timedelta(days=n)
def iso(t): return t.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (t.microsecond // 1000)
def rid(): return str(uuid.UUID(int=random.getrandbits(128), version=4))
def sec(t, lo=2, hi=40): return t + timedelta(seconds=random.randint(lo, hi))

def add(t, event, code, **kw):
    if t > NOW: return
    d = {'cluster_name': CL, 'code': code, 'ei': random.randint(0, 6), 'event': event,
         'time': iso(t), 'uid': rid(), 'demo': True}
    d.update(kw); E.append((t, d))

def login(t, u, ip, ok=True):
    if ok: add(t, 'user.login', 'T1000I', user=u, success=True, method='local', mfa_device='yubikey', **{'addr.remote': ip + ':50123'})
    else:  add(t, 'user.login', 'T1000W', user=u, success=False, method='local',
               error='invalid username, password or second factor', **{'addr.remote': ip + ':50123'})

def cert(t, u, roles, ttl_h, ip, bot=False):
    add(t, 'cert.create', 'TC000I', cert_type='user', certificate_authority={'type': 'user', 'domain': CL},
        identity={'user': u, 'roles': roles, 'expires': iso(t + timedelta(hours=ttl_h)), 'client_ip': ip,
                  'bot_internal': bot, 'teleport_cluster': CL, 'private_key_policy': 'none'})

def ssh(t, u, login_as, host, ip, denied=False):
    if denied:
        add(t, 'auth', 'T3007W', user=u, success=False, login=login_as,
            error='ssh: principal "%s" not in the set of valid principals for given certificate' % login_as,
            **{'addr.remote': ip + ':50411'})
        return t
    sid = rid()
    add(t, 'session.start', 'T2000I', user=u, sid=sid, login=login_as, server_hostname=host, proto='ssh', **{'addr.remote': ip + ':50411'})
    end = t + timedelta(minutes=random.randint(2, 25))
    add(end, 'session.end', 'T2004I', user=u, sid=sid, login=login_as, server_hostname=host, proto='ssh', participants=[u], interactive=True)
    return end

def dbs(t, u, db_user, queries, ip, bot=None, denied=False):
    sid = rid(); extra = {'bot_name': bot, 'bot_instance_id': rid()} if bot else {}
    base = dict(user=u, sid=sid, db_service='lab-postgres', db_name='labdb', db_user=db_user, db_protocol='postgres', db_type='self-hosted', **extra)
    if denied:
        add(t, 'db.session.start', 'TDB00W', success=False, error=DENY_DB, **base); return t
    add(t, 'db.session.start', 'TDB00I', success=True, **base)
    for q in queries:
        t = sec(t, 2, 25); add(t, 'db.session.query', 'TDB02I', success=True, db_query=q, **base)
    t = sec(t, 3, 30); add(t, 'db.session.end', 'TDB01I', **base); return t

def app(t, u, name, ip):
    add(t, 'app.session.start', 'T2007I', user=u, app_name=name, public_addr=name + '.demo.local', **{'addr.remote': ip + ':50600'})

def bot_join(t, bot, method, ip):
    add(t, 'bot.join', 'TJ001I', bot_name=bot, method=method, success=True, user_name='bot-' + bot, **{'addr.remote': ip + ':40022'}, bot_instance_id=rid())

# ---------- cast ----------
HUMANS = [
  dict(u='anna.becker',  roles=['sre-prod'],       ip='10.20.1.11', kinds=['ssh','db','app'], w=[5,2,1]),
  dict(u='maria.rossi',  roles=['sre-prod'],       ip='10.20.1.14', kinds=['ssh','db','app'], w=[5,2,2]),
  dict(u='chloe.martin', roles=['dev-nonprod'],    ip='10.20.2.21', kinds=['ssh','app','db'], w=[3,4,2]),
  dict(u='dev.singh',    roles=['dba-readonly'],   ip='10.20.3.31', kinds=['db','app'],       w=[8,1]),
]
def human_day(h, d0):
    if d0.weekday() >= 5 and random.random() > 0.10: return
    t = d0 + timedelta(hours=random.choice([7, 8, 8, 9]), minutes=random.randint(0, 50))
    if random.random() < 0.05:
        login(t, h['u'], h['ip'], ok=False); t = sec(t, 20, 60)
    login(t, h['u'], h['ip']); t = sec(t, 1, 3); cert(t, h['u'], h['roles'], 8, h['ip'])
    for _ in range(random.randint(2, 5)):
        t += timedelta(minutes=random.randint(8, 70))
        k = random.choices(h['kinds'], h['w'])[0]
        if k == 'ssh': t = ssh(t, h['u'], 'labuser', random.choice(HOSTS), h['ip'])
        elif k == 'db': t = dbs(t, h['u'], 'labreader', random.sample(READS, random.randint(1, 4)), h['ip'])
        else: app(t, h['u'], random.choice(['whoami', 'whoami', 'grafana']), h['ip'])

# ---------- routine noise: engineers + machine identities ----------
for n in range(A.days, -1, -1):
    d0 = day(n)
    for h in HUMANS: human_day(h, d0)
    for hr in range(0, 24):                                   # monitoring bot: hourly, 24/7, read-only
        t = d0 + timedelta(hours=hr, minutes=random.randint(0, 9))
        cert(t, 'bot-monitoring', ['bot-lab-readonly'], 1, '10.30.0.5', bot=True)
        dbs(sec(t, 3, 9), 'bot-monitoring', 'labreader', ['select count(*) as servers from servers'], '10.30.0.5', bot='monitoring')
    if d0.weekday() < 5:                                      # CI deploy bot: weekdays, every 2h
        for hr in range(8, 18, 2):
            t = d0 + timedelta(hours=hr, minutes=random.randint(0, 20))
            bot_join(t, 'ci-deploy', 'kubernetes', '10.30.0.9'); cert(sec(t, 1, 3), 'bot-ci-deploy', ['bot-ci-readonly'], 1, '10.30.0.9', bot=True)
            dbs(sec(t, 5, 15), 'bot-ci-deploy', 'labreader', random.sample(READS, 2), '10.30.0.9', bot='ci-deploy')

# ---------- the AI agent (scene 3): mostly reads, a few Teleport-level denials + write attempts ----------
agent_days = [n for n in random.sample(range(1, A.days), 6)]
danger_days = set(agent_days[:3])
for n in agent_days:
    t = day(n) + timedelta(hours=random.randint(9, 15), minutes=random.randint(0, 50))
    bot_join(t, 'claude-agent', 'token', '10.40.0.7'); t = sec(t, 1, 3)
    cert(t, 'bot-claude-agent', ['bot-lab-readonly'], 1, '10.40.0.7', bot=True); t = sec(t, 2, 6)
    if random.random() < 0.6: t = dbs(t, 'bot-claude-agent', 'postgres', [], '10.40.0.7', bot='claude-agent', denied=True); t = sec(t, 5, 20)
    qs = random.sample(READS, random.randint(3, 6))
    if n in danger_days: qs += random.sample(WRITES, random.randint(1, 3)); random.shuffle(qs)
    dbs(t, 'bot-claude-agent', 'labreader', qs, '10.40.0.7', bot='claude-agent')

# ---------- scripted incidents (scene 4) ----------
t = day(11) + timedelta(hours=3, minutes=12)                  # brute force against a contractor account
for _ in range(14): login(t, 'ben.okafor', '203.0.113.77', ok=False); t += timedelta(seconds=random.randint(8, 25))
t = day(7) + timedelta(hours=2, minutes=10)                   # off-hours contractor DB access, unusual IP
login(t, 'ben.okafor', '198.51.100.23'); cert(sec(t, 1, 2), 'ben.okafor', ['contractor-lab'], 8, '198.51.100.23')
dbs(sec(t, 30, 60), 'ben.okafor', 'labreader', random.sample(READS, 3), '198.51.100.23')
ssh(day(2) + timedelta(hours=11, minutes=5), 'bot-ci-deploy', 'labuser', 'linux-server-1', '10.30.0.9', denied=True)   # bot tries SSH it has no role for
ssh(day(2) + timedelta(hours=11, minutes=6), 'bot-ci-deploy', 'root', 'linux-server-1', '10.30.0.9', denied=True)
for i in range(3):
    login(day(4) + timedelta(hours=8, minutes=30 + i), 'chloe.martin', '10.20.2.21', ok=False)

# ---------- access as code (IaC) + day-one onboarding (scene 1) ----------
t = day(A.days - 1) + timedelta(hours=9)
for r in ['sre-prod', 'dev-nonprod', 'dba-readonly', 'contractor-lab', 'bot-lab-readonly', 'bot-ci-readonly']:
    t = sec(t, 3, 12); add(t, 'role.created', 'T9000I', user='bot-terraform', name=r, user_kind=2)
t = day(3) + timedelta(hours=10); add(t, 'user.update', 'T1003I', user='bot-terraform', name='ben.okafor', roles=['contractor-lab'], connector='local')
t = day(1) + timedelta(hours=8, minutes=30)                   # new hire: Lena, onboarded in minutes
add(t, 'user.create', 'T1002I', user='bot-terraform', name='lena.vogel', roles=['dev-nonprod'], connector='local'); t = sec(t, 20, 40)
add(t, 'reset_password_token.create', 'T6000I', user='bot-terraform', name='lena.vogel', ttl='1h0m0s'); t += timedelta(minutes=4)
add(t, 'mfa.add', 'T1006I', user='lena.vogel', mfa_device_name='yubikey', mfa_device_type='WebAuthn', **{'addr.remote': '10.20.2.40:50123'}); t = sec(t, 20, 40)
login(t, 'lena.vogel', '10.20.2.40'); t = sec(t, 1, 3); cert(t, 'lena.vogel', ['dev-nonprod'], 8, '10.20.2.40')
t += timedelta(minutes=2); t = ssh(t, 'lena.vogel', 'labuser', 'k8s-stg-worker-1', '10.20.2.40')
dbs(t + timedelta(minutes=3), 'lena.vogel', 'labreader', ['select name, role from servers order by id'], '10.20.2.40')

# ---------- write files ----------
E.sort(key=lambda x: x[0]); by = {}
for t, d in E: by.setdefault(t.strftime('%Y-%m-%d'), []).append(d)
out = os.path.abspath(A.out); os.makedirs(out, exist_ok=True)
files = {k: os.path.join(out, k + '.00:00:00.log') for k in by}
clash = [f for f in files.values() if os.path.exists(f)]
if clash and not A.force: sys.exit('Refusing to overwrite %d existing file(s). Use --force only after clearing index=teleport_demo.' % len(clash))
for k, evs in by.items():
    with open(files[k], 'w') as fh:
        for d in evs: fh.write(json.dumps(d, separators=(',', ':')) + '\n')
from collections import Counter
c = Counter(d['event'] for _, d in E)
print('wrote %d events in %d files -> %s' % (len(E), len(files), out))
for k, v in c.most_common(): print('%6d  %s' % (v, k))
