
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MACRO DASHBOARD - MACRO ENGINE
Version: 1.0
Output: data/macro_data.json

Data source:
- Federal Reserve Economic Data (FRED)
- FRED CSV export (no API key required where available)
- Official FRED API (optional FRED_API_KEY)

Important:
- DTWEXBGS is a broad trade-weighted USD index proxy,
  NOT the ICE DXY index.
- Missing or stale data is never replaced with zero.
- This engine provides macro context, not personal investment advice.
"""

import csv
import io
import json
import logging
import math
import os
import sys
import tempfile
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.0"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "macro_data.json"

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

TIMEOUT = 20
RETRIES = 2
MAX_WORKERS = 8

USER_AGENT = "CryptoMacroDashboard/1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

LOGGER = logging.getLogger("macro_engine")


# ============================================================
# FRED SERIES CONFIGURATION
# ============================================================

SERIES = {
    "fed_funds_rate": {
        "id": "DFF",
        "name": "Federal Funds Effective Rate",
        "unit": "%",
        "cadence": "daily",
        "risk_type": "rate"
    },
    "cpi": {
        "id": "CPIAUCSL",
        "name": "Consumer Price Index",
        "unit": "index",
        "cadence": "monthly",
        "risk_type": "inflation"
    },
    "core_cpi": {
        "id": "CPILFESL",
        "name": "Core CPI",
        "unit": "index",
        "cadence": "monthly",
        "risk_type": "inflation"
    },
    "pce": {
        "id": "PCEPI",
        "name": "PCE Price Index",
        "unit": "index",
        "cadence": "monthly",
        "risk_type": "inflation"
    },
    "core_pce": {
        "id": "PCEPILFE",
        "name": "Core PCE Price Index",
        "unit": "index",
        "cadence": "monthly",
        "risk_type": "inflation"
    },
    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "%",
        "cadence": "monthly",
        "risk_type": "labor"
    },
    "nonfarm_payrolls": {
        "id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "unit": "thousands",
        "cadence": "monthly",
        "risk_type": "labor"
    },
    "yield_2y": {
        "id": "DGS2",
        "name": "US 2-Year Treasury Yield",
        "unit": "%",
        "cadence": "daily",
        "risk_type": "yield"
    },
    "yield_10y": {
        "id": "DGS10",
        "name": "US 10-Year Treasury Yield",
        "unit": "%",
        "cadence": "daily",
        "risk_type": "yield"
    },
    "yield_30y": {
        "id": "DGS30",
        "name": "US 30-Year Treasury Yield",
        "unit": "%",
        "cadence": "daily",
        "risk_type": "yield"
    },
    "yield_curve_10y_2y": {
        "id": "T10Y2Y",
        "name": "10Y-2Y Treasury Spread",
        "unit": "%",
        "cadence": "daily",
        "risk_type": "yield_curve"
    },
    "usd_broad_index": {
        "id": "DTWEXBGS",
        "name": "Trade Weighted US Dollar Index",
        "unit": "index",
        "cadence": "daily",
        "risk_type": "dollar"
    },
    "vix": {
        "id": "VIXCLS",
        "name": "CBOE Volatility Index",
        "unit": "index",
        "cadence": "daily",
        "risk_type": "volatility"
    },
    "sp500": {
        "id": "SP500",
        "name": "S&P 500",
        "unit": "index",
        "cadence": "daily",
        "risk_type": "equity"
    },
    "nasdaq": {
        "id": "NASDAQCOM",
        "name": "NASDAQ Composite",
        "unit": "index",
        "cadence": "daily",
        "risk_type": "equity"
    },
    "oil": {
        "id": "DCOILWTICO",
        "name": "WTI Crude Oil",
        "unit": "USD/barrel",
        "cadence": "daily",
        "risk_type": "commodity"
    },
    "gold": {
        "id": "GOLDAMGBD228NLBM",
        "name": "London Gold Price AM",
        "unit": "USD/oz",
        "cadence": "daily",
        "risk_type": "commodity"
    },
    "usd_jpy": {
        "id": "DEXJPUS",
        "name": "Japanese Yen per US Dollar",
        "unit": "JPY/USD",
        "cadence": "daily",
        "risk_type": "currency"
    },
    "fed_balance_sheet": {
        "id": "WALCL",
        "name": "Federal Reserve Total Assets",
        "unit": "millions USD",
        "cadence": "weekly",
        "risk_type": "liquidity"
    },
    "reverse_repo": {
        "id": "RRPONTSYD",
        "name": "Overnight Reverse Repurchase Agreements",
        "unit": "billions USD",
        "cadence": "daily",
        "risk_type": "liquidity"
    },
    "treasury_general_account": {
        "id": "WTREGEN",
        "name": "Treasury General Account",
        "unit": "millions USD",
        "cadence": "weekly",
        "risk_type": "liquidity"
    },
    "m2_money_supply": {
        "id": "M2SL",
        "name": "M2 Money Supply",
        "unit": "billions USD",
        "cadence": "monthly",
        "risk_type": "liquidity"
    }
}


# ============================================================
# FRESHNESS POLICY
# ============================================================

FRESHNESS_DAYS = {
    "daily": 7,
    "weekly": 18,
    "monthly": 55,
    "quarterly": 120
}


# ============================================================
# TIME AND JSON HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None


def safe_number(value):
    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (ValueError, TypeError):
        return None


def percentage_change(current, previous):
    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100


def round_value(value, digits=4):
    if value is None:
        return None

    return round(value, digits)


# ============================================================
# HTTP CLIENT
# ============================================================

def http_get(url):
    last_error = None

    for attempt in range(RETRIES + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/csv, application/json"
                }
            )

            with urlopen(request, timeout=TIMEOUT) as response:
                return response.read().decode("utf-8-sig")

        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)

            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(last_error or "HTTP request failed")


# ============================================================
# FRED DATA FETCH
# ============================================================

def fetch_fred_csv(series_id):
    params = urlencode({"id": series_id})
    url = f"{FRED_CSV_URL}?{params}"

    raw = http_get(url)

    reader = csv.DictReader(io.StringIO(raw))
    observations = []

    for row in reader:
        date_text = (
            row.get("observation_date")
            or row.get("DATE")
            or row.get("date")
        )

        value_text = (
            row.get(series_id)
            or row.get("value")
        )

        date = parse_date(date_text)
        value = safe_number(value_text)

        if date is None or value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    return observations


def fetch_fred_api(series_id):
    params = urlencode({
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc"
    })

    url = f"{FRED_API_URL}?{params}"

    raw = http_get(url)
    payload = json.loads(raw)

    observations = []

    for item in payload.get("observations", []):
        date_text = item.get("date")
        value = safe_number(item.get("value"))

        if parse_date(date_text) is None or value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    return observations


def fetch_series(series_id):
    if FRED_API_KEY:
        try:
            return fetch_fred_api(series_id), "FRED API"
        except Exception as exc:
            LOGGER.warning(
                "%s API failed; trying CSV: %s",
                series_id,
                exc
            )

    return fetch_fred_csv(series_id), "FRED CSV"


# ============================================================
# OBSERVATION PROCESSING
# ============================================================

def classify_freshness(observation_date, cadence):
    date = parse_date(observation_date)

    if date is None:
        return "UNAVAILABLE"

    age_days = (utc_now() - date).total_seconds() / 86400

    threshold = FRESHNESS_DAYS.get(cadence, 7)

    if age_days > threshold:
        return "STALE"

    return "OK"


def build_metric(key, config, observations, source):
    fetched_at = iso_now()

    if not observations:
        return {
            "key": key,
            "name": config["name"],
            "value": None,
            "unit": config["unit"],
            "observation_date": None,
            "previous_value": None,
            "previous_date": None,
            "change": None,
            "change_percent": None,
            "source": source,
            "fetched_at": fetched_at,
            "status": "UNAVAILABLE",
            "error": "No valid observations"
        }

    observations.sort(key=lambda item: item["date"])

    current = observations[-1]

    previous = (
        observations[-2]
        if len(observations) >= 2
        else None
    )

    status = classify_freshness(
        current["date"],
        config["cadence"]
    )

    change = None
    change_percent = None

    if previous:
        change = current["value"] - previous["value"]

        change_percent = percentage_change(
            current["value"],
            previous["value"]
        )

    return {
        "key": key,
        "name": config["name"],
        "value": round_value(current["value"]),
        "unit": config["unit"],
        "observation_date": current["date"],
        "previous_value": (
            round_value(previous["value"])
            if previous else None
        ),
        "previous_date": (
            previous["date"]
            if previous else None
        ),
        "change": round_value(change),
        "change_percent": round_value(change_percent),
        "source": source,
        "fetched_at": fetched_at,
        "status": status,
        "error": None if status == "OK" else "Observation is stale"
    }


# ============================================================
# INFLATION CALCULATIONS
# ============================================================

def historical_change(observations, periods):
    if len(observations) <= periods:
        return None

    current = observations[-1]["value"]
    previous = observations[-1 - periods]["value"]

    return round_value(
        percentage_change(current, previous),
        3
    )


def build_inflation_report(metrics, observations_by_key):
    inflation_keys = {
        "cpi": "CPI",
        "core_cpi": "Core CPI",
        "pce": "PCE",
        "core_pce": "Core PCE"
    }

    result = {}

    for key, label in inflation_keys.items():
        metric = metrics.get(key)
        observations = observations_by_key.get(key, [])

        if not metric or metric["status"] != "OK":
            result[key] = {
                "name": label,
                "mom_percent": None,
                "yoy_percent": None,
                "status": "UNAVAILABLE"
            }
            continue

        result[key] = {
            "name": label,
            "mom_percent": historical_change(observations, 1),
            "yoy_percent": historical_change(observations, 12),
            "status": "OK"
        }

    return result


# ============================================================
# NFP CHANGE
# ============================================================

def calculate_payroll_change(observations):
    if len(observations) < 2:
        return None

    return round_value(
        observations[-1]["value"] -
        observations[-2]["value"],
        1
    )


# ============================================================
# INDICATOR REPORT ENGINE
# ============================================================

def report(
    data,
    title,
    analysis,
    decision,
    action,
    risk
):
    return {
        "DATA": data,
        "ANALYSIS": analysis,
        "DECISION": decision,
        "ACTION": action,
        "RISK": risk
    }


def get_metric(metrics, key):
    metric = metrics.get(key)

    if not metric:
        return None

    if metric.get("status") != "OK":
        return None

    return metric.get("value")


def build_indicator_reports(metrics, inflation):
    reports = {}

    # --------------------------------------------------------
    # CPI
    # --------------------------------------------------------

    cpi = inflation.get("cpi", {})
    cpi_yoy = cpi.get("yoy_percent")
    cpi_mom = cpi.get("mom_percent")

    if cpi_yoy is None:
        reports["cpi"] = report(
            None,
            "CPI",
            "CPI data unavailable or stale.",
            "WAIT — INSUFFICIENT DATA",
            "CPI-ভিত্তিক নতুন সিদ্ধান্ত নেবেন না।",
            "মুদ্রাস্ফীতির বর্তমান চাপ যাচাই করা যাচ্ছে না।"
        )
    else:
        if cpi_yoy >= 4:
            decision = "REDUCE RISK"
            action = "CPI YoY উচ্চ—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "মুদ্রাস্ফীতির চাপ বেশি।"
            risk = "Fed-এর কঠোর নীতির ঝুঁকি বাড়ছে।"

        elif cpi_yoy >= 3:
            decision = "WAIT"
            action = "নতুন ঝুঁকিপূর্ণ BUY এড়িয়ে চলুন।"
            analysis = "মুদ্রাস্ফীতি এখনো লক্ষ্যমাত্রার ওপরে।"
            risk = "Rate cut প্রত্যাশা দুর্বল হতে পারে।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "মুদ্রাস্ফীতি কমার প্রবণতা পর্যবেক্ষণ করুন।"
            analysis = "CPI YoY তুলনামূলকভাবে নিয়ন্ত্রিত।"
            risk = "একটি CPI রিপোর্ট দিয়ে Fed policy নিশ্চিত হয় না।"

        reports["cpi"] = report(
            {
                "yoy_percent": cpi_yoy,
                "mom_percent": cpi_mom
            },
            "CPI",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # CORE CPI
    # --------------------------------------------------------

    core_cpi = inflation.get("core_cpi", {})
    core_cpi_yoy = core_cpi.get("yoy_percent")

    if core_cpi_yoy is None:
        reports["core_cpi"] = report(
            None,
            "Core CPI",
            "Core CPI data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Core CPI-ভিত্তিক সিদ্ধান্ত স্থগিত রাখুন।",
            "Underlying inflation যাচাই করা যাচ্ছে না।"
        )
    else:
        if core_cpi_yoy >= 4:
            decision = "REDUCE RISK"
            action = "Core CPI উচ্চ—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "Underlying inflation শক্তিশালী।"
            risk = "Monetary policy দীর্ঘ সময় restrictive থাকতে পারে."

        elif core_cpi_yoy >= 3:
            decision = "WAIT"
            action = "নতুন BUY সীমিত রাখুন।"
            analysis = "Core inflation এখনো বেশি।"
            risk = "দ্রুত rate cut প্রত্যাশা ঝুঁকিপূর্ণ।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "Core inflation trend পর্যবেক্ষণ করুন।"
            analysis = "Core CPI তুলনামূলকভাবে নিয়ন্ত্রিত।"
            risk = "অন্যান্য inflation ও labor data-ও গুরুত্বপূর্ণ।"

        reports["core_cpi"] = report(
            {"yoy_percent": core_cpi_yoy},
            "Core CPI",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # PCE
    # --------------------------------------------------------

    pce = inflation.get("pce", {})
    pce_yoy = pce.get("yoy_percent")

    if pce_yoy is None:
        reports["pce"] = report(
            None,
            "PCE",
            "PCE data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "PCE-ভিত্তিক সিদ্ধান্ত নেবেন না।",
            "Fed-এর preferred inflation measure অনুপস্থিত।"
        )
    else:
        if pce_yoy >= 3:
            decision = "REDUCE RISK"
            action = "PCE উচ্চ—ঝুঁকিপূর্ণ exposure কমান।"
            analysis = "Fed-এর inflation target থেকে PCE দূরে।"
            risk = "Rate cut বিলম্বিত হওয়ার ঝুঁকি।"

        elif pce_yoy > 2:
            decision = "WAIT"
            action = "Macro confirmation না পাওয়া পর্যন্ত সতর্ক থাকুন।"
            analysis = "PCE target-এর ওপরে।"
            risk = "Inflation আবার বাড়ার ঝুঁকি রয়েছে।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "অন্যান্য macro data-এর সঙ্গে মিলিয়ে দেখুন।"
            analysis = "PCE target-এর কাছাকাছি বা নিচে।"
            risk = "একক রিপোর্ট থেকে monetary easing নিশ্চিত নয়।"

        reports["pce"] = report(
            {"yoy_percent": pce_yoy},
            "PCE",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # CORE PCE
    # --------------------------------------------------------

    core_pce = inflation.get("core_pce", {})
    core_pce_yoy = core_pce.get("yoy_percent")

    if core_pce_yoy is None:
        reports["core_pce"] = report(
            None,
            "Core PCE",
            "Core PCE unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Core PCE-ভিত্তিক সিদ্ধান্ত স্থগিত রাখুন।",
            "Underlying PCE inflation যাচাই করা যাচ্ছে না।"
        )
    else:
        if core_pce_yoy >= 3:
            decision = "REDUCE RISK"
            action = "Core PCE উচ্চ—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "Underlying PCE inflation বেশি।"
            risk = "Fed rate cut বিলম্বিত হওয়ার ঝুঁকি।"

        elif core_pce_yoy > 2:
            decision = "WAIT"
            action = "নতুন BUY-তে সতর্ক থাকুন।"
            analysis = "Core PCE এখনো target-এর ওপরে।"
            risk = "Inflation persistence-এর ঝুঁকি।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "Inflation trend পর্যবেক্ষণ করুন।"
            analysis = "Core PCE তুলনামূলকভাবে নিয়ন্ত্রিত।"
            risk = "অন্যান্য অর্থনৈতিক সূচকও যাচাই প্রয়োজন।"

        reports["core_pce"] = report(
            {"yoy_percent": core_pce_yoy},
            "Core PCE",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # FED RATE
    # --------------------------------------------------------

    fed_rate = get_metric(metrics, "fed_funds_rate")

    if fed_rate is None:
        reports["fed_rate"] = report(
            None,
            "Fed Rate",
            "Fed rate unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Fed policy সম্পর্কে নিশ্চিত সিদ্ধান্ত নেবেন না।",
            "বর্তমান policy rate যাচাই করা যাচ্ছে না।"
        )
    else:
        reports["fed_rate"] = report(
            {"percent": fed_rate},
            "Fed Rate",
            "বর্তমান effective Fed funds rate যাচাই করা হয়েছে।",
            "HOLD / SELECTIVE",
            "Fed rate-কে CPI, PCE, employment ও bond yield-এর সঙ্গে বিশ্লেষণ করুন।",
            "Fed funds rate একা পরবর্তী FOMC সিদ্ধান্ত নির্দেশ করে না।"
        )

    # --------------------------------------------------------
    # LABOR MARKET
    # --------------------------------------------------------

    unemployment = get_metric(metrics, "unemployment")
    payroll_change = metrics.get(
        "nonfarm_payrolls", {}
    ).get("monthly_change_thousands")

    labor_available = (
        unemployment is not None
        and payroll_change is not None
    )

    if not labor_available:
        reports["labor_market"] = report(
            None,
            "US Labor Market",
            "Employment data incomplete.",
            "WAIT — INSUFFICIENT DATA",
            "Labor market নিয়ে নিশ্চিত সিদ্ধান্ত নেবেন না।",
            "Unemployment বা NFP data অনুপস্থিত।"
        )
    else:
        if unemployment >= 5 or payroll_change < 0:
            decision = "REDUCE RISK"
            action = "Labor market দুর্বল—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "Employment deterioration দেখা যাচ্ছে।"
            risk = "Economic slowdown ও recession risk বাড়তে পারে।"

        elif unemployment >= 4.5:
            decision = "WAIT"
            action = "নতুন BUY সীমিত রাখুন।"
            analysis = "Labor market দুর্বল হওয়ার লক্ষণ রয়েছে।"
            risk = "Economic slowdown risk পর্যবেক্ষণ করুন।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "Employment trend পর্যবেক্ষণ করুন।"
            analysis = "Labor market তুলনামূলকভাবে স্থিতিশীল।"
            risk = "শক্তিশালী employment inflation pressure বাড়াতে পারে।"

        reports["labor_market"] = report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "US Labor Market",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # TREASURY YIELDS
    # --------------------------------------------------------

    yield_10y = metrics.get("yield_10y", {})
    yield_10y_change = yield_10y.get("change")

    if yield_10y.get("status") != "OK" or yield_10y_change is None:
        reports["bond_yields"] = report(
            None,
            "US Treasury Yields",
            "Yield data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Bond yield trend যাচাই না হওয়া পর্যন্ত macro risk নির্ধারণ করবেন না।",
            "Yield movement অনুপস্থিত।"
        )
    else:
        if yield_10y_change >= 0.05:
            decision = "REDUCE RISK"
            action = "10Y yield দ্রুত বাড়ছে—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "দীর্ঘমেয়াদি borrowing cost বাড়ছে।"
            risk = "Risk asset valuation-এর ওপর চাপ তৈরি হচ্ছে।"

        elif yield_10y_change <= -0.05:
            decision = "HOLD / SELECTIVE"
            action = "Yield কমার প্রবণতা BTC ও Altcoin trend-এর সঙ্গে যাচাই করুন।"
            analysis = "10Y yield কমছে।"
            risk = "Yield পতন growth concern থেকেও হতে পারে।"

        else:
            decision = "WAIT"
            action = "Bond yield movement পর্যবেক্ষণ করুন।"
            analysis = "10Y yield-এ বড় দৈনিক পরিবর্তন নেই।"
            risk = "দিক নির্ধারণে আরও data প্রয়োজন।"

        reports["bond_yields"] = report(
            {
                "2y": get_metric(metrics, "yield_2y"),
                "10y": get_metric(metrics, "yield_10y"),
                "30y": get_metric(metrics, "yield_30y"),
                "10y_daily_change": yield_10y_change
            },
            "US Treasury Yields",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # BROAD USD INDEX PROXY
    # --------------------------------------------------------

    dollar = metrics.get("usd_broad_index", {})
    dollar_change = dollar.get("change_percent")

    if dollar.get("status") != "OK" or dollar_change is None:
        reports["usd_index"] = report(
            None,
            "Broad USD Index Proxy",
            "Dollar data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "USD trend যাচাই না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",
            "এটি ICE DXY নয়; broad dollar proxy।"
        )
    else:
        if dollar_change >= 0.30:
            decision = "REDUCE RISK"
            action = "Broad USD index বাড়ছে—ঝুঁকিপূর্ণ Altcoin exposure কমান।"
            analysis = "Dollar strength risk assets-এর জন্য চাপ তৈরি করছে।"
            risk = "এটি ICE DXY নয়, broad dollar proxy।"

        elif dollar_change <= -0.30:
            decision = "HOLD / SELECTIVE"
            action = "USD দুর্বলতা BTC ও Altcoin trend-এর সঙ্গে যাচাই করুন।"
            analysis = "Broad dollar index দুর্বল হচ্ছে।"
            risk = "USD দুর্বল হলেই Crypto bullish হয় না।"

        else:
            decision = "WAIT"
            action = "USD trend পর্যবেক্ষণ করুন।"
            analysis = "Broad dollar index-এ বড় পরিবর্তন নেই।"
            risk = "এই সূচক ICE DXY-এর বিকল্প নয়।"

        reports["usd_index"] = report(
            {"daily_change_percent": dollar_change},
            "Broad USD Index Proxy",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    vix = get_metric(metrics, "vix")

    if vix is None:
        reports["vix"] = report(
            None,
            "VIX",
            "VIX data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Volatility risk যাচাই না হওয়া পর্যন্ত সতর্ক থাকুন।",
            "বর্তমান VIX যাচাই করা যাচ্ছে না।"
        )
    else:
        if vix >= 30:
            decision = "REDUCE RISK"
            action = "VIX অত্যন্ত উচ্চ—Crypto risk exposure কমান।"
            analysis = "Equity market volatility stress level-এ রয়েছে।"
            risk = "Risk-off sentiment দ্রুত ছড়াতে পারে।"

        elif vix >= 25:
            decision = "REDUCE RISK"
            action = "VIX উচ্চ—নতুন ঝুঁকিপূর্ণ BUY বন্ধ রাখুন।"
            analysis = "Market uncertainty বেড়েছে।"
            risk = "Crypto volatility আরও বাড়তে পারে।"

        elif vix >= 18:
            decision = "WAIT"
            action = "নতুন BUY-তে সতর্ক থাকুন।"
            analysis = "Volatility elevated।"
            risk = "Risk sentiment স্থিতিশীল নয়।"

        else:
            decision = "HOLD / SELECTIVE"
            action = "কম VIX-কে একমাত্র BUY signal হিসেবে ব্যবহার করবেন না।"
            analysis = "Equity volatility তুলনামূলক কম।"
            risk = "VIX কম থাকলেও Crypto-specific risk থাকে।"

        reports["vix"] = report(
            {"value": vix},
            "VIX",
            analysis,
            decision,
            action,
            risk
        )

    # --------------------------------------------------------
    # EQUITY MARKET
    # --------------------------------------------------------

    sp500 = get_metric(metrics, "sp500")
    nasdaq = get_metric(metrics, "nasdaq")

    equity_available = sp500 is not None and nasdaq is not None

    if not equity_available:
        reports["equity_market"] = report(
            None,
            "US Equity Market",
            "Equity data incomplete.",
            "WAIT — INSUFFICIENT DATA",
            "Stock market direction যাচাই করুন।",
            "S&P 500 বা Nasdaq data অনুপস্থিত।"
        )
    else:
        reports["equity_market"] = report(
            {
                "sp500": sp500,
                "nasdaq": nasdaq
            },
            "US Equity Market",
            "S&P 500 ও Nasdaq-এর সর্বশেষ উপলব্ধ closing value পাওয়া গেছে।",
            "HOLD / SELECTIVE",
            "Equity trend-কে VIX, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।",
            "Closing index value একা market trend নিশ্চিত করে না।"
        )

    # --------------------------------------------------------
    # COMMODITIES
    # --------------------------------------------------------

    oil = get_metric(metrics, "oil")
    gold = get_metric(metrics, "gold")

    reports["commodities"] = report(
        {
            "wti_oil_usd": oil,
            "gold_usd_oz": gold,
            "gold_data_status": metrics.get("gold", {}).get("status")
        },
        "Oil & Gold",
        "Oil ও Gold-এর সর্বশেষ উপলব্ধ FRED observations।",
        (
            "HOLD / SELECTIVE"
            if oil is not None or gold is not None
            else "WAIT — INSUFFICIENT DATA"
        ),
        "Oil inflation pressure এবং Gold safe-haven demand হিসেবে পর্যবেক্ষণ করুন।",
        "Gold fixing data পুরোনো হতে পারে; STALE হলে live price হিসেবে ব্যবহার করবেন না।"
    )

    # --------------------------------------------------------
    # YEN
    # --------------------------------------------------------

    yen = get_metric(metrics, "usd_jpy")

    if yen is None:
        reports["yen"] = report(
            None,
            "USD/JPY",
            "USD/JPY data unavailable.",
            "WAIT — INSUFFICIENT DATA",
            "Yen carry-trade risk সম্পর্কে নিশ্চিত সিদ্ধান্ত নেবেন না।",
            "BOJ policy ও JGB yield data এই engine-এ সম্পূর্ণ নেই।"
        )
    else:
        reports["yen"] = report(
            {"jpy_per_usd": yen},
            "USD/JPY",
            "USD/JPY exchange rate পাওয়া গেছে।",
            "WAIT",
            "Yen movement-এর সঙ্গে BOJ policy ও Japanese bond yield পর্যবেক্ষণ করুন।",
            "শুধু USD/JPY দিয়ে carry-trade unwind নিশ্চিত করা যায় না।"
        )

    # --------------------------------------------------------
    # LIQUIDITY
    # --------------------------------------------------------

    fed_assets = get_metric(metrics, "fed_balance_sheet")
    rrp = get_metric(metrics, "reverse_repo")
    tga = get_metric(metrics, "treasury_general_account")
    m2 = get_metric(metrics, "m2_money_supply")

    liquidity_available = all(
        value is not None
        for value in [fed_assets, rrp, tga, m2]
    )

    if liquidity_available:
        decision = "HOLD / SELECTIVE"
        analysis = "Fed assets, RRP, TGA ও M2-এর latest observations পাওয়া গেছে।"
        action = "সব series-এর পরিবর্তন একত্রে বিশ্লেষণ করুন; একটি metric দিয়ে liquidity সিদ্ধান্ত নেবেন না।"
        risk = "এটি পূর্ণ global liquidity composite নয়।"
    else:
        decision = "WAIT — INSUFFICIENT DATA"
        analysis = "Liquidity data incomplete."
        action = "Global liquidity সম্পর্কে নিশ্চিত সিদ্ধান্ত নেবেন না।"
        risk = "Missing data-এর কারণে liquidity direction নির্ধারণ করা যাচ্ছে না।"

    reports["liquidity"] = report(
        {
            "fed_balance_sheet": fed_assets,
            "reverse_repo": rrp,
            "treasury_general_account": tga,
            "m2": m2
        },
        "US Liquidity",
        analysis,
        decision,
        action,
        risk
    )

    return reports


# ============================================================
# OVERALL MACRO DECISION
# ============================================================

def build_overall_decision(metrics):
    required = [
        "usd_broad_index",
        "vix",
        "yield_10y"
    ]

    missing = [
        key for key in required
        if metrics.get(key, {}).get("status") != "OK"
    ]

    if missing:
        return {
            "DATA": {
                "required_metrics": required,
                "missing_metrics": missing
            },
            "ANALYSIS": "প্রয়োজনীয় Macro data সম্পূর্ণ বা fresh নয়।",
            "DECISION": "WAIT — INSUFFICIENT DATA",
            "ACTION": "Macro data সম্পূর্ণ না হওয়া পর্যন্ত নতুন risk-on সিদ্ধান্ত নেবেন না।",
            "RISK": "অসম্পূর্ণ data থেকে ভুল market assessment হতে পারে।"
        }

    dollar = metrics["usd_broad_index"]
    vix = metrics["vix"]
    yield_10y = metrics["yield_10y"]

    dollar_change = dollar.get("change_percent")
    vix_value = vix.get("value")
    yield_change = yield_10y.get("change")

    if (
        dollar_change is None
        or vix_value is None
        or yield_change is None
    ):
        return {
            "DATA": None,
            "ANALYSIS": "প্রয়োজনীয় পরিবর্তনের হিসাব অনুপস্থিত।",
            "DECISION": "WAIT — INSUFFICIENT DATA",
            "ACTION": "নির্ভরযোগ্য change data সংগ্রহ করুন।",
            "RISK": "শুধু বর্তমান level দিয়ে macro direction নির্ধারণ করা যাচ্ছে না।"
        }

    risk_flags = []
    support_flags = []

    if dollar_change >= 0.30:
        risk_flags.append("Broad USD index increased")

    if vix_value >= 25:
        risk_flags.append("VIX elevated")

    if yield_change >= 0.05:
        risk_flags.append("10Y yield increased")

    if dollar_change <= -0.30:
        support_flags.append("Broad USD index decreased")

    if vix_value < 18:
        support_flags.append("VIX low")

    if yield_change <= -0.05:
        support_flags.append("10Y yield decreased")

    if len(risk_flags) >= 2:
        decision = "REDUCE RISK"
        action = (
            "Macro risk elevated—ঝুঁকিপূর্ণ Altcoin exposure কমান "
            "এবং নতুন BUY সীমিত রাখুন।"
        )
        analysis = "একাধিক Macro risk indicator একসঙ্গে চাপ তৈরি করছে।"
        risk = "BTC trend, ETF flows ও crypto liquidity-ও যাচাই করা প্রয়োজন।"

    elif len(support_flags) >= 2 and not risk_flags:
        decision = "HOLD / SELECTIVE"
        action = (
            "Macro পরিবেশ তুলনামূলক সহায়ক—তবুও "
            "BTC trend ও market breadth ছাড়া aggressive BUY নয়।"
        )
        analysis = "একাধিক Macro indicator তুলনামূলক সহায়ক।"
        risk = "Macro support নিশ্চিত Bull market signal নয়।"

    else:
        decision = "WAIT"
        action = "নতুন বড় risk exposure নেবেন না; BTC ও Macro trend পর্যবেক্ষণ করুন।"
        analysis = "Macro signal মিশ্র বা অপর্যাপ্ত।"
        risk = "দিক নির্ধারণের জন্য আরও confirmation প্রয়োজন।"

    return {
        "DATA": {
            "broad_usd_daily_change_percent": dollar_change,
            "vix": vix_value,
            "10y_yield_daily_change_percentage_points": yield_change,
            "risk_flags": risk_flags,
            "support_flags": support_flags
        },
        "ANALYSIS": analysis,
        "DECISION": decision,
        "ACTION": action,
        "RISK": risk
    }


# ============================================================
# FETCH ALL SERIES
# ============================================================

def fetch_all_series():
    metrics = {}
    observations_by_key = {}

    def worker(key, config):
        observations, source = fetch_series(config["id"])

        metric = build_metric(
            key,
            config,
            observations,
            source
        )

        return key, metric, observations

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(worker, key, config): key
            for key, config in SERIES.items()
        }

        for future in as_completed(futures):
            key = futures[future]

            try:
                result_key, metric, observations = future.result()

                metrics[result_key] = metric
                observations_by_key[result_key] = observations

                LOGGER.info(
                    "%s | %s | %s",
                    result_key,
                    metric["status"],
                    metric["observation_date"]
                )

            except Exception as exc:
                config = SERIES[key]

                LOGGER.error("%s failed: %s", key, exc)

                metrics[key] = build_metric(
                    key,
                    config,
                    [],
                    "FRED"
                )

                metrics[key]["error"] = str(exc)
                observations_by_key[key] = []

    return metrics, observations_by_key


# ============================================================
# BUILD FINAL PAYLOAD
# ============================================================

def build_payload():
    LOGGER.info("Starting Macro Engine v%s", VERSION)

    metrics, observations = fetch_all_series()

    # Add payroll change
    payroll_change = calculate_payroll_change(
        observations.get("nonfarm_payrolls", [])
    )

    if "nonfarm_payrolls" in metrics:
        metrics["nonfarm_payrolls"][
            "monthly_change_thousands"
        ] = payroll_change

    inflation = build_inflation_report(
        metrics,
        observations
    )

    indicator_reports = build_indicator_reports(
        metrics,
        inflation
    )

    overall = build_overall_decision(metrics)

    ok_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "OK"
    )

    stale_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "STALE"
    )

    unavailable_count = sum(
        1 for item in metrics.values()
        if item.get("status") == "UNAVAILABLE"
    )

    return {
        "schema_version": 1,
        "engine": "Crypto Macro Engine",
        "engine_version": VERSION,
        "fetched_at": iso_now(),
        "source": "Federal Reserve Economic Data (FRED)",
        "source_mode": (
            "FRED API"
            if FRED_API_KEY
            else "FRED CSV export"
        ),
        "summary": {
            "total_series": len(SERIES),
            "ok": ok_count,
            "stale": stale_count,
            "unavailable": unavailable_count,
            "data_quality": (
                "GOOD"
                if ok_count >= 18
                else "PARTIAL"
                if ok_count >= 8
                else "POOR"
            )
        },
        "metrics": metrics,
        "inflation": inflation,
        "reports": indicator_reports,
        "overall_macro_decision": overall,
        "limitations": [
            "DTWEXBGS is a broad USD index proxy, not ICE DXY.",
            "FRED observations may be delayed according to release schedules.",
            "Gold fixing data may be stale and is not a guaranteed live gold quote.",
            "Official economic calendar forecast and actual surprise are not integrated.",
            "BOJ policy and Japanese government bond yield curves are not integrated.",
            "Global liquidity composite is not integrated.",
            "Crypto ETF flows and crypto-specific on-chain data are not integrated.",
            "Macro decision is not a standalone trading signal.",
            "No personal portfolio or buy/sell position data is used."
        ],
        "not_integrated_yet": [
            "Economic calendar with forecast, actual and previous",
            "BOJ policy and JGB yields",
            "JPY carry-trade risk model",
            "Global central-bank liquidity composite",
            "Live gold market price cross-check",
            "Crypto ETF flows",
            "BTC market structure and technical confirmation",
            "Crypto-specific on-chain data"
        ]
    }


# ============================================================
# ATOMIC JSON WRITER
# ============================================================

def save_json(payload):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix="macro_data_",
        suffix=".tmp",
        dir=str(DATA_DIR)
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            file.write("\n")

        os.replace(temp_path, OUTPUT_FILE)

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        payload = build_payload()

        save_json(payload)

        summary = payload["summary"]

        LOGGER.info(
            "Macro Engine completed | OK=%s | STALE=%s | UNAVAILABLE=%s",
            summary["ok"],
            summary["stale"],
            summary["unavailable"]
        )

        LOGGER.info(
            "Overall decision: %s",
            payload["overall_macro_decision"]["DECISION"]
        )

        LOGGER.info("Output: %s", OUTPUT_FILE)

        # Fail the workflow if data collection is too poor.
        if summary["ok"] < 8:
            LOGGER.error(
                "Insufficient successful data series: %s",
                summary["ok"]
            )
            return 1

        return 0

    except Exception:
        LOGGER.exception("Macro Engine failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
