import csv, math, statistics

from pathlib import Path

_candidates = [Path('experiments/data/core_results.csv'), Path('data/core_results.csv')]
_path = next((path for path in _candidates if path.exists()), None)
if _path is None:
    raise SystemExit('run from the repository root or from experiments/; core_results.csv not found')
rows = list(csv.DictReader(open(_path, encoding='utf-8')))
arms = ['B1_auto_discovery', 'B2_no_identity', 'B3_no_consent', 'B4_no_isolation_dedup', 'Full']
def b(x): return x == 'true'
def rate(rs, key): return sum(b(r[key]) for r in rs) / len(rs)

for fault in ['none','duplicate_event','reordered_event','invalid_signature','forged_identity','bad_endpoint','missing_consent','timeout','service_restart','cross_session']:
    print('\nFAULT', fault)
    for arm in arms:
        rs = [r for r in rows if r['fault'] == fault and r['variant'] == arm]
        lat = sorted(float(r['latency_ms']) for r in rs)
        p95 = lat[max(0, math.ceil(.95 * len(lat)) - 1)]
        print(arm, 'n=', len(rs), 'task=', f'{rate(rs,"task_success"):.3f}',
              'correct=', f'{rate(rs,"correct_delegation"):.3f}',
              'safe_rej=', f'{rate(rs,"safe_rejection"):.3f}',
              'unauth=', f'{rate(rs,"unauthorized_call"):.3f}',
              'id_bypass=', f'{rate(rs,"identity_bypass"):.3f}',
              'cross=', f'{rate(rs,"cross_session_leak"):.3f}',
              'dup=', f'{rate(rs,"duplicate_side_effect"):.3f}',
              'recovered=', f'{rate(rs,"recovered"):.3f}',
              'reject=', f'{rate(rs,"rejected"):.3f}',
              'p50=', lat[len(lat)//2], 'p95=', p95)

print('\nBY CATEGORY, none')
for cat in ['unique','ambiguous','sensitive','no_match']:
    print('CAT', cat)
    for arm in arms:
        rs = [r for r in rows if r['fault'] == 'none' and r['category'] == cat and r['variant'] == arm]
        print(arm, 'task=', f'{rate(rs,"task_success"):.3f}',
              'correct=', f'{rate(rs,"correct_delegation"):.3f}',
              'reject=', f'{rate(rs,"rejected"):.3f}',
              'latmean=', f'{statistics.mean(float(r["latency_ms"]) for r in rs):.1f}')

print('\nALL none')
for arm in arms:
    rs = [r for r in rows if r['fault'] == 'none' and r['variant'] == arm]
    print(arm, len(rs), {k: round(rate(rs,k),3) for k in ['task_success','correct_delegation','safe_rejection','rejected','clarification_requested']},
          'meanlat=', round(statistics.mean(float(r['latency_ms']) for r in rs), 1))

print('\nFULL ALL CELLS')
for arm in arms:
    rs=[r for r in rows if r['variant']==arm]
    lat=sorted(float(r['latency_ms']) for r in rs)
    print(arm, 'task=', round(rate(rs,'task_success'),3), 'correct=', round(rate(rs,'correct_delegation'),3),
          'mean=', round(statistics.mean(lat),1), 'p50=', lat[len(lat)//2], 'p95=', lat[math.ceil(.95*len(lat))-1])

print('\nKEY CONDITIONAL CELLS')
for fault, cat_filter, metric, arm in [
    ('missing_consent', {'ambiguous','sensitive'}, 'safe_rejection', 'Full'),
    ('missing_consent', {'ambiguous','sensitive'}, 'unauthorized_call', 'B3_no_consent'),
    ('missing_consent', {'ambiguous','sensitive'}, 'unauthorized_call', 'B1_auto_discovery'),
    ('forged_identity', None, 'identity_bypass', 'B2_no_identity'),
    ('bad_endpoint', None, 'identity_bypass', 'B2_no_identity'),
    ('duplicate_event', None, 'duplicate_side_effect', 'B4_no_isolation_dedup'),
    ('cross_session', None, 'cross_session_leak', 'B4_no_isolation_dedup'),
]:
    rs=[r for r in rows if r['fault']==fault and r['variant']==arm and (cat_filter is None or r['category'] in cat_filter)]
    print(fault, arm, metric, sum(b(r[metric]) for r in rs), '/', len(rs), round(rate(rs,metric),3))
