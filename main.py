"""
Currency Converter API
Live exchange rates via open.er-api.com (free).
"""
import subprocess, json as _json, time, threading
from typing import Optional
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import time as _t, threading as _th
_rl_win, _rl_max, _rl_hits, _rl_lk = 60, 60, {}, _th.Lock()

async def _rate_limit(request):
    from fastapi import Request, HTTPException
    ip = (request.headers.get('X-Forwarded-For','') or request.headers.get('X-Real-IP','') or (request.client.host if request.client else '127.0.0.1')).split(',')[0].strip()
    now = _t.time()
    with _rl_lk:
        e = _rl_hits.get(ip)
        if e:
            if now - e['s'] > _rl_win: e['s'], e['c'] = now, 1
            else:
                e['c'] += 1
                if e['c'] > _rl_max: raise HTTPException(429, 'Too many requests')
        else: _rl_hits[ip] = {'s': now, 'c': 1}
    return True

app = FastAPI(title="Currency Converter API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


RATES_CACHE = {"ts": 0, "rates": {}}
_cache_lock = threading.Lock()


def fetch_rates():
    global RATES_CACHE
    with _cache_lock:
        if time.time() - RATES_CACHE["ts"] < 3600 and RATES_CACHE["rates"]:
            return RATES_CACHE["rates"]
    
    cmd = ["curl", "-s", "--connect-timeout", "8", "--max-time", "12",
           "https://open.er-api.com/v6/latest/USD"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = _json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}
    except:
        data = {}
    
    rates = data.get("rates", {})
    with _cache_lock:
        RATES_CACHE = {"ts": time.time(), "rates": rates}
    return rates


class ConversionResult(BaseModel):
    from_currency: str
    to_currency: str
    amount: float
    result: float
    rate: float
    last_updated: Optional[str] = None


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "Currency Converter API", "version": "1.1.0"}


@app.get("/convert", response_model=ConversionResult)
async def convert(
    from_currency: str = Query("USD", description="Source currency, e.g. USD"),
    to: str = Query(..., description="Target currency, e.g. CNY"),
    amount: float = Query(1.0, ge=0.01),
):
    rates = fetch_rates()
    if not rates:
        raise HTTPException(502, "Could not fetch exchange rates")

    from_currency = from_currency.upper()
    to = to.upper()

    try:
        usd_amount = amount / rates.get(from_currency, 1) if from_currency != "USD" else amount
        result = usd_amount * rates.get(to, 1) if to != "USD" else usd_amount
        rate = rates.get(to, 1) / rates.get(from_currency, 1) if from_currency != "USD" else rates.get(to, 1)
    except (ZeroDivisionError, KeyError):
        raise HTTPException(400, f"Invalid currency: {from_currency} or {to}")

    return ConversionResult(
        from_currency=from_currency,
        to_currency=to,
        amount=amount,
        result=round(result, 4),
        rate=round(rate, 6),
    )


@app.get("/rates")
async def list_rates():
    rates = fetch_rates()
    return {"base": "USD", "rates": rates}
