
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO FINAL DECISION ENGINE
Version: 1.0.0

INPUT:
    data/macro_data.json
    data/market_data.json

OUTPUT:
    data/decision_data.json

Spot market only.
No futures or margin recommendations.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MACRO_FILE = DATA_DIR / "macro_data.json"
MARKET_FILE = DATA_DIR / "market_data.json"
OUTPUT_FILE = DATA_DIR / "decision_data.json"

MACRO_MAX_AGE_HOURS = 72
MARKET_MAX_AGE_HOURS = 36
TECHNICAL_MAX_AGE_HOURS = 60


# =========================================================
# TIME AND DATA UTILITIES
# =========================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return (
        utc_now()
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_time(value):

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (TypeError, ValueError):
        return None


def hours_old(value):

    parsed = parse_time(value)

    if parsed is None:
        return None

    return max(
        0.0,
        (utc_now() - parsed).total_seconds() / 3600.0
    )


def finite_number(value):

    if isinstance(value, bool):
        return None

    try:
        number = float(value)

    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def read_json(path):

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            return None, "JSON root must be an object"

        return data, None

    except FileNotFoundError:
        return None, "File not found"

    except json.JSONDecodeError as exc:
        return None, "Invalid JSON: " + str(exc)

    except OSError as exc:
        return None, "File read error: " + str(exc)


def nested_value(obj, *keys):

    current = obj

    for key in keys:

        if not isinstance(current, dict):
            return None

        current = current.get(key)

    if isinstance(current, dict):

        if current.get("status") not in (None, "OK"):
            return None

        current = current.get("value")

    return finite_number(current)


def metric_value(metrics, key):

    item = metrics.get(key)

    if not isinstance(item, dict):
        return None

    if item.get("status") != "OK":
        return None

    return finite_number(item.get("value"))


def check_snapshot(name, timestamp, limit_hours):

    age = hours_old(timestamp)

    if age is None:
        status = "TIMESTAMP_UNKNOWN"

    elif age > limit_hours:
        status = "STALE"

    else:
        status = "FRESH"

    return {
        "name": name,
        "timestamp": timestamp,
        "age_hours": round(age, 2) if age is not None else None,
        "max_age_hours": limit_hours,
        "status": status
    }


# =========================================================
# INPUT LOADING
# =========================================================

def load_inputs():

    macro, macro_error = read_json(MACRO_FILE)
    market, market_error = read_json(MARKET_FILE)

    errors = []

    if macro_error:
        errors.append(
            "macro_data.json: " + macro_error
        )

    if market_error:
        errors.append(
            "market_data.json: " + market_error
        )

    return macro, market, errors


# =========================================================
# MACRO ANALYSIS
# =========================================================

