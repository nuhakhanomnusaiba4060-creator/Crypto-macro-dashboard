
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MARKET CYCLE & BULL RUN TRACKER
Version: 1.0.0

Read-only inputs:
  data/market_data.json
  data/advanced_data.json
  data/macro_data.json
  data/market_zone_data.json

Independent output:
  data/cycle_data.json

Existing engines and their JSON files are never modified.
"""

import csv
import json
import math
import os
import tempfile
import time

from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

MARKET_FILE = DATA / "market_data.json"
ADVANCED_FILE = DATA / "advanced_data.json"
MACRO_FILE = DATA / "macro_data.json"
ZONE_FILE = DATA / "market_zone_data.json"
OUTPUT_FILE = DATA / "cycle_data.json"

BINANCE = "https://data-api.binance.vision"
ALTSEASON = "https://api.blockchaincenter.net/api/coin/altcoinseason/"
FRED_SAHM = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SAHMREALTIME"

VERSION = "1.0.0"
TIMEOUT = 18
HISTORY_DAYS = 730


# ============================================================
# COMMON UTILITIES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso():
    return (
        utc_now()
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def parse_time(value):

    if not isinstance(value, str):
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def age_minutes(value):

    dt = parse_time(value)

    if dt is None:
        return None

    age = (
        utc_now() - dt
    ).total_seconds() / 60

    if age < -5:
        return None

    return max(0, age)


def number(value):

    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)

        return (
            result
            if math.isfinite(result)
            else None
        )

    except (ValueError, TypeError, OverflowError):
        return None


def read_json(path):

    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except (OSError, ValueError, UnicodeError):
        return {}


def metric_value(item):

    if not isinstance(item, dict):
        return None

    if str(item.get("status", "")).upper() not in (
        "OK", "FRESH", "SUCCESS"
    ):
        return None

    return number(item.get("value"))


def metric_time(item):

    if not isinstance(item, dict):
        return None

    return (
        item.get("source_updated_at")
        or item.get("observation_date")
        or item.get("observed_at")
    )


def request(url, accept="application/json"):

    req = Request(
        url,
        headers={
            "User-Agent": "CryptoCycleTracker/1.0",
            "Accept": accept
        }
    )

    last_error = "Unknown network error"

    for attempt in range(3):

        try:

            with urlopen(
                req,
                timeout=TIMEOUT
            ) as response:

                raw = response.read()

            return raw.decode("utf-8-sig"), iso()

        except HTTPError as exc:

            last_error = f"HTTP_{exc.code}"

            if exc.code not in (
                429, 500, 502, 503, 504
            ):
                break

        except (
            URLError,
            TimeoutError,
            OSError
        ) as exc:

            last_error = str(exc)

        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(last_error)


def unavailable(source, reason):

    return {
        "value": None,
        "status": "UNAVAILABLE",
        "source": source,
        "source_updated_at": None,
        "fetched_at": iso(),
        "reason": str(reason)[:240]
    }


# ============================================================
# ALTCOIN SEASON INDEX
# ============================================================

def get_altcoin_season(previous):

    source = "BlockchainCenter Altcoin Season Index API"

    old = previous.get("altcoin_season", {})

    # Provider requests are limited to one per 35 minutes.
    old_age = age_minutes(old.get("fetched_at"))

    if (
        isinstance(old, dict)
        and old.get("value") is not None
        and old_age is not None
        and old_age < 35
    ):
        return old

    fetched = iso()

    try:

        raw, fetched = request(ALTSEASON)

        payload = json.loads(raw)

        scores = payload.get("score", {})
        daily = scores.get("90", {})

        if not isinstance(daily, dict) or not daily:
            raise ValueError("Missing 90-day index")

        observations = []

        for day, raw_value in daily.items():

            value = number(raw_value)

            if value is not None and 0 <= value <= 100:
                observations.append((day, value))

        if not observations:
            raise ValueError("No valid index observations")

        day, value = max(
            observations,
            key=lambda x: x[0]
        )

        if value >= 75:
            classification = "ALTCOIN_SEASON"
            label = "Altcoin Season"

        elif value <= 25:
            classification = "BITCOIN_SEASON"
            label = "Bitcoin Season"

        else:
            classification = "NEUTRAL"
            label = "Neutral"

        age = age_minutes(day + "T00:00:00Z")

        status = (
            "OK"
            if age is not None and age <= 72 * 60
            else "STALE"
        )

        return {
            "value": value,
            "unit": "index / 100",
            "classification": classification,
            "label": label,
            "window_days": 90,
            "source": source,
            "source_updated_at": day + "T00:00:00Z",
            "fetched_at": fetched,
            "status": status,
            "definition": (
                "90-day performance comparison of eligible "
                "Top 50 altcoins against Bitcoin. "
                "75 or above indicates Altcoin Season."
            ),
            "reason": None
        }

    except Exception as exc:

        if isinstance(old, dict) and old.get("value") is not None:

            result = dict(old)
            result["status"] = "STALE"
            result["fetched_at"] = fetched
            result["reason"] = (
                "Refresh failed; previous observation retained: "
                + str(exc)
            )

            return result

        return unavailable(source, str(exc))


# ============================================================
# ETH / BTC RATIO
# ============================================================

def get_eth_btc():

    source = "Binance Spot ETHBTC"

    fetched = iso()

    try:

        raw, fetched = request(
            BINANCE + "/api/v3/ticker/price?symbol=ETHBTC"
        )

        payload = json.loads(raw)

        value = number(payload.get("price"))

        if value is None or value <= 0:
            raise ValueError("Invalid ETHBTC price")

        return {
            "value": value,
            "unit": "BTC per ETH",
            "status": "TIME_UNKNOWN",
            "source": source,
            "source_updated_at": None,
            "fetched_at": fetched,
            "reason": (
                "Binance ticker endpoint does not provide "
                "a verified exchange observation timestamp."
            )
        }

    except Exception as exc:

        return unavailable(source, str(exc))


# ============================================================
# RECESSION RISK - FRED SAHM RULE
# ============================================================

def get_recession_risk(previous):

    source = "FRED SAHMREALTIME"

    old = previous.get("recession_risk", {})

    old_age = age_minutes(old.get("fetched_at"))

    # Sahm Rule is monthly. Refreshing every 6 hours is unnecessary.
    if (
        isinstance(old, dict)
        and old.get("value") is not None
        and old_age is not None
        and old_age < 6 * 60
    ):
        return old

    fetched = iso()

    try:

        raw, fetched = request(
            FRED_SAHM,
            "text/csv"
        )

        rows = list(
            csv.DictReader(raw.splitlines())
        )

        observations = []

        for row in rows:

            day = (
                row.get("observation_date")
                or row.get("DATE")
            )

            value = number(
                row.get("SAHMREALTIME")
            )

            if day and value is not None:
                observations.append((day, value))

        if not observations:
            raise ValueError("No valid FRED observations")

        day, value = max(
            observations,
            key=lambda x: x[0]
        )

        age = age_minutes(day + "T00:00:00Z")

        status = (
            "OK"
            if age is not None and age <= 100 * 24 * 60
            else "STALE"
        )

        if value >= 0.50:
            label = "SAHM_RULE_TRIGGERED"
            level = "HIGH"

        elif value >= 0.30:
            label = "RECESSION_WARNING"
            level = "ELEVATED"

        else:
            label = "NO_SAHM_TRIGGER"
            level = "LOW"

        return {
            "value": value,
            "unit": "percentage points",
            "classification": label,
            "risk_level": level,
            "source": source,
            "source_updated_at": day + "T00:00:00Z",
            "fetched_at": fetched,
            "frequency": "Monthly",
            "status": status,
            "definition": (
                "Sahm Rule threshold is 0.50 percentage points. "
                "This is a recession indicator, not a probability forecast."
            )
        }

    except Exception as exc:

        if isinstance(old, dict) and old.get("value") is not None:

            result = dict(old)
            result["status"] = "STALE"
            result["fetched_at"] = fetched
            result["reason"] = str(exc)

            return result

        return unavailable(source, str(exc))


# ============================================================
# TOTAL2 / TOTAL3 / ALTCOIN MARKET CAP
# ============================================================

def build_market_caps(market):

    global_data = market.get("global_market", {})

    total = metric_value(
        global_data.get("total_market_cap_usd")
    )

    btc_dom = metric_value(
        global_data.get("btc_dominance_pct")
    )

    eth_dom = metric_value(
        global_data.get("eth_dominance_pct")
    )

    items = [
        global_data.get("total_market_cap_usd"),
        global_data.get("btc_dominance_pct"),
        global_data.get("eth_dominance_pct")
    ]

    source_time = min(
        [
            metric_time(x)
            for x in items
            if metric_time(x)
        ],
        default=None
    )

    fetched = iso()

    if (
        total is None
        or btc_dom is None
        or eth_dom is None
    ):

        reason = (
            "Total Market Cap and BTC/ETH Dominance "
            "must all be available."
        )

        return {
            key: unavailable(
                "CoinGecko Global API",
                reason
            )
            for key in (
                "total_altcoin_market_cap_ex_btc",
                "total2",
                "total3",
                "btc_market_cap",
                "eth_market_cap"
            )
        }

    if (
        btc_dom < 0
        or eth_dom < 0
        or btc_dom + eth_dom > 100.5
    ):

        return {
            key: unavailable(
                "CoinGecko Global API",
                "Dominance values failed validation."
            )
            for key in (
                "total_altcoin_market_cap_ex_btc",
                "total2",
                "total3",
                "btc_market_cap",
                "eth_market_cap"
            )
        }

    btc_cap = total * btc_dom / 100
    eth_cap = total * eth_dom / 100

    total2 = total - btc_cap
    total3 = total - btc_cap - eth_cap

    age = age_minutes(source_time)

    status = (
        "OK"
        if age is not None and age <= 120
        else "STALE"
    )

    source = "CoinGecko Global API - Derived"

    def item(value, calculation):

        return {
            "value": value,
            "unit": "USD",
            "status": status,
            "source": source,
            "source_updated_at": source_time,
            "fetched_at": fetched,
            "calculation": calculation
        }

    return {

        "total_altcoin_market_cap_ex_btc": item(
            total2,
            "Total market cap less BTC market cap."
        ),

        "total2": item(
            total2,
            "Total Crypto Market Cap - BTC Market Cap."
        ),

        "total3": item(
            total3,
            "Total Crypto Market Cap - BTC - ETH."
        ),

        "btc_market_cap": item(
            btc_cap,
            "Total market cap multiplied by BTC dominance."
        ),

        "eth_market_cap": item(
            eth_cap,
            "Total market cap multiplied by ETH dominance."
        )
    }


# ============================================================
# BTC TECHNICAL DATA
# ============================================================

def btc_context(market):

    btc = (
        market.get("technical", {}).get("BTC", {})
    )

    indicators = btc.get("indicators", {})

    result = {
        "price": metric_value(
            btc.get("price_usdt")
        )
    }

    for key in (
        "ma20",
        "ma50",
        "ma200",
        "rsi14",
        "macd",
        "macd_signal"
    ):

        result[key] = metric_value(
            indicators.get(key)
        )

    result["source_updated_at"] = (
        btc.get("last_closed_candle_at")
    )

    return result


# ============================================================
# CYCLE CLASSIFICATION
# ============================================================

def classify_cycle(
    btc,
    fear_greed,
    alt_index,
    recession
):

    price = btc.get("price")
    ma20 = btc.get("ma20")
    ma50 = btc.get("ma50")
    ma200 = btc.get("ma200")
    rsi = btc.get("rsi14")

    required = [
        price,
        ma20,
        ma50,
        ma200
    ]

    if any(x is None for x in required):

        return {
            "zone_code": "INSUFFICIENT_DATA",
            "zone": "তথ্য অপর্যাপ্ত",
            "bull_run_status": "UNCONFIRMED",
            "bull_run_label": "Bull Run নিশ্চিত নয়",
            "confidence_score": 0,
            "bullish_evidence": [],
            "bearish_evidence": [
                "BTC Price/MA20/MA50/MA200 অসম্পূর্ণ।"
            ]
        }

    bullish = []
    bearish = []

    if price > ma200:
        bullish.append("BTC মূল্য Daily MA200-এর উপরে")
    else:
        bearish.append("BTC মূল্য Daily MA200-এর নিচে")

    if ma20 > ma50:
        bullish.append("Daily MA20, MA50-এর উপরে")
    else:
        bearish.append("Daily MA20, MA50-এর নিচে")

    if ma50 > ma200:
        bullish.append("Daily MA50, MA200-এর উপরে")
    else:
        bearish.append("Daily MA50, MA200-এর নিচে")

    if rsi is not None:

        if 50 <= rsi < 70:
            bullish.append("BTC RSI 50–70")

        elif rsi < 40:
            bearish.append("BTC RSI 40-এর নিচে")

        elif rsi >= 75:
            bearish.append("BTC RSI 75+: অতিরিক্ত উত্তাপের ঝুঁকি")

    if fear_greed is not None:

        if fear_greed >= 75:
            bearish.append("Fear & Greed 75+: অতিরিক্ত আশাবাদ")

        elif fear_greed <= 25:
            bearish.append("Fear & Greed 25 বা কম: চরম ভয়")

    alt_value = None

    if (
        isinstance(alt_index, dict)
        and alt_index.get("status") == "OK"
    ):

        alt_value = number(
            alt_index.get("value")
        )

        if alt_value is not None:

            if alt_value >= 75:
                bullish.append("Altcoin Season Index 75 বা বেশি")

            elif alt_value <= 25:
                bearish.append("Bitcoin Season Index 25 বা কম")

    if (
        isinstance(recession, dict)
        and recession.get("status") == "OK"
        and number(recession.get("value")) is not None
        and recession["value"] >= 0.50
    ):

        bearish.append("FRED Sahm Rule threshold triggered")

    bull_structure = (
        price > ma200
        and ma20 > ma50
        and ma50 > ma200
    )

    bear_structure = (
        price < ma200
        and ma20 < ma50
        and ma50 < ma200
    )

    if (
        bull_structure
        and rsi is not None
        and rsi >= 75
        and fear_greed is not None
        and fear_greed >= 75
    ):

        code = "LATE_BULL_EUPHORIA"
        label = "Late Bull / অতিরিক্ত উত্তাপ"
        status = "LATE_BULL"
        bull_label = "Bull Run-এর শেষ পর্যায়ের ঝুঁকি"

    elif (
        bull_structure
        and alt_value is not None
        and alt_value >= 75
    ):

        code = "ALTCOIN_SEASON"
        label = "Altcoin Season"
        status = "ACTIVE_BULL_ALTSEASON"
        bull_label = "Active Bull — Altcoin Season"

    elif bull_structure:

        code = "BULL_MARKET"
        label = "Bull Market"
        status = "ACTIVE_BULL"
        bull_label = "Active Bull Run"

    elif price > ma200 and ma20 > ma50:

        code = "EARLY_BULL"
        label = "Early Bull"
        status = "EARLY_BULL"
        bull_label = "প্রাথমিক Bullish Structure"

    elif bear_structure and rsi is not None and rsi < 45:

        code = "BEAR_ACCUMULATION_WATCH"
        label = "Bear / Accumulation Watch"
        status = "NOT_STARTED"
        bull_label = "Bull Run শুরু নিশ্চিত নয়"

    elif bear_structure:

        code = "BEAR_MARKET"
        label = "Bear Market"
        status = "NOT_STARTED"
        bull_label = "Bull Run শুরু নিশ্চিত নয়"

    elif price < ma200 and rsi is not None and rsi < 45:

        code = "BEARISH_RECOVERY_RISK"
        label = "Bearish Recovery Risk"
        status = "UNCONFIRMED"
        bull_label = "Recovery চলছে, Bull Run নিশ্চিত নয়"

    else:

        code = "TRANSITION"
        label = "Transition / মিশ্র বাজার"
        status = "UNCONFIRMED"
        bull_label = "Bull Run নিশ্চিত নয়"

    available = (
        4
        + (1 if rsi is not None else 0)
        + (1 if fear_greed is not None else 0)
        + (1 if alt_value is not None else 0)
    )

    confidence = round(
        available / 7 * 100
    )

    return {

        "zone_code": code,
        "zone": label,

        "bull_run_status": status,
        "bull_run_label": bull_label,

        "confidence_score": confidence,

        "bullish_evidence": bullish,
        "bearish_evidence": bearish,

        "confidence_note": (
            "এটি তথ্য ও সংকেতের Coverage Score; "
            "লাভের সম্ভাবনা বা Bull Run probability নয়।"
        )
    }


# ============================================================
# CYCLE HISTORY
# ============================================================

def update_history(previous, cycle, btc, caps):

    old = previous.get("cycle_history", [])

    if not isinstance(old, list):
        old = []

    today = utc_now().date().isoformat()

    history = [
        x for x in old
        if isinstance(x, dict)
        and x.get("date") != today
    ]

    history.append({

        "date": today,

        "zone_code": cycle.get("zone_code"),

        "bull_run_status": cycle.get(
            "bull_run_status"
        ),

        "btc_price": btc.get("price"),

        "eth_btc": None,

        "total2": caps.get(
            "total2", {}
        ).get("value"),

        "total3": caps.get(
            "total3", {}
        ).get("value")
    })

    cutoff = (
        utc_now().date()
        - timedelta(days=HISTORY_DAYS)
    )

    retained = []

    for item in history:

        try:

            day = datetime.strptime(
                item["date"],
                "%Y-%m-%d"
            ).date()

            if day >= cutoff:
                retained.append(item)

        except (ValueError, KeyError, TypeError):
            continue

    return retained


def phase_duration(history, current_status):

    if not history or not current_status:
        return None, None

    matching = []

    for item in reversed(history):

        if item.get("bull_run_status") != current_status:
            break

        matching.append(item.get("date"))

    if not matching:
        return None, None

    start_date = matching[-1]

    try:

        start = datetime.strptime(
            start_date,
            "%Y-%m-%d"
        ).date()

        days = (
            utc_now().date() - start
        ).days + 1

        return start_date, max(1, days)

    except (ValueError, TypeError):
        return None, None


# ============================================================
# BUILD OUTPUT
# ============================================================

def build():

    previous = read_json(OUTPUT_FILE)

    market = read_json(MARKET_FILE)
    advanced = read_json(ADVANCED_FILE)
    macro = read_json(MACRO_FILE)
    existing_zone = read_json(ZONE_FILE)

    alt_index = get_altcoin_season(previous)
    eth_btc = get_eth_btc()
    recession = get_recession_risk(previous)

    caps = build_market_caps(market)

    btc = btc_context(market)

    fear_item = market.get("fear_greed", {})

    fear_greed = metric_value(fear_item)

    fear_time = metric_time(fear_item)

    cycle = classify_cycle(
        btc,
        fear_greed,
        alt_index,
        recession
    )

    history = update_history(
        previous,
        cycle,
        btc,
        caps
    )

    if history:

        history[-1]["eth_btc"] = (
            eth_btc.get("value")
        )

    start_date, phase_days = phase_duration(
        history,
        cycle.get("bull_run_status")
    )

    mvrv = (
        advanced.get("on_chain", {})
        .get("mvrv_ratio", {})
    )

    if metric_value(mvrv) is None:

        mvrv_output = unavailable(
            "Advanced Engine",
            "Verified MVRV observation unavailable."
        )

    else:

        mvrv_output = mvrv

    data_quality = "GOOD"

    statuses = [
        alt_index.get("status"),
        eth_btc.get("status"),
        recession.get("status")
    ]

    if any(
        x not in ("OK", "TIME_UNKNOWN")
        for x in statuses
    ):
        data_quality = "PARTIAL"

    if cycle.get("zone_code") == "INSUFFICIENT_DATA":
        data_quality = "INSUFFICIENT"

    return {

        "schema_version": 1,

        "engine": "Crypto Market Cycle & Bull Run Tracker",

        "engine_version": VERSION,

        "generated_at": iso(),

        "update_mode": "scheduled_snapshot_not_realtime",

        "data_quality": data_quality,

        "data_policy": (
            "Existing engines are read-only. "
            "Missing, stale or timestamp-unknown data "
            "is never fabricated."
        ),

        "current_market_cycle": cycle,

        "bull_run_tracker": {

            "status": cycle.get("bull_run_status"),

            "label": cycle.get("bull_run_label"),

            "confidence_score": cycle.get(
                "confidence_score"
            ),

            "start_date": start_date,

            "days_in_current_phase": phase_days,

            "confidence_note": (
                "Coverage Score; not statistical probability."
            )
        },

        "recession_risk": recession,

        "altcoin_season": alt_index,

        "eth_btc_ratio": eth_btc,

        "altcoin_market_caps": caps,

        "btc_context": {

            **btc,

            "fear_greed": {

                "value": fear_greed,

                "source": fear_item.get("source"),

                "source_updated_at": fear_time
            }
        },

        "on_chain_context": {

            "mvrv": mvrv_output,

            "nupl": unavailable(
                "Advanced Engine",
                "Verified NUPL provider not configured."
            ),

            "sopr": unavailable(
                "Advanced Engine",
                "Verified SOPR provider not configured."
            ),

            "exchange_netflow": unavailable(
                "Advanced Engine",
                "Verified exchange netflow provider not configured."
            ),

            "exchange_reserves": unavailable(
                "Advanced Engine",
                "Verified exchange reserve provider not configured."
            ),

            "whale_activity": unavailable(
                "Advanced Engine",
                "Verified entity-labelled whale provider not configured."
            )
        },

        "existing_market_zone_engine": {

            "current_zone": existing_zone.get(
                "current_zone"
            ),

            "zone_code": existing_zone.get(
                "zone_code"
            ),

            "market_position": existing_zone.get(
                "market_position"
            ),

            "confidence": existing_zone.get(
                "confidence"
            ),

            "spot_action": existing_zone.get(
                "spot_action"
            ),

            "risk_level": existing_zone.get(
                "risk_level"
            ),

            "generated_at": existing_zone.get(
                "generated_at"
            )
        },

        "cycle_history": history,

        "methodology": {

            "bull_market": (
                "BTC price > MA200, MA20 > MA50, "
                "and MA50 > MA200."
            ),

            "early_bull": (
                "BTC price > MA200 and MA20 > MA50."
            ),

            "altcoin_season": (
                "BlockchainCenter 90-day index >=75."
            ),

            "late_bull_warning": (
                "Full bullish MA structure plus RSI >=75 "
                "and Fear & Greed >=75."
            ),

            "recession": (
                "FRED Sahm Rule >=0.50; "
                "not a forward probability forecast."
            ),

            "total2": (
                "Total market cap less BTC market cap."
            ),

            "total3": (
                "Total market cap less BTC and ETH market cap."
            )
        },

        "limitations": [

            "Bull Run stage is a rule-based classification, not a prediction.",

            "Altcoin Season Index updates daily.",

            "FRED Sahm Rule is monthly.",

            "ETH/BTC ticker has no verified exchange observation timestamp.",

            "TOTAL2 and TOTAL3 are derived from CoinGecko global data.",

            "NUPL, SOPR, exchange reserves, netflow and whale activity "
            "remain unavailable until verified sources are configured.",

            "Existing engines and their output files are not modified."
        ]
    }


# ============================================================
# ATOMIC OUTPUT
# ============================================================

def write_atomic(payload):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, temp = tempfile.mkstemp(
        dir=str(OUTPUT_FILE.parent),
        suffix=".tmp"
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                payload,
                f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            f.write("\n")

        os.replace(temp, OUTPUT_FILE)

    finally:

        if os.path.exists(temp):
            os.remove(temp)


def main():

    payload = build()

    write_atomic(payload)

    print("=" * 55)

    print("CRYPTO MARKET CYCLE & BULL RUN TRACKER")

    print("Version:", VERSION)

    print("Data Quality:", payload["data_quality"])

    print(
        "Current Zone:",
        payload["current_market_cycle"]["zone"]
    )

    print(
        "Bull Run:",
        payload["bull_run_tracker"]["label"]
    )

    print(
        "Altcoin Season:",
        payload["altcoin_season"].get("value")
    )

    print(
        "ETH/BTC:",
        payload["eth_btc_ratio"].get("value")
    )

    print(
        "Recession Risk:",
        payload["recession_risk"].get("value")
    )

    print("Output:", OUTPUT_FILE)

    print("=" * 55)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
