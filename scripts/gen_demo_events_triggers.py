#!/usr/bin/env python3
"""SYNTHETIC trigger-style events for the demo index (demo=true).

The live traffic (scripts/demo-traffic.sh) produces a particular kind of event:
bot reads, writes the database refuses, a denied admin user, denied SSH and
failed logins. This script makes the same kinds of events for past days, so the
synthetic data (index=teleport_demo) has the same mix, size and shape.

* Templates are CLONED from your real audit log (data/log), so every field and
  every event size matches the real thing. Each clone gets a new time, a new
  uid/sid, and "demo": true.
* Events follow the demo data's own daily curve (busy and quiet hours).
* Writes <day>.triggers.log, one file per complete UTC day. Days that already
  have a triggers file are skipped (unless --force), so re-running never
  duplicates anything and nothing in Splunk has to be deleted.
"""
import argparse, copy, glob, json, os, random, re, sys, uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument('--days', type=int, default=15, help='how many past complete days to cover')
ap.add_argument('--per-day', type=int, default=110, help='target trigger events per day')
ap.add_argument('--out', default=os.path.join(HERE, '..', 'demo-data'))
ap.add_argument('--audit', default=os.path.join(HERE, '..', 'data', 'log'))
ap.add_argument('--force', action='store_true', help='overwrite existing triggers files')
A = ap.parse_args()

WRITE = re.compile(r'(?i)^\s*(create|delete|update|drop|insert|alter|truncate)')
TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# ---- templates from the real audit log ------------------------------------
sessions, admin, ssh, login = defaultdict(list), [], [], []
for f in glob.glob(os.path.join(A.audit, '*', '*.log')):
    for line in open(f, errors='replace'):
        try: e = json.loads(line)
        except ValueError: continue
        u, ev = e.get('user'), e.get('event')
        if u == 'bot-lab-bot' and ev in ('db.session.start', 'db.session.query', 'db.session.end'):
            sessions[e.get('sid')].append(e)
        if u == 'bot-lab-bot' and ev == 'db.session.start' and e.get('success') is False: admin.append(e)
        if u == 'bot-lab-bot' and ev == 'auth' and e.get('success') is False: ssh.append(e)
        if ev == 'user.login' and e.get('success') is False and u in ('ben.okafor', 'temp.contractor'): login.append(e)
reads, writes = [], []
for evs in sessions.values():
    qs = [x for x in evs if x['event'] == 'db.session.query' and not (x.get('db_query') or '').startswith('--')]
    st = [x for x in evs if x['event'] == 'db.session.start' and x.get('success')]
    en = [x for x in evs if x['event'] == 'db.session.end']
    if len(qs) == 1 and st and en:
        (writes if WRITE.match(qs[0].get('db_query', '')) else reads).append([st[0], qs[0], en[0]])
kinds = {'read': reads, 'write': writes, 'admin': admin, 'ssh': ssh, 'login': login}
missing = [k for k, v in kinds.items() if not v]
if missing:
    sys.exit('No real template events for: %s. Run scripts/demo-traffic.sh start for a few minutes first.' % ', '.join(missing))

# ---- daily curve from the demo story itself ---------------------------------
hours = Counter()
story = [p for p in glob.glob(os.path.join(A.out, '*.log')) if not p.endswith('.triggers.log')]
for p in story:
    for line in open(p, errors='replace'):
        try: hours[int(json.loads(line)['time'][11:13])] += 1
        except (ValueError, KeyError): pass
weights = [hours[h] or 1 for h in range(24)]

# action mix, and roughly how many events each action produces
MIX = [('read', .55), ('write', .10), ('admin', .05), ('ssh', .10), ('login', .20)]
COST = {'read': 3, 'write': 3, 'admin': 1, 'ssh': 1, 'login': 2}
avg_cost = sum(w * COST[k] for k, w in MIX)

def ts(t): return t.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
def clone(tpl, t, sid=None):
    e = copy.deepcopy(tpl)
    e['time'] = ts(t); e['uid'] = str(uuid.uuid4()); e['demo'] = True
    if sid and 'sid' in e: e['sid'] = sid
    return e

os.makedirs(A.out, exist_ok=True)
made = 0
for n in range(A.days, 0, -1):            # complete days only, oldest first
    day = TODAY - timedelta(days=n)
    path = os.path.join(A.out, day.strftime('%Y-%m-%d') + '.triggers.log')
    if os.path.exists(path) and not A.force: continue
    rng = random.Random('triggers-' + day.strftime('%Y-%m-%d'))
    random.seed(rng.random())
    out = []
    for _ in range(max(1, round(A.per_day / avg_cost))):
        kind = rng.choices([k for k, _ in MIX], [w for _, w in MIX])[0]
        t = day + timedelta(hours=rng.choices(range(24), weights)[0], seconds=rng.uniform(0, 3599))
        if kind in ('read', 'write'):
            sid = str(uuid.uuid4())
            for i, tpl in enumerate(rng.choice(kinds[kind])):
                out.append(clone(tpl, t + timedelta(milliseconds=40 * i), sid))
        elif kind == 'login':
            tpl = rng.choice(login)
            for i in range(rng.randint(1, 3)): out.append(clone(tpl, t + timedelta(seconds=i)))
        else:
            out.append(clone(rng.choice(kinds[kind]), t))
    out.sort(key=lambda e: e['time'])
    with open(path, 'w') as fh:
        for e in out: fh.write(json.dumps(e, separators=(',', ':')) + '\n')
    made += 1
    print('%s  %4d events' % (os.path.basename(path), len(out)))
print('wrote %d triggers file(s) -> %s' % (made, os.path.abspath(A.out)))