def analyze_macro(macro):

    metrics = macro.get("metrics", {})
    summary = macro.get("summary", {})
    overall = macro.get("overall_macro_decision", {})

    if not isinstance(metrics, dict):
        metrics = {}

    if not isinstance(summary, dict):
        summary = {}

    if not isinstance(overall, dict):
        overall = {}

    overall_data = overall.get("DATA", {})

    if not isinstance(overall_data, dict):
        overall_data = {}

    decision = str(
        overall.get("DECISION", "UNKNOWN")
    ).upper()

    risk_score = finite_number(
        overall_data.get("risk_score")
    )

    support_score = finite_number(
        overall_data.get("support_score")
    )

    inflation = macro.get("inflation", {})

    if not isinstance(inflation, dict):
        inflation = {}

    cpi_yoy = finite_number(
        (inflation.get("cpi") or {}).get("yoy_percent")
    )

    core_pce_yoy = finite_number(
        (inflation.get("core_pce") or {}).get("yoy_percent")
    )

    vix = metric_value(metrics, "vix")

    sp_change = finite_number(
        (metrics.get("sp500") or {}).get("change_percent")
    )

    nasdaq_change = finite_number(
        (metrics.get("nasdaq") or {}).get("change_percent")
    )

    yield_10y_change = finite_number(
        (metrics.get("yield_10y") or {}).get("change")
    )

    liquidity = macro.get("liquidity", {})

    liquidity_trend = (
        liquidity.get("trend")
        if isinstance(liquidity, dict)
        else None
    )

    flags = []

    if decision == "REDUCE RISK":
        flags.append(
            "Macro engine-এর সামগ্রিক সিদ্ধান্ত REDUCE RISK।"
        )

    if cpi_yoy is not None and cpi_yoy >= 3.5:
        flags.append(
            "CPI YoY উচ্চ; inflation pressure রয়েছে।"
        )

    if core_pce_yoy is not None and core_pce_yoy >= 3.0:
        flags.append(
            "Core PCE YoY 3% বা তার বেশি।"
        )

    if vix is not None and vix >= 20:
        flags.append(
            "VIX 20-এর ওপরে; equity volatility elevated।"
        )

    if (
        sp_change is not None
        and nasdaq_change is not None
        and sp_change <= -1.5
        and nasdaq_change <= -1.5
    ):
        flags.append(
            "S&P 500 ও Nasdaq উভয়ই সর্বশেষ session-এ "
            "1.5% বা বেশি কমেছে।"
        )

    if (
        yield_10y_change is not None
        and yield_10y_change >= 0.05
    ):
        flags.append(
            "10Y Treasury yield-এর দৈনিক বৃদ্ধি "
            "0.05 percentage point বা বেশি।"
        )

    if liquidity_trend == "CONTRACTING":
        flags.append(
            "US Net Liquidity proxy-এর trend CONTRACTING।"
        )

    return {

        "decision": decision,

        "risk_score": risk_score,

        "support_score": support_score,

        "data_quality": summary.get(
            "data_quality", "UNKNOWN"
        ),

        "critical_series_available": summary.get(
            "critical_series_available"
        ),

        "critical_series_count": summary.get(
            "critical_series_count"
        ),

        "critical_missing": summary.get(
            "critical_missing", []
        ),

        "key_metrics": {

            "cpi_yoy_percent": cpi_yoy,

            "core_pce_yoy_percent": core_pce_yoy,

            "vix": vix,

            "sp500_daily_change_percent": sp_change,

            "nasdaq_daily_change_percent": nasdaq_change,

            "yield_10y_daily_change_pp": yield_10y_change,

            "net_liquidity_trend": liquidity_trend
        },

        "risk_flags": flags
    }


# =========================================================
# BTC / ETH TECHNICAL ANALYSIS
# =========================================================

