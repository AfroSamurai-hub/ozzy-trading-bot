import os, sys, time, json, hmac, hashlib, requests
sys.path.insert(0, '.')
import config
from binance.client import Client
from urllib.parse import urlencode

KEY_REDACTED = (config.BINANCE_API_KEY[:6] + '...' + config.BINANCE_API_KEY[-4:]) if len(getattr(config, 'BINANCE_API_KEY', '') or '') >= 10 else '***REDACTED***'

BASE = 'https://fapi.binance.com'
BASE_SPOT = 'https://api.binance.com'

def sign(params):
    p = dict(params or {})
    p['timestamp'] = int(time.time() * 1000)
    qs = urlencode(p)
    sig = hmac.new(getattr(config, 'BINANCE_API_SECRET', '').encode(), qs.encode(), hashlib.sha256).hexdigest()
    return f'{qs}&signature={sig}', p['timestamp']

def get_signed(path, params=None, base=BASE):
    qs, ts = sign(params)
    url = f'{base}{path}?{qs}'
    r = requests.get(url, headers={'X-MBX-APIKEY': getattr(config, 'BINANCE_API_KEY', '')}, timeout=20)
    return r.status_code, r.text[:4000]

client = Client(getattr(config, 'BINANCE_API_KEY', ''), getattr(config, 'BINANCE_API_SECRET', ''), testnet=False)

out = {
    'key_redacted': KEY_REDACTED,
    'testnet': getattr(config, 'BINANCE_TESTNET', None),
}

# 1) raw spot account (checks if key has any account access)
try:
    acct = client.get_account()
    out['spot_account_status'] = 'OK'
    out['spot_balances_nonzero'] = len([a for a in acct.get('balances', []) if float(a.get('free', 0.0)) + float(a.get('locked', 0.0)) > 0])
    out['spot_balances_sample'] = [a for a in acct.get('balances', [])[:5]]
except Exception as e:
    out['spot_account_status'] = f'ERROR: {type(e).__name__}: {e}'

# 2) futures account via wrapper
try:
    f = client.futures_account()
    out['futures_account_wrapper'] = {
        'totalWalletBalance': float(f.get('totalWalletBalance', 0.0)),
        'totalMarginBalance': float(f.get('totalMarginBalance', 0.0)),
        'maxWithdrawAmount': float(f.get('maxWithdrawAmount', 0.0)),
        'assets_count': len(f.get('assets', [])),
    }
except Exception as e:
    out['futures_account_wrapper'] = f'ERROR: {type(e).__name__}: {e}'

# 3) futures v2 account endpoint (some keys require v2)
try:
    r = requests.get(f'{BASE}/fapi/v2/account', headers={'X-MBX-APIKEY': getattr(config, 'BINANCE_API_KEY', '')}, params={'timestamp': int(time.time()*1000), 'recvWindow': 5000}, timeout=20)
    out['fapi_v2_status'] = r.status_code
    out['fapi_v2_body_sample'] = r.text[:1500]
except Exception as e:
    out['fapi_v2_status'] = f'ERROR: {type(e).__name__}: {e}'

# 4) SAPI account status (restrictions / jurisdiction)
try:
    code, body = get_signed('/sapi/v1/account/status')
    out['account_status_code'] = code
    out['account_status_body'] = body
except Exception as e:
    out['account_status_error'] = str(e)

# 5) SAPI API key permissions (the authoritative scope/status)
try:
    code, body = get_signed('/sapi/v1/apiKeyPermissions')
    out['api_key_permissions_code'] = code
    out['api_key_permissions_body'] = body
except Exception as e:
    out['api_key_permissions_error'] = str(e)

# 6) Spot cross wallet balance endpoint (alternative balance view)
try:
    code, body = get_signed('/sapi/v1/asset/crossMarginBalance', params={'asset': 'USDT', 'withdrawAlves': 0}, base=BASE_SPOT)
    out['spot_cross_margin_code'] = code
    out['spot_cross_margin_body'] = body
except Exception as e:
    out['spot_cross_margin_error'] = str(e)

# 7) futures ping/time sync (basic auth + endpoint sanity)
try:
    out['fapi_time'] = client.futures_time()
    ping = client.futures_ping()
    out['fapi_ping'] = ping
except Exception as e:
    out['fapi_ping_error'] = str(e)

print(json.dumps(out, indent=2, default=str))
