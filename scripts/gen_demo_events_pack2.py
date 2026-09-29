#!/usr/bin/env python3
"""PACK 2 of SYNTHETIC demo events: a bigger company, Kubernetes, more databases, more incident types.

ADDITIVE: writes <day>.pack2.log files next to the pack-1 files. Nothing existing is overwritten,
so Splunk just picks up the new files (no need to clear the index).
Every event has demo=true. Fake names and documentation-range IPs only. No secrets.
NOTE: Kubernetes events are shaped like Teleport's kube.request but denial codes are approximated.
"""
import argparse, json, os, random, sys, uuid
from datetime import datetime, timedelta, timezone

ap = argparse.ArgumentParser()
ap.add_argument('--days', type=int, default=15)
ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'demo-data'))
A = ap.parse_args()
random.seed(20260930)
NOW = datetime.now(timezone.utc); TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
CL = 'localhost'; E = []
DENY_DB = 'access to db denied. User does not have permissions. Confirm database user and name.'
DBS = {'orders-db': ["select id, status from orders limit 20", "select count(*) from orders", "select status, count(*) from orders group by status"],
       'ledger-db': ["select count(*) from ledger_entries", "select account, sum(amount) from ledger_entries group by account limit 10", "select max(booked_at) from ledger_entries"]}
WRITES = ["create table hack (id int);", "drop table orders;", "delete from ledger_entries;", "update orders set status='paid';"]
KPATHS = ['/api/v1/namespaces/payments/pods', '/apis/apps/v1/namespaces/payments/deployments', '/api/v1/namespaces/payments/services', '/api/v1/namespaces/default/configmaps']