def analyze_asset(market, symbol):

    technical = market.get("technical", {})

    asset = technical.get(symbol, {})

    if not isinstance(asset, dict):
        asset = {}

    indicators = asset.get("indicators", {})

    if not isinstance(indicators, dict):
        indicators = {}

    price = nested_value(
        asset, "price_usdt"
    )

    ma20 = nested_value(
        indicators, "ma20"
    )

    ma50 = nested_value(
        indicators, "ma50"
    )

    ma200 = nested_value(
        indicators, "ma200"
    )

    rsi = nested_value(
        indicators, "rsi14"
    )

    macd = nested_value(
        indicators, "macd"
    )

    macd_signal = nested_value(
        indicators, "macd_signal"
    )

    adx = nested_value(
        indicators, "adx14"
    )

    volume_ratio = nested_value(
        indicators, "volume_ratio_20d"
    )

    support = nested_value(
        indicators, "support_20d"
    )

    resistance = nested_value(
        indicators, "resistance_20d"
    )

    lower_band = nested_value(
        indicators, "bollinger_lower"
    )

    last_candle = asset.get(
        "last_closed_candle_at"
    )

    available = all(
        value is not None
        for value in (
            price,
            ma20,
            ma50,
            ma200,
            rsi
        )
    )

    if not available:

        trend = "INSUFFICIENT_DATA"

    elif price < ma20 and ma20 < ma50 and ma50 < ma200:

        trend = "STRONG_BEARISH"

    elif price < ma20 and ma20 < ma50:

        trend = "BEARISH"

    elif (
        price > ma20
        and ma20 > ma50
        and ma50 > ma200
    ):

        trend = "BULLISH"

    elif price > ma20 and price > ma50:

        trend = "RECOVERY_ATTEMPT"

    else:

        trend = "MIXED"

    signals = []

    if available:

        if price < ma20:
            signals.append(
                "দাম MA20-এর নিচে।"
            )

        if ma20 < ma50:
            signals.append(
                "MA20 < MA50; short/mid-term trend দুর্বল।"
            )

        if ma50 < ma200:
            signals.append(
                "MA50 < MA200; দীর্ঘমেয়াদি trend bearish।"
            )

        if rsi < 30:
            signals.append(
                "RSI 30-এর নিচে; oversold, "
                "কিন্তু reversal নিশ্চিত নয়।"
            )

        elif rsi >= 70:
            signals.append(
                "RSI 70 বা বেশি; overbought সতর্কতা।"
            )

        if (
            macd is not None
            and macd_signal is not None
            and macd < macd_signal
        ):
            signals.append(
                "MACD signal line-এর নিচে।"
            )

        if (
            support is not None
            and price < support
        ):
            signals.append(
                "দাম 20D support-এর নিচে; support breakdown।"
            )

        if (
            volume_ratio is not None
            and volume_ratio >= 1.2
        ):
            signals.append(
                "শেষ দিনের volume 20D average-এর তুলনায় বেশি।"
            )

    return {

        "symbol": symbol,

        "price_usdt": price,

        "ma20": ma20,

        "ma50": ma50,

        "ma200": ma200,

        "rsi14": rsi,

        "macd": macd,

        "macd_signal": macd_signal,

        "adx14": adx,

        "volume_ratio_20d": volume_ratio,

        "support_20d": support,

        "resistance_20d": resistance,

        "bollinger_lower": lower_band,

        "last_closed_candle_at": last_candle,

        "candle_count": asset.get("candle_count"),

        "trend": trend,

        "signals": signals,

        "data_complete": available
    }


# =========================================================
# DATA QUALITY AND SOURCE CONSISTENCY
# =========================================================

def detect_data_issues(macro, market):

    issues = []

    major_assets = market.get("major_assets", {})

    bitcoin = major_assets.get("bitcoin", {})

    cg_btc = nested_value(
        bitcoin, "price_usd"
    )

    technical = market.get("technical", {})

    btc_asset = technical.get("BTC", {})

    bn_btc = nested_value(
        btc_asset, "price_usdt"
    )

    if (
        cg_btc is not None
        and bn_btc is not None
        and cg_btc > 0
    ):

        difference = (
            abs(bn_btc - cg_btc) / cg_btc
        ) * 100.0

        if difference >= 1.0:

            issues.append(
                "BTC price source discrepancy: "
                "CoinGecko snapshot ও Binance technical price-এর "
                "পার্থক্য "
                + str(round(difference, 2))
                + "%। ভিন্ন source/timestamp হওয়ায় "
                "কোনো একটি value auto-correct করা হয়নি।"
            )

    metrics = macro.get("metrics", {})

    rrp_metric = metric_value(
        metrics, "reverse_repo"
    )

    liquidity = macro.get("liquidity", {})

    components = liquidity.get(
        "components", {}
    ) if isinstance(liquidity, dict) else {}

    rrp_component = finite_number(
        components.get("reverse_repo")
    )

    if (
        rrp_metric is not None
        and rrp_component is not None
        and abs(rrp_metric - rrp_component) > 0.001
    ):

        issues.append(
            "Net Liquidity RRP mismatch: "
            "metrics.reverse_repo="
            + str(rrp_metric)
            + "B, liquidity.components.reverse_repo="
            + str(rrp_component)
            + "B। Liquidity formula-এর aligned component "
            "আলাদা করে দেখানো হয়েছে।"
        )

    summary = macro.get("summary", {})

    if (
        summary.get("data_quality")
        == "GOOD_WITH_OPTIONAL_GAPS"
    ):

        issues.append(
            "Macro data quality GOOD_WITH_OPTIONAL_GAPS; "
            "optional Gold data unavailable।"
        )

    if market.get("update_mode") != "realtime":

        issues.append(
            "Market data scheduled snapshot; realtime feed নয়।"
        )

    return issues


