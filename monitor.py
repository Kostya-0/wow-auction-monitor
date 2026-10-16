import json, os, pathlib, urllib.request, urllib.error, datetime

ROOT = pathlib.Path(__file__).parent
STATE = ROOT / 'state.json'
CONFIG = ROOT / 'items.json'
API = 'https://api.undermine.exchange'

def get_json(url, key):
    req = urllib.request.Request(url, headers={'Authorization': 'ApiKey ' + key, 'Accept-Encoding': 'gzip', 'User-Agent': 'WoW-Median-Monitor/1.0'})
    with urllib.request.urlopen(req, timeout=35) as resp:
        data = resp.read()
        if resp.headers.get('Content-Encoding') == 'gzip':
            import gzip
            data = gzip.decompress(data)
        return json.loads(data)

def median_auctions(rows):
    levels = sorted((int(a['price']), int(a.get('quantity', 1))) for a in rows if int(a.get('quantity', 1)) > 0)
    total = sum(q for _, q in levels)
    if not total: return None
    targets = ((total - 1)//2, total//2)
    acc, found = 0, []
    for price, q in levels:
        for t in targets:
            if acc <= t < acc + q: found.append(price)
        acc += q
        if len(found) == 2: return sum(found)/2
    return None

def money(copper):
    n = round(copper)
    return f'{n//10000}з {(n%10000)//100}с {n%100}м'

def notify(msg):
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        print('Telegram not configured. Alert:\n' + msg)
        return
    payload = json.dumps({'chat_id':chat, 'text':msg}).encode()
    req = urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage', data=payload, headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=25) as r: r.read()

def main():
    key = os.environ.get('UNDERMINE_API_KEY')
    if not key: raise SystemExit('Missing UNDERMINE_API_KEY GitHub secret')
    items = json.loads(CONFIG.read_text(encoding='utf-8'))
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    changed = False
    for item in items:
        name = item['name']
        item_id = item.get('id')
        if not item_id:
            print(f'SKIP {name}: item ID not configured')
            continue
        typ = item.get('type', 'commodity')
        if typ == 'commodity':
            url = f'{API}/v1/region/eu/commodities/{item_id}/now.json'
        else:
            url = f'{API}/v1/realm/eu/eversong/items/{item_id}/now.json'
        try:
            response = get_json(url, key)
            result = response['result']
            median = median_auctions(result.get('auctions', []))
            if median is None: raise ValueError('No auction rows to calculate median')
            snapshot = result.get('lastSeen') or result.get('lastUpdated')
            old = state.get(str(item_id))
            if old and snapshot == old.get('snapshot'):
                print(f'UNCHANGED snapshot {name}: {snapshot}')
                continue
            if old and old['median'] > 0:
                delta = (median / old['median'] - 1) * 100
                if abs(delta) >= float(item.get('threshold_percent', 30)):
                    notify(f'WoW EU — {name}\nМедиана: {money(old["median"])} → {money(median)}\nИзменение: {delta:+.1f}%\nСнимок: {snapshot}')
            state[str(item_id)] = {'median': median, 'snapshot': snapshot, 'checked_at': now}
            changed = True
            print(f'OK {name}: {money(median)} snapshot={snapshot}')
        except Exception as exc:
            print(f'ERROR {name}: {exc}')
    if changed:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__': main()