def day(n): return TODAY - timedelta(days=n)
def iso(t): return t.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (t.microsecond // 1000)
def rid(): return str(uuid.UUID(int=random.getrandbits(128), version=4))
def sec(t, lo=2, hi=40): return t + timedelta(seconds=random.randint(lo, hi))
def add(t, event, code, **kw):
    if t > NOW: return
    d = {'cluster_name': CL, 'code': code, 'ei': random.randint(0, 6), 'event': event, 'time': iso(t), 'uid': rid(), 'demo': True}
    d.update(kw); E.append((t, d))
def login(t, u, ip, ok=True):
    if ok: add(t, 'user.login', 'T1000I', user=u, success=True, method='local', mfa_device='yubikey', **{'addr.remote': ip + ':50123'})
    else:  add(t, 'user.login', 'T1000W', user=u, success=False, method='local', error='invalid username, password or second factor', **{'addr.remote': ip + ':50123'})
def cert(t, u, roles, ttl_h, ip, bot=False):
    add(t, 'cert.create', 'TC000I', cert_type='user', certificate_authority={'type': 'user', 'domain': CL},
        identity={'user': u, 'roles': roles, 'expires': iso(t + timedelta(hours=ttl_h)), 'client_ip': ip, 'bot_internal': bot, 'teleport_cluster': CL, 'private_key_policy': 'none'})
def ssh(t, u, host, ip):
    sid = rid(); add(t, 'session.start', 'T2000I', user=u, sid=sid, login='labuser', server_hostname=host, proto='ssh', **{'addr.remote': ip + ':50411'})
    end = t + timedelta(minutes=random.randint(2, 25))
    add(end, 'session.end', 'T2004I', user=u, sid=sid, login='labuser', server_hostname=host, proto='ssh', participants=[u], interactive=True); return end
def dbs(t, u, db_user, queries, bot=None, denied=False, svc='orders-db'):
    sid = rid(); extra = {'bot_name': bot, 'bot_instance_id': rid()} if bot else {}
    base = dict(user=u, sid=sid, db_service=svc, db_name=svc.replace('-', '_'), db_user=db_user, db_protocol='postgres', db_type='self-hosted', **extra)
    if denied: add(t, 'db.session.start', 'TDB00W', success=False, error=DENY_DB, **base); return t
    add(t, 'db.session.start', 'TDB00I', success=True, **base)
    for q in queries: t = sec(t, 2, 25); add(t, 'db.session.query', 'TDB02I', success=True, db_query=q, **base)
    t = sec(t, 3, 30); add(t, 'db.session.end', 'TDB01I', **base); return t
def app(t, u, name, ip): add(t, 'app.session.start', 'T2007I', user=u, app_name=name, public_addr=name + '.demo.local', **{'addr.remote': ip + ':50600'})
def kube(t, u, cluster, verb, path, ip, resp=200):
    add(t, 'kube.request', 'T3009I' if resp < 400 else 'T3009W', user=u, kubernetes_cluster=cluster, verb=verb, request_path=path, response_code=resp, **{'addr.remote': ip + ':51000'})
def bot_join(t, bot, method, ip, ok=True):
    if ok: add(t, 'bot.join', 'TJ001I', bot_name=bot, method=method, success=True, user_name='bot-' + bot, bot_instance_id=rid(), **{'addr.remote': ip + ':40022'})
    else:  add(t, 'bot.join', 'TJ001W', bot_name=bot, method=method, success=False, user_name='bot-' + bot, error='token not found or expired', **{'addr.remote': ip + ':40022'})

HUMANS = [
 dict(u='tomas.weber',   roles=['sre-prod', 'k8s-admin-prod'], ip='10.20.1.31', kinds=['kube', 'ssh', 'db'],  w=[6, 2, 1], clusters=['k8s-prod', 'k8s-stg']),
 dict(u='marco.bianchi', roles=['sre-prod'],                   ip='10.20.1.35', kinds=['kube', 'ssh', 'app'], w=[4, 3, 1], clusters=['k8s-prod', 'k8s-stg']),
 dict(u='sofia.klein',   roles=['payments-dba'],               ip='10.20.3.41', kinds=['db', 'app'],         w=[9, 1],    clusters=[]),
 dict(u='jonas.fischer', roles=['dev-nonprod'],                ip='10.20.2.51', kinds=['kube', 'app', 'ssh'], w=[5, 2, 1], clusters=['k8s-stg', 'k8s-dev']),
 dict(u='priya.nair',    roles=['dev-nonprod'],                ip='10.20.2.52', kinds=['kube', 'app', 'db'],  w=[4, 3, 1], clusters=['k8s-stg', 'k8s-dev']),
 dict(u='elena.petrova', roles=['security-analyst'],           ip='10.20.4.61', kinds=['app'],               w=[1],       clusters=[]),
]
def human_day(h, d0):
    if d0.weekday() >= 5 and random.random() > 0.08: return
    t = d0 + timedelta(hours=random.choice([7, 8, 8, 9, 10]), minutes=random.randint(0, 50))
    if random.random() < 0.06: login(t, h['u'], h['ip'], ok=False); t = sec(t, 20, 60)
    login(t, h['u'], h['ip']); t = sec(t, 1, 3); cert(t, h['u'], h['roles'], 8, h['ip'])
    for _ in range(random.randint(3, 7)):
        t += timedelta(minutes=random.randint(6, 55)); k = random.choices(h['kinds'], h['w'])[0]
        if k == 'kube':
            cl = random.choice(h['clusters'])
            for _ in range(random.randint(2, 6)): t = sec(t, 3, 40); kube(t, h['u'], cl, random.choice(['get', 'list', 'watch']), random.choice(KPATHS), h['ip'])
            if 'k8s-admin-prod' in h['roles'] and cl == 'k8s-prod' and random.random() < 0.25: kube(sec(t, 5, 30), h['u'], cl, 'create', KPATHS[0] + '/api-7d9c/exec', h['ip'])
            if h['u'] in ('jonas.fischer', 'priya.nair') and random.random() < 0.05: kube(sec(t, 5, 30), h['u'], 'k8s-prod', 'get', KPATHS[0], h['ip'], resp=403)
        elif k == 'ssh': t = ssh(t, h['u'], random.choice(['k8s-prod-worker-1', 'k8s-stg-worker-1', 'linux-server-1']), h['ip'])
        elif k == 'db':
            svc = 'ledger-db' if h['u'] == 'sofia.klein' and random.random() < 0.6 else 'orders-db'
            t = dbs(t, h['u'], 'readonly', random.sample(DBS[svc], random.randint(1, 3)), svc=svc)
        else: app(t, h['u'], random.choice(['grafana', 'argocd', 'wiki', 'whoami']), h['ip'])

# ---- routine noise ----
for n in range(A.days, -1, -1):
    d0 = day(n)
    for h in HUMANS: human_day(h, d0)
    t = d0 + timedelta(hours=2, minutes=random.randint(0, 20))                       # nightly backup bot
    bot_join(t, 'backup', 'kubernetes', '10.30.0.21'); cert(sec(t, 1, 3), 'bot-backup', ['bot-backup-readonly'], 1, '10.30.0.21', bot=True)
    dbs(sec(t, 5, 15), 'bot-backup', 'readonly', [DBS['ledger-db'][0]], bot='backup', svc='ledger-db')
    for hr in range(0, 24, 4):                                                        # ETL bot every 4h
        t = d0 + timedelta(hours=hr, minutes=random.randint(0, 15))
        cert(t, 'bot-etl', ['bot-etl-readonly'], 1, '10.30.0.33', bot=True)
        dbs(sec(t, 4, 10), 'bot-etl', 'readonly', random.sample(DBS['orders-db'], 2), bot='etl', svc='orders-db')

# ---- second AI agent: support copilot (reads orders, gets blocked from ledger) ----
for n in random.sample(range(1, A.days), 9):
    t = day(n) + timedelta(hours=random.randint(8, 16), minutes=random.randint(0, 50))
    bot_join(t, 'copilot-support', 'token', '10.40.0.12'); t = sec(t, 1, 3)
    cert(t, 'bot-copilot-support', ['bot-support-readonly'], 1, '10.40.0.12', bot=True); t = sec(t, 2, 6)
    if random.random() < 0.7: t = dbs(t, 'bot-copilot-support', 'readonly', [], bot='copilot-support', denied=True, svc='ledger-db'); t = sec(t, 5, 20)
    qs = random.sample(DBS['orders-db'], random.randint(1, 3))
    if random.random() < 0.2: qs.append(random.choice(WRITES))
    dbs(t, 'bot-copilot-support', 'readonly', qs, bot='copilot-support', svc='orders-db')

# ---- new incident types ----
t = day(9) + timedelta(hours=9, minutes=10)                                          # 1) impossible travel: same person, two places
login(t, 'marco.bianchi', '10.20.1.35'); cert(sec(t, 1, 3), 'marco.bianchi', ['sre-prod'], 8, '10.20.1.35')
t += timedelta(minutes=12); login(t, 'marco.bianchi', '203.0.113.140'); cert(sec(t, 1, 3), 'marco.bianchi', ['sre-prod'], 8, '203.0.113.140')
kube(t + timedelta(minutes=3), 'marco.bianchi', 'k8s-prod', 'list', KPATHS[0], '203.0.113.140')
t = day(5) + timedelta(hours=14, minutes=2)                                           # 2) role change made by a person, outside Terraform
add(t, 'user.update', 'T1003I', user='anna.becker', name='chloe.martin', roles=['dev-nonprod', 'k8s-admin-prod'], connector='local')
kube(t + timedelta(minutes=18), 'chloe.martin', 'k8s-prod', 'create', KPATHS[0] + '/api-7d9c/exec', '10.20.2.21')
add(t + timedelta(hours=2, minutes=28), 'user.update', 'T1003I', user='anna.becker', name='chloe.martin', roles=['dev-nonprod'], connector='local')
t = day(3) + timedelta(hours=4, minutes=30)                                           # 3) bot join with a bad token, unknown IP
for _ in range(5): bot_join(t, 'etl', 'token', '198.51.100.66', ok=False); t += timedelta(seconds=random.randint(20, 90))
t = day(6) + timedelta(hours=23, minutes=5)                                           # 4) bulk read at night on the ledger
login(t, 'sofia.klein', '10.20.3.41'); cert(sec(t, 1, 2), 'sofia.klein', ['payments-dba'], 8, '10.20.3.41')
dbs(sec(t, 20, 40), 'sofia.klein', 'readonly', ['select * from customers;'] * 22, svc='ledger-db')
t = day(1) + timedelta(hours=10, minutes=15)                                           # 5) developer probing production Kubernetes
for _ in range(6): kube(t, 'jonas.fischer', 'k8s-prod', 'get', random.choice(KPATHS), '10.20.2.51', resp=403); t += timedelta(seconds=random.randint(5, 25))

# ---- access as code + more onboarding ----
t = day(A.days - 1) + timedelta(hours=9, minutes=30)
for r in ['k8s-admin-prod', 'payments-dba', 'security-analyst', 'auditor', 'bot-backup-readonly', 'bot-etl-readonly', 'bot-support-readonly']:
    t = sec(t, 3, 12); add(t, 'role.created', 'T9000I', user='bot-terraform', name=r, user_kind=2)
for u, roles, dback, hr, first in [('hannah.mueller', ['dev-nonprod'], 6, 9, 'app'), ('oskar.lindqvist', ['auditor'], 10, 13, 'app')]:
    t = day(dback) + timedelta(hours=hr)
    add(t, 'user.create', 'T1002I', user='bot-terraform', name=u, roles=roles, connector='local'); t = sec(t, 20, 40)
    add(t, 'reset_password_token.create', 'T6000I', user='bot-terraform', name=u, ttl='1h0m0s'); t += timedelta(minutes=random.randint(3, 9))
    add(t, 'mfa.add', 'T1006I', user=u, mfa_device_name='yubikey', mfa_device_type='WebAuthn', **{'addr.remote': '10.20.2.70:50123'}); t = sec(t, 20, 40)
    login(t, u, '10.20.2.70'); t = sec(t, 1, 3); cert(t, u, roles, 8, '10.20.2.70'); t += timedelta(minutes=random.randint(2, 6)); app(t, u, 'wiki', '10.20.2.70')

# ---- write ----
E.sort(key=lambda x: x[0]); by = {}
for t, d in E: by.setdefault(t.strftime('%Y-%m-%d'), []).append(d)
out = os.path.abspath(A.out); os.makedirs(out, exist_ok=True)
files = {k: os.path.join(out, k + '.pack2.log') for k in by}
if any(os.path.exists(f) for f in files.values()): sys.exit('pack2 files already exist; refusing to overwrite (they may already be indexed).')
for k, evs in by.items():
    with open(files[k], 'w') as fh:
        for d in evs: fh.write(json.dumps(d, separators=(',', ':')) + '\n')
from collections import Counter
c = Counter(d['event'] for _, d in E)
print('pack2: wrote %d events in %d files -> %s' % (len(E), len(files), out))
for k, v in c.most_common(): print('%6d  %s' % (v, k))