# =========================================================
# FINAL DECISION ENGINE
# =========================================================

def build_decision(
    macro_result,
    btc,
    market_quality,
    macro_quality,
    market
):

    fear_greed = market.get(
        "fear_greed", {}
    )

    fg_value = nested_value(
        {"fg": fear_greed},
        "fg"
    )

    fg_class = (
        fear_greed.get("classification")
        if isinstance(fear_greed, dict)
        else None
    )

    global_market = market.get(
        "global_market", {}
    )

    btc_dom = nested_value(
        global_market,
        "btc_dominance_pct"
    )

    market_cap = nested_value(
        global_market,
        "total_market_cap_usd"
    )

    volume_24h = nested_value(
        global_market,
        "total_volume_24h_usd"
    )

    reasons = []
    actions = []
    risks = []

    data_blocked = (

        market_quality.get("status") != "FRESH"

        or macro_quality.get("status") != "FRESH"

        or not btc.get("data_complete")

        or btc.get("trend") == "INSUFFICIENT_DATA"
    )

    bearish_btc = btc.get(
        "trend"
    ) in (
        "BEARISH",
        "STRONG_BEARISH"
    )

    bullish_btc = (
        btc.get("trend") == "BULLISH"
    )

    macro_reduce = (
        macro_result.get("decision")
        == "REDUCE RISK"
    )

    support = btc.get("support_20d")

    price = btc.get("price_usdt")

    support_broken = (
        price is not None
        and support is not None
        and price < support
    )

    # DATA GATE

    if data_blocked:

        decision = "WAIT"

        reasons.append(
            "প্রয়োজনীয় ডেটা stale, timestamp অজানা, "
            "অথবা BTC technical data অসম্পূর্ণ।"
        )

        actions.append(
            "নতুন BUY/DCA স্থগিত রাখুন; "
            "নতুন নির্ভরযোগ্য snapshot সংগ্রহ করুন।"
        )

    # STRONG COMBINED BEARISH CONDITION

    elif (
        support_broken
        and bearish_btc
        and macro_reduce
    ):

        decision = "SELL"

        reasons.append(
            "BTC bearish structure, 20D support breakdown "
            "এবং Macro REDUCE RISK একসঙ্গে রয়েছে।"
        )

        actions.append(
            "ঝুঁকিপূর্ণ Altcoin exposure কমান। "
            "Macro signal একা সব asset sell করার নির্দেশ নয়।"
        )

    # BEARISH BTC + BEARISH MACRO

    elif bearish_btc and macro_reduce:

        decision = "REDUCE RISK"

        reasons.append(
            "Macro REDUCE RISK এবং BTC daily trend bearish।"
        )

        actions.append(
            "নতুন Altcoin BUY/DCA বন্ধ রাখুন। "
            "দুর্বল ও অতিরিক্ত ওজনের holdings পর্যালোচনা করুন।"
        )

    # BEARISH BTC

    elif bearish_btc:

        decision = "WAIT"

        reasons.append(
            "BTC daily trend bearish; oversold RSI একা buy signal নয়।"
        )

        actions.append(
            "নতুন BUY/DCA এড়িয়ে চলুন। "
            "Daily trend recovery নিশ্চিত না হওয়া পর্যন্ত অপেক্ষা করুন।"
        )

    # MACRO RISK

    elif macro_reduce:

        decision = "REDUCE RISK"

        reasons.append(
            "Macro risk elevated; BTC technical trend "
            "একা Macro risk বাতিল করছে না।"
        )

        actions.append(
            "নতুন Altcoin exposure সীমিত রাখুন; "
            "cash reserve বজায় রাখুন।"
        )

    # BULLISH MARKET

    elif bullish_btc:

        decision = "HOLD"

        reasons.append(
            "BTC daily trend bullish এবং Macro engine "
            "REDUCE RISK signal দিচ্ছে না।"
        )

        actions.append(
            "বর্তমান spot holdings HOLD করুন। "
            "নতুন BUY-এর আগে coin-level valuation "
            "ও fundamentals যাচাই করুন।"
        )

    else:

        decision = "WAIT"

        reasons.append(
            "Macro ও BTC trend থেকে একমুখী শক্তিশালী "
            "সিদ্ধান্ত পাওয়া যায়নি।"
        )

        actions.append(
            "নতুন BUY/DCA করার আগে trend confirmation অপেক্ষা করুন।"
        )

    # ADDITIONAL RISK WARNINGS

    if fg_value is not None and fg_value <= 20:

        reasons.append(
            "Fear & Greed Extreme Fear; "
            "এটি একা market bottom signal নয়।"
        )

    if (
        btc.get("rsi14") is not None
        and btc["rsi14"] < 30
    ):

        risks.append(
            "BTC RSI oversold; আরও পতন বা consolidation সম্ভব। "
            "Oversold মানেই reversal নয়।"
        )

    if (
        btc.get("ma20") is not None
        and btc.get("ma50") is not None
        and btc["ma20"] < btc["ma50"]
    ):

        risks.append(
            "BTC MA20 < MA50; short/mid-term trend দুর্বল।"
        )

    if (
        btc.get("ma50") is not None
        and btc.get("ma200") is not None
        and btc["ma50"] < btc["ma200"]
    ):

        risks.append(
            "BTC MA50 < MA200; দীর্ঘমেয়াদি bearish structure।"
        )

    if macro_reduce:

        risks.append(
            "Macro risk elevated; এটি coin-specific "
            "fundamental sell analysis নয়।"
        )

    if fg_value is None:

        risks.append(
            "Fear & Greed value unavailable; "
            "sentiment confirmation নেই।"
        )

    return {

        "decision": decision,

        "confidence_label": "RULE_BASED_NOT_PROBABILITY",

        "reasons": reasons,

        "actions": actions,

        "risk": risks,

        "market_context": {

            "fear_greed_value": fg_value,

            "fear_greed_classification": fg_class,

            "btc_dominance_percent": btc_dom,

            "total_market_cap_usd": market_cap,

            "total_volume_24h_usd": volume_24h
        },

        "important_note": (
            "এটি সামগ্রিক market-regime guidance; "
            "ব্যক্তিগত portfolio holdings-এর "
            "coin-by-coin SELL signal নয়।"
        )
    }


# =========================================================
# MAIN ENGINE
# =========================================================

def main():

    macro, market, errors = load_inputs()

    if errors:

        output = {

            "schema_version": 1,

            "engine": "Crypto Final Decision Engine",

            "engine_version": VERSION,

            "generated_at": iso_now(),

            "status": "ERROR",

            "decision": "WAIT",

            "errors": errors,

            "message": (
                "Input data পাওয়া যায়নি বা JSON invalid; "
                "কোনো market decision তৈরি করা হয়নি।"
            )
        }

        DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        OUTPUT_FILE.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2
            )
        )

        return 1

    macro_time = macro.get(
        "fetched_at"
    )

    market_time = market.get(
        "generated_at"
    )

    macro_quality = check_snapshot(
        "macro_data",
        macro_time,
        MACRO_MAX_AGE_HOURS
    )

    market_quality = check_snapshot(
        "market_data",
        market_time,
        MARKET_MAX_AGE_HOURS
    )

    btc = analyze_asset(
        market,
        "BTC"
    )

    eth = analyze_asset(
        market,
        "ETH"
    )

    technical_quality = check_snapshot(
        "BTC last closed daily candle",
        btc.get("last_closed_candle_at"),
        TECHNICAL_MAX_AGE_HOURS
    )

    eth_technical_quality = check_snapshot(
        "ETH last closed daily candle",
        eth.get("last_closed_candle_at"),
        TECHNICAL_MAX_AGE_HOURS
    )

    macro_result = analyze_macro(
        macro
    )

    issues = detect_data_issues(
        macro,
        market
    )

    # A fresh API fetch does not guarantee fresh candles.

    if technical_quality["status"] != "FRESH":

        market_quality = dict(
            market_quality
        )

        market_quality["status"] = (
            "STALE_TECHNICAL_CANDLES"
        )

    decision = build_decision(
        macro_result,
        btc,
        market_quality,
        macro_quality,
        market
    )

    overall_status = "OK"

    if (
        macro_quality["status"] != "FRESH"
        or market_quality["status"] != "FRESH"
        or not btc.get("data_complete")
    ):

        overall_status = "DATA_WARNING"

    output = {

        "schema_version": 1,

        "engine": "Crypto Final Decision Engine",

        "engine_version": VERSION,

        "generated_at": iso_now(),

        "status": overall_status,

        "data_quality": {

            "macro": macro_quality,

            "market": market_quality,

            "btc_technical": technical_quality,

            "eth_technical": eth_technical_quality,

            "issues": issues
        },

        "macro_analysis": macro_result,

        "crypto_market": {

            "global_market_cap_usd": nested_value(
                market.get("global_market", {}),
                "total_market_cap_usd"
            ),

            "global_volume_24h_usd": nested_value(
                market.get("global_market", {}),
                "total_volume_24h_usd"
            ),

            "btc_dominance_percent": nested_value(
                market.get("global_market", {}),
                "btc_dominance_pct"
            ),

            "fear_greed": market.get(
                "fear_greed", {}
            ),

            "btc": btc,

            "eth": eth
        },

        "final_decision": decision,

        "limitations": [

            "Rule-based engine; calibrated probability নয়।",

            "Macro decision একা crypto SELL signal নয়।",

            "BTC/ETH technical data 1D closed candles; "
            "intraday reversal ধরার জন্য নয়।",

            "ETF flows, crypto on-chain, whale flows, "
            "liquidation data ও derivatives positioning "
            "এখনো integrate করা হয়নি।",

            "Coin-specific tokenomics, unlocks, fundamentals "
            "ও portfolio weight এই engine-এ নেই।",

            "CoinGecko ও Binance price আলাদা source/time; "
            "source mismatch report করা হয়, auto-correct নয়।",

            "FRED macro observations প্রকাশে বিলম্বিত হতে পারে।"
        ]
    }

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    temp_file.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            allow_nan=False
        ),
        encoding="utf-8"
    )

    temp_file.replace(
        OUTPUT_FILE
    )

    print(
        "Crypto Final Decision Engine v"
        + VERSION
    )

    print(
        "Status: "
        + overall_status
    )

    print(
        "Decision: "
        + str(decision.get("decision"))
    )

    print(
        "BTC trend: "
        + str(btc.get("trend"))
    )

    print(
        "Macro decision: "
        + str(macro_result.get("decision"))
    )

    print(
        "Macro data: "
        + str(macro_quality.get("status"))
    )

    print(
        "Market data: "
        + str(market_quality.get("status"))
    )

    print(
        "Output: data/decision_data.json"
    )

    if issues:

        print(
            "Data issues: "
            + str(len(issues))
        )

        for issue in issues:
            print("- " + issue)

    return 0


if __name__ == "__main__":

    sys.exit(main())
