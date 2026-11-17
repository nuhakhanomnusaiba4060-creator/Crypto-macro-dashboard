
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CRYPTO MACRO DASHBOARD - MACRO ENGINE
Version: 1.2

Output:
data/macro_data.json

Source:
Federal Reserve Economic Data (FRED)

v1.2 Improvements:
- Inflation trend analysis
- US net liquidity calculation
- 7D / 30D liquidity changes
- Yield curve analysis
- Multi-factor macro risk engine
- Better missing/stale data handling
- No fake or synthetic market data

IMPORTANT:
DTWEXBGS is a broad USD proxy, NOT ICE DXY.
Gold remains unavailable until a verified source is configured.
Macro decisions are not standalone crypto trading signals.
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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.2"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "macro_data.json"

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

TIMEOUT = 25
RETRIES = 2
MAX_WORKERS = 8

USER_AGENT = "CryptoMacroDashboard/1.2"

# Minimum observations required for reliable calculations.
MIN_MONTHLY_OBSERVATIONS = 13

# Liquidity calculation uses weekly Fed/TGA dates.
LIQUIDITY_LOOKBACK_DAYS = 45

# Data quality thresholds.
CRITICAL_SERIES = (
    "cpi",
    "core_cpi",
    "pce",
    "core_pce",
    "fed_funds_rate",
    "unemployment",
    "nonfarm_payrolls",
    "yield_2y",
    "yield_10y",
    "yield_30y",
    "yield_curve_10y_2y",
    "usd_broad_index",
    "vix",
    "sp500",
    "nasdaq",
    "fed_balance_sheet",
    "reverse_repo",
    "treasury_general_account"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

LOGGER = logging.getLogger("macro_engine")


# ============================================================
# FRED SERIES
# ============================================================

SERIES = {
    "fed_funds_rate": {
        "id": "DFF",
        "name": "Federal Funds Effective Rate",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "cpi": {
        "id": "CPIAUCSL",
        "name": "Consumer Price Index",
        "unit": "index",
        "freshness_days": 75,
        "frequency": "monthly"
    },
    "core_cpi": {
        "id": "CPILFESL",
        "name": "Core CPI",
        "unit": "index",
        "freshness_days": 75,
        "frequency": "monthly"
    },
    "pce": {
        "id": "PCEPI",
        "name": "PCE Price Index",
        "unit": "index",
        "freshness_days": 100,
        "frequency": "monthly"
    },
    "core_pce": {
        "id": "PCEPILFE",
        "name": "Core PCE Price Index",
        "unit": "index",
        "freshness_days": 100,
        "frequency": "monthly"
    },
    "unemployment": {
        "id": "UNRATE",
        "name": "Unemployment Rate",
        "unit": "%",
        "freshness_days": 75,
        "frequency": "monthly"
    },
    "nonfarm_payrolls": {
        "id": "PAYEMS",
        "name": "Total Nonfarm Payrolls",
        "unit": "thousands",
        "freshness_days": 75,
        "frequency": "monthly"
    },
    "yield_2y": {
        "id": "DGS2",
        "name": "US 2-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "yield_10y": {
        "id": "DGS10",
        "name": "US 10-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "yield_30y": {
        "id": "DGS30",
        "name": "US 30-Year Treasury Yield",
        "unit": "%",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "yield_curve_10y_2y": {
        "id": "T10Y2Y",
        "name": "10Y-2Y Treasury Spread",
        "unit": "percentage_points",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "usd_broad_index": {
        "id": "DTWEXBGS",
        "name": "Trade Weighted US Dollar Index",
        "unit": "index",
        "freshness_days": 10,
        "frequency": "daily"
    },
    "vix": {
        "id": "VIXCLS",
        "name": "CBOE Volatility Index",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "sp500": {
        "id": "SP500",
        "name": "S&P 500",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "nasdaq": {
        "id": "NASDAQCOM",
        "name": "NASDAQ Composite",
        "unit": "index",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "oil": {
        "id": "DCOILWTICO",
        "name": "WTI Crude Oil",
        "unit": "USD/barrel",
        "freshness_days": 10,
        "frequency": "daily"
    },
    "usd_jpy": {
        "id": "DEXJPUS",
        "name": "Japanese Yen per US Dollar",
        "unit": "JPY/USD",
        "freshness_days": 10,
        "frequency": "daily"
    },
    "fed_balance_sheet": {
        "id": "WALCL",
        "name": "Federal Reserve Total Assets",
        "unit": "millions USD",
        "freshness_days": 21,
        "frequency": "weekly"
    },
    "reverse_repo": {
        "id": "RRPONTSYD",
        "name": "Overnight Reverse Repurchase Agreements",
        "unit": "billions USD",
        "freshness_days": 7,
        "frequency": "daily"
    },
    "treasury_general_account": {
        "id": "WTREGEN",
        "name": "Treasury General Account",
        "unit": "millions USD",
        "freshness_days": 21,
        "frequency": "weekly"
    },
    "m2_money_supply": {
        "id": "M2SL",
        "name": "M2 Money Supply",
        "unit": "billions USD",
        "freshness_days": 100,
        "frequency": "monthly"
    }
}


DISABLED_SERIES = {
    "gold": {
        "name": "Gold Price",
        "unit": "USD/oz",
        "source": "FRED GOLDAMGBD228NLBM (disabled)",
        "reason": (
            "FRED endpoint returned HTTP 404. "
            "No verified replacement price source is configured."
        )
    }
}


# ============================================================
# TIME AND NUMBER HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def iso_now():
    return utc_now().isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def parse_date(value):
    try:
        return datetime.strptime(
            value, "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)
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


def round_value(value, digits=4):
    if value is None:
        return None

    return round(value, digits)


def percentage_change(current, previous):
    if current is None or previous is None:
        return None

    if previous == 0:
        return None

    return (
        (current - previous) / abs(previous)
    ) * 100


def observation_age_days(date_text):
    observed = parse_date(date_text)

    if observed is None:
        return None

    return max(
        0,
        (utc_now() - observed).total_seconds() / 86400
    )


def find_observation_at_or_before(observations, target_date):
    """
    Return latest observation at or before target_date.
    """

    result = None

    for item in observations:

        observed = parse_date(item["date"])

        if observed is None:
            continue

        if observed <= target_date:
            result = item
        else:
            break

    return result


def historical_percentage_change(observations, days):
    """
    Compare latest value with latest available observation
    at or before the requested calendar-day cutoff.
    """

    if not observations:
        return None

    current = observations[-1]

    current_date = parse_date(current["date"])

    if current_date is None:
        return None

    cutoff = current_date - timedelta(days=days)

    previous = find_observation_at_or_before(
        observations,
        cutoff
    )

    if previous is None:
        return None

    return round_value(
        percentage_change(
            current["value"],
            previous["value"]
        ),
        4
    )


def historical_value(observations, days):

    if not observations:
        return None

    current_date = parse_date(
        observations[-1]["date"]
    )

    if current_date is None:
        return None

    cutoff = current_date - timedelta(days=days)

    item = find_observation_at_or_before(
        observations,
        cutoff
    )

    if item is None:
        return None

    return item["value"]


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

            with urlopen(
                request,
                timeout=TIMEOUT
            ) as response:

                return response.read().decode(
                    "utf-8-sig"
                )

        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError
        ) as exc:

            last_error = str(exc)

            if attempt < RETRIES:
                time.sleep(
                    1.5 * (attempt + 1)
                )

    raise RuntimeError(
        last_error or "HTTP request failed"
    )


# ============================================================
# FRED DATA FETCH
# ============================================================

def fetch_fred_csv(series_id):

    params = urlencode({
        "id": series_id
    })

    url = f"{FRED_CSV_URL}?{params}"

    raw = http_get(url)

    reader = csv.DictReader(
        io.StringIO(raw)
    )

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
            or row.get("VALUE")
        )

        if not date_text:
            continue

        if parse_date(date_text) is None:
            continue

        value = safe_number(value_text)

        if value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    observations.sort(
        key=lambda item: item["date"]
    )

    if not observations:
        raise RuntimeError(
            f"No valid observations in CSV for {series_id}"
        )

    return observations


def fetch_fred_api(series_id):

    params = urlencode({
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc"
    })

    url = f"{FRED_API_URL}?{params}"

    payload = json.loads(
        http_get(url)
    )

    observations = []

    for item in payload.get("observations", []):

        date_text = item.get("date")

        value = safe_number(
            item.get("value")
        )

        if not date_text:
            continue

        if parse_date(date_text) is None:
            continue

        if value is None:
            continue

        observations.append({
            "date": date_text,
            "value": value
        })

    observations.sort(
        key=lambda item: item["date"]
    )

    if not observations:
        raise RuntimeError(
            f"No valid observations in API for {series_id}"
        )

    return observations


def fetch_series(series_id):

    if FRED_API_KEY:

        try:

            return (
                fetch_fred_api(series_id),
                "FRED_API"
            )

        except Exception as exc:

            LOGGER.warning(
                "%s API failed; trying CSV: %s",
                series_id,
                exc
            )

    return (
        fetch_fred_csv(series_id),
        "FRED_CSV_EXPORT"
    )


# ============================================================
# FRESHNESS AND METRIC PROCESSING
# ============================================================

def classify_freshness(observation_date, config):

    age_days = observation_age_days(
        observation_date
    )

    if age_days is None:
        return "UNAVAILABLE"

    limit = config.get(
        "freshness_days",
        7
    )

    if age_days > limit:
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
            "error": "No valid observations returned."
        }

    observations.sort(
        key=lambda item: item["date"]
    )

    current = observations[-1]

    previous = (
        observations[-2]
        if len(observations) >= 2
        else None
    )

    change = None
    change_percent = None

    if previous:

        change = (
            current["value"] - previous["value"]
        )

        change_percent = percentage_change(
            current["value"],
            previous["value"]
        )

    status = classify_freshness(
        current["date"],
        config
    )

    return {
        "key": key,
        "name": config["name"],
        "value": round_value(
            current["value"]
        ),
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
        "change_percent": round_value(
            change_percent
        ),
        "source": source,
        "fetched_at": fetched_at,
        "age_days": round_value(
            observation_age_days(
                current["date"]
            ),
            2
        ),
        "status": status,
        "error": (
            None
            if status == "OK"
            else "Latest observation is older than freshness limit."
        )
    }


# ============================================================
# INFLATION CALCULATIONS
# ============================================================

def historical_change(observations, periods):

    if len(observations) <= periods:
        return None

    current = observations[-1]["value"]

    previous = observations[
        -1 - periods
    ]["value"]

    return round_value(
        percentage_change(
            current,
            previous
        ),
        3
    )


def calculate_inflation_metrics(observations):

    if len(observations) < MIN_MONTHLY_OBSERVATIONS:

        return {
            "mom_percent": None,
            "three_month_percent": None,
            "yoy_percent": None,
            "status": "INSUFFICIENT_HISTORY"
        }

    mom = historical_change(
        observations,
        1
    )

    three_month = historical_change(
        observations,
        3
    )

    yoy = historical_change(
        observations,
        12
    )

    return {
        "mom_percent": mom,
        "three_month_percent": three_month,
        "yoy_percent": yoy,
        "status": (
            "OK"
            if mom is not None and yoy is not None
            else "INSUFFICIENT_HISTORY"
        )
    }


def build_inflation_report(metrics, observations_by_key):

    labels = {
        "cpi": "CPI",
        "core_cpi": "Core CPI",
        "pce": "PCE",
        "core_pce": "Core PCE"
    }

    result = {}

    for key, label in labels.items():

        metric = metrics.get(key, {})

        observations = observations_by_key.get(
            key,
            []
        )

        if metric.get("status") != "OK":

            result[key] = {
                "name": label,
                "mom_percent": None,
                "three_month_percent": None,
                "yoy_percent": None,
                "status": metric.get(
                    "status",
                    "UNAVAILABLE"
                )
            }

            continue

        calculated = calculate_inflation_metrics(
            observations
        )

        result[key] = {
            "name": label,
            **calculated
        }

    return result


# ============================================================
# PAYROLL CALCULATIONS
# ============================================================

def calculate_payroll_change(observations):

    if len(observations) < 2:
        return None

    return round_value(
        observations[-1]["value"]
        - observations[-2]["value"],
        1
    )


# ============================================================
# REPORT FORMAT
# ============================================================

def make_report(
    data,
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


def metric_value(metrics, key):

    item = metrics.get(key, {})

    if item.get("status") != "OK":
        return None

    return item.get("value")


def report_unavailable(label):

    return make_report(
        None,
        f"{label} data unavailable or stale.",
        "WAIT — INSUFFICIENT DATA",
        f"{label} data যাচাই না হওয়া পর্যন্ত সিদ্ধান্ত স্থগিত রাখুন।",
        "অসম্পূর্ণ বা পুরোনো ডেটা থেকে নির্ভরযোগ্য সিদ্ধান্ত নেওয়া যাবে না।"
    )


# ============================================================
# US NET LIQUIDITY ENGINE
# ============================================================


def build_liquidity_analysis(
    metrics,
    observations_by_key
):
    """
    US Net Liquidity proxy:

    WALCL (millions USD) / 1000
    - WTREGEN (millions USD) / 1000
    - RRPONTSYD (billions USD)

    Historical observations are aligned using as-of dates.
    RRP/TGA observation age is measured against the
    historical target date, NOT the current date.

    All output values are billions USD.
    """

    required = (
        "fed_balance_sheet",
        "treasury_general_account",
        "reverse_repo"
    )

    missing = [
        key for key in required
        if metrics.get(key, {}).get("status") != "OK"
    ]

    if missing:
        return {
            "status": "UNAVAILABLE",
            "missing_metrics": missing,
            "unit": "billions USD",
            "current": None,
            "change_7d": None,
            "change_30d": None,
            "formula": "WALCL - TGA - RRP",
            "error": "Required liquidity series unavailable or stale."
        }

    walcl = observations_by_key.get(
        "fed_balance_sheet", []
    )

    tga = observations_by_key.get(
        "treasury_general_account", []
    )

    rrp = observations_by_key.get(
        "reverse_repo", []
    )

    if not walcl or not tga or not rrp:
        return {
            "status": "UNAVAILABLE",
            "missing_metrics": [],
            "unit": "billions USD",
            "current": None,
            "change_7d": None,
            "change_30d": None,
            "formula": "WALCL - TGA - RRP",
            "error": "One or more historical liquidity series are empty."
        }

    # Sort and validate all observations.
    def clean_observations(items):
        cleaned = []

        for item in items:
            date_text = item.get("date")
            value = safe_number(item.get("value"))

            if parse_date(date_text) is None:
                continue

            if value is None:
                continue

            cleaned.append({
                "date": date_text,
                "value": value
            })

        cleaned.sort(key=lambda x: x["date"])

        return cleaned

    walcl = clean_observations(walcl)
    tga = clean_observations(tga)
    rrp = clean_observations(rrp)

    if not walcl or not tga or not rrp:
        return {
            "status": "UNAVAILABLE",
            "missing_metrics": [],
            "unit": "billions USD",
            "current": None,
            "change_7d": None,
            "change_30d": None,
            "formula": "WALCL - TGA - RRP",
            "error": "No valid historical liquidity observations."
        }

    # Maximum allowed age relative to each target date.
    MAX_TGA_AGE_DAYS = 10
    MAX_RRP_AGE_DAYS = 7

    combined = []

    # WALCL weekly observations are the calculation anchors.
    for walcl_item in walcl:

        target_date = parse_date(
            walcl_item["date"]
        )

        if target_date is None:
            continue

        # Find latest TGA observation on or before target.
        tga_item = find_observation_at_or_before(
            tga,
            target_date
        )

        if tga_item is None:
            continue

        tga_date = parse_date(tga_item["date"])

        if tga_date is None:
            continue

        tga_age = (
            target_date - tga_date
        ).total_seconds() / 86400

        if tga_age < 0 or tga_age > MAX_TGA_AGE_DAYS:
            continue

        # Find latest RRP observation on or before target.
        rrp_item = find_observation_at_or_before(
            rrp,
            target_date
        )

        if rrp_item is None:
            continue

        rrp_date = parse_date(rrp_item["date"])

        if rrp_date is None:
            continue

        # IMPORTANT:
        # Compare RRP date with historical target date,
        # not with today's date.
        rrp_age = (
            target_date - rrp_date
        ).total_seconds() / 86400

        if rrp_age < 0 or rrp_age > MAX_RRP_AGE_DAYS:
            continue

        walcl_billions = (
            walcl_item["value"] / 1000.0
        )

        tga_billions = (
            tga_item["value"] / 1000.0
        )

        rrp_billions = rrp_item["value"]

        net_liquidity = (
            walcl_billions
            - tga_billions
            - rrp_billions
        )

        if not math.isfinite(net_liquidity):
            continue

        combined.append({
            "date": walcl_item["date"],
            "value": net_liquidity,
            "walcl": walcl_billions,
            "tga": tga_billions,
            "rrp": rrp_billions,
            "tga_observation_date": tga_item["date"],
            "rrp_observation_date": rrp_item["date"]
        })

    combined.sort(
        key=lambda x: x["date"]
    )

    if not combined:
        return {
            "status": "UNAVAILABLE",
            "missing_metrics": [],
            "unit": "billions USD",
            "current": None,
            "change_7d": None,
            "change_30d": None,
            "formula": "WALCL - TGA - RRP",
            "error": (
                "No valid as-of aligned weekly observations. "
                "Check historical date coverage and source data."
            ),
            "source_observation_counts": {
                "walcl": len(walcl),
                "tga": len(tga),
                "rrp": len(rrp)
            }
        }

    latest = combined[-1]

    latest_date = parse_date(
        latest["date"]
    )

    if latest_date is None:
        raise ValueError(
            "Invalid latest liquidity observation date."
        )

    def find_combined_before(days):

        cutoff = latest_date - timedelta(
            days=days
        )

        candidates = [
            item for item in combined
            if parse_date(item["date"]) <= cutoff
        ]

        return candidates[-1] if candidates else None

    def calculate_absolute_change(days):

        previous = find_combined_before(days)

        if previous is None:
            return None

        return round_value(
            latest["value"] - previous["value"],
            3
        )

    change_7d = calculate_absolute_change(7)
    change_30d = calculate_absolute_change(30)

    if change_30d is None:
        trend = "INSUFFICIENT_HISTORY"
    elif change_30d > 0:
        trend = "EXPANDING"
    elif change_30d < 0:
        trend = "CONTRACTING"
    else:
        trend = "FLAT"

    return {
        "status": "OK",
        "unit": "billions USD",
        "formula": "WALCL - TGA - RRP",
        "observation_date": latest["date"],
        "current": round_value(
            latest["value"],
            3
        ),
        "components": {
            "fed_assets": round_value(
                latest["walcl"], 3
            ),
            "treasury_general_account": round_value(
                latest["tga"], 3
            ),
            "reverse_repo": round_value(
                latest["rrp"], 3
            ),
            "tga_observation_date": (
                latest["tga_observation_date"]
            ),
            "reverse_repo_observation_date": (
                latest["rrp_observation_date"]
            )
        },
        "change_7d": change_7d,
        "change_30d": change_30d,
        "trend": trend,
        "observations_available": len(combined),
        "alignment_method": "AS_OF_DATE",
        "max_tga_age_days": MAX_TGA_AGE_DAYS,
        "max_rrp_age_days": MAX_RRP_AGE_DAYS
    }


# ============================================================
# YIELD CURVE ENGINE
# ============================================================

def build_yield_curve_analysis(
    metrics,
    observations_by_key
):

    metric = metrics.get(
        "yield_curve_10y_2y",
        {}
    )

    observations = observations_by_key.get(
        "yield_curve_10y_2y",
        []
    )

    if metric.get("status") != "OK":

        return {
            "status": "UNAVAILABLE",
            "spread": None,
            "change_30d": None,
            "inverted": None,
            "trend": "UNKNOWN"
        }

    spread = metric.get("value")

    change_30d = historical_value(
        observations,
        30
    )

    change_30d = (
        round_value(
            spread - change_30d,
            4
        )
        if change_30d is not None
        else None
    )

    if spread < 0:
        inverted = True
    else:
        inverted = False

    if change_30d is None:
        trend = "INSUFFICIENT_HISTORY"

    elif change_30d > 0.05:
        trend = "STEEPENING"

    elif change_30d < -0.05:
        trend = "FLATTENING"

    else:
        trend = "STABLE"

    return {
        "status": "OK",
        "spread": spread,
        "unit": "percentage_points",
        "observation_date": metric.get(
            "observation_date"
        ),
        "change_30d": change_30d,
        "inverted": inverted,
        "trend": trend
    }


def build_yield_curve_report(
    metrics,
    observations_by_key
):

    curve = build_yield_curve_analysis(
        metrics,
        observations_by_key
    )

    if curve["status"] != "OK":

        return make_report(
            curve,
            "Yield curve data unavailable or stale.",
            "WAIT — INSUFFICIENT DATA",
            "Fresh 10Y-2Y spread data সংগ্রহ করুন।",
            "Yield curve ছাড়া recession risk assessment অসম্পূর্ণ।"
        )

    spread = curve["spread"]

    if spread < 0:

        decision = "WAIT"

        analysis = (
            "10Y-2Y Yield Curve inverted অবস্থায় রয়েছে।"
        )

        action = (
            "Yield curve inversion-কে labor market, credit "
            "conditions ও equity trend-এর সঙ্গে বিশ্লেষণ করুন।"
        )

    elif curve["trend"] == "STEEPENING":

        decision = "HOLD / SELECTIVE"

        analysis = (
            "10Y-2Y spread 30D-তে বেড়েছে; "
            "Yield Curve steepening হয়েছে।"
        )

        action = (
            "Steepening-এর কারণ যাচাই করুন—growth expectation "
            "নাকি long-term yield pressure।"
        )

    elif curve["trend"] == "FLATTENING":

        decision = "WAIT"

        analysis = (
            "10Y-2Y spread 30D-তে কমেছে; "
            "Yield Curve flattening হয়েছে।"
        )

        action = (
            "Growth expectation ও Treasury yield pressure "
            "পর্যবেক্ষণ করুন।"
        )

    else:

        decision = "HOLD / SELECTIVE"

        analysis = (
            "10Y-2Y spread positive এবং বড় 30D পরিবর্তন নেই।"
        )

        action = (
            "Yield curve-কে inflation, employment ও "
            "long-term yield-এর সঙ্গে পর্যবেক্ষণ করুন।"
        )

    return make_report(
        curve,
        analysis,
        decision,
        action,
        (
            "Yield curve inversion recession-এর ঝুঁকি নির্দেশ করতে পারে, "
            "কিন্তু recession নিশ্চিত করে না।"
        )
    )


# ============================================================
# INFLATION REPORT ENGINE
# ============================================================

def build_inflation_indicator_report(
    key,
    label,
    inflation,
    high_level,
    caution_level
):

    item = inflation.get(
        key,
        {}
    )

    if item.get("status") != "OK":

        return report_unavailable(label)

    yoy = item.get("yoy_percent")
    mom = item.get("mom_percent")
    three_month = item.get(
        "three_month_percent"
    )

    if yoy is None or mom is None:

        return make_report(
            item,
            f"{label} history incomplete.",
            "WAIT — INSUFFICIENT DATA",
            "Inflation trend সম্পূর্ণ হওয়ার আগে সিদ্ধান্ত নেবেন না।",
            "পর্যাপ্ত historical observation নেই।"
        )

    # Do not trigger REDUCE RISK from one monthly reading.
    # The decision describes inflation pressure, not direct
    # portfolio instructions.

    if yoy >= high_level and mom >= 0.30:

        decision = "REDUCE RISK"

        analysis = (
            f"{label} YoY উচ্চ এবং MoM-ও শক্তিশালী; "
            "inflation pressure বজায় রয়েছে।"
        )

        action = (
            "Inflation pressure বেশি—Fed policy ও Treasury yield "
            "এর সঙ্গে মিলিয়ে Crypto risk সতর্কভাবে পরিচালনা করুন।"
        )

    elif yoy >= high_level:

        decision = "WAIT"

        analysis = (
            f"{label} YoY উচ্চ, কিন্তু সর্বশেষ MoM reading "
            "তুলনামূলকভাবে কম।"
        )

        action = (
            "পরবর্তী inflation release দিয়ে trend নিশ্চিত করুন; "
            "একটি reading দেখে exposure পরিবর্তন করবেন না।"
        )

    elif yoy >= caution_level:

        decision = "WAIT"

        analysis = (
            f"{label} inflation এখনো সতর্কতার পর্যায়ে রয়েছে।"
        )

        action = (
            "MoM ও 3M trend-এর সঙ্গে Fed policy ও yields পর্যবেক্ষণ করুন।"
        )

    else:

        decision = "HOLD / SELECTIVE"

        analysis = (
            f"{label} YoY তুলনামূলকভাবে নিয়ন্ত্রিত।"
        )

        action = (
            "Inflation trend-কে Fed policy, yields ও BTC trend-এর "
            "সঙ্গে যাচাই করুন।"
        )

    return make_report(
        {
            "yoy_percent": yoy,
            "mom_percent": mom,
            "three_month_percent": three_month
        },
        analysis,
        decision,
        action,
        (
            "YoY, MoM ও 3M trend একসঙ্গে দেখতে হবে; "
            "একটি metric দিয়ে Fed policy নিশ্চিত করা যায় না।"
        )
    )


# ============================================================
# INDICATOR REPORT ENGINE
# ============================================================

def build_indicator_reports(
    metrics,
    inflation,
    observations_by_key
):

    reports = {}

    # --------------------------------------------------------
    # INFLATION
    # --------------------------------------------------------

    inflation_rules = [
        ("cpi", "CPI", 4.0, 3.0),
        ("core_cpi", "Core CPI", 4.0, 3.0),
        ("pce", "PCE", 3.0, 2.0),
        ("core_pce", "Core PCE", 3.0, 2.0)
    ]

    for key, label, high, caution in inflation_rules:

        reports[key] = build_inflation_indicator_report(
            key,
            label,
            inflation,
            high,
            caution
        )

    # --------------------------------------------------------
    # FED RATE
    # --------------------------------------------------------

    fed = metric_value(
        metrics,
        "fed_funds_rate"
    )

    if fed is None:

        reports["fed_rate"] = report_unavailable(
            "Fed Funds Rate"
        )

    else:

        reports["fed_rate"] = make_report(
            {
                "effective_rate_percent": fed,
                "observation_date": metrics[
                    "fed_funds_rate"
                ]["observation_date"]
            },
            "সর্বশেষ effective Fed funds rate পাওয়া গেছে।",
            "HOLD / SELECTIVE",
            (
                "Fed rate-কে inflation, employment, "
                "Treasury yield ও FOMC guidance-এর সঙ্গে বিশ্লেষণ করুন।"
            ),
            "Effective rate একা FOMC-এর পরবর্তী সিদ্ধান্ত জানায় না।"
        )

    # --------------------------------------------------------
    # LABOR MARKET
    # --------------------------------------------------------

    unemployment = metric_value(
        metrics,
        "unemployment"
    )

    payroll_change = metrics.get(
        "nonfarm_payrolls",
        {}
    ).get("monthly_change_thousands")

    if unemployment is None or payroll_change is None:

        reports["labor_market"] = report_unavailable(
            "Labor Market"
        )

    elif unemployment >= 5.0 or payroll_change < 0:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Employment deterioration-এর লক্ষণ রয়েছে।",
            "REDUCE RISK",
            (
                "Labor market দুর্বলতার সঙ্গে equity, credit "
                "conditions ও Fed policy যাচাই করুন।"
            ),
            "এক মাসের NFP revision ও labor force participation গুরুত্বপূর্ণ।"
        )

    elif unemployment >= 4.5:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Unemployment elevated range-এ রয়েছে।",
            "WAIT",
            "পরবর্তী NFP ও unemployment release পর্যবেক্ষণ করুন।",
            "Unemployment একা recession নিশ্চিত করে না।"
        )

    else:

        reports["labor_market"] = make_report(
            {
                "unemployment_percent": unemployment,
                "nfp_monthly_change_thousands": payroll_change
            },
            "Labor market তুলনামূলকভাবে স্থিতিশীল।",
            "HOLD / SELECTIVE",
            "Employment trend ও wage inflation একসঙ্গে পর্যবেক্ষণ করুন।",
            "শক্তিশালী employment inflation pressure বজায় রাখতে পারে।"
        )

    # --------------------------------------------------------
    # BOND YIELDS
    # --------------------------------------------------------

    y2 = metric_value(metrics, "yield_2y")
    y10 = metric_value(metrics, "yield_10y")
    y30 = metric_value(metrics, "yield_30y")

    y10_metric = metrics.get(
        "yield_10y",
        {}
    )

    y10_change = y10_metric.get(
        "change"
    )

    if (
        y2 is None
        or y10 is None
        or y30 is None
        or y10_change is None
    ):

        reports["bond_yields"] = report_unavailable(
            "Treasury Yield"
        )

    else:

        if y10_change >= 0.05:

            decision = "REDUCE RISK"

            analysis = (
                "10Y Treasury yield সর্বশেষ observation-এ "
                "অর্থপূর্ণভাবে বেড়েছে।"
            )

            action = (
                "Yield pressure বাড়ছে—Inflation, Treasury supply "
                "ও BTC trend যাচাই করুন।"
            )

        elif y10_change <= -0.05:

            decision = "HOLD / SELECTIVE"

            analysis = (
                "10Y Treasury yield সর্বশেষ observation-এ কমেছে।"
            )

            action = (
                "Yield decline-এর কারণ growth concern নাকি "
                "inflation cooling তা যাচাই করুন।"
            )

        else:

            decision = "WAIT"

            analysis = (
                "10Y yield-এ বড় দৈনিক পরিবর্তন নেই।"
            )

            action = "Treasury yield trend পর্যবেক্ষণ করুন।"

        reports["bond_yields"] = make_report(
            {
                "2y": y2,
                "10y": y10,
                "30y": y30,
                "10y_daily_change_pp": y10_change
            },
            analysis,
            decision,
            action,
            (
                "এক দিনের yield change দীর্ঘমেয়াদি trend "
                "নিশ্চিত করে না।"
            )
        )

    # --------------------------------------------------------
    # YIELD CURVE
    # --------------------------------------------------------

    reports["yield_curve"] = build_yield_curve_report(
        metrics,
        observations_by_key
    )

    # --------------------------------------------------------
    # BROAD USD INDEX
    # --------------------------------------------------------

    usd = metrics.get(
        "usd_broad_index",
        {}
    )

    usd_change = usd.get(
        "change_percent"
    )

    if usd.get("status") != "OK" or usd_change is None:

        reports["usd_index"] = report_unavailable(
            "Broad USD Index"
        )

    elif usd_change >= 0.30:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index সর্বশেষ observation-এ উল্লেখযোগ্যভাবে বেড়েছে।",
            "REDUCE RISK",
            "Dollar strength বাড়ছে—Crypto risk exposure সতর্কভাবে পরিচালনা করুন।",
            "এটি ICE DXY নয়; broad trade-weighted USD index।"
        )

    elif usd_change <= -0.30:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index সর্বশেষ observation-এ উল্লেখযোগ্যভাবে কমেছে।",
            "HOLD / SELECTIVE",
            "USD দুর্বলতা BTC ও Altcoin trend-এর সঙ্গে যাচাই করুন।",
            "USD দুর্বল হলেই Crypto bullish হয় না।"
        )

    else:

        reports["usd_index"] = make_report(
            {"daily_change_percent": usd_change},
            "Broad USD index-এ বড় দৈনিক পরিবর্তন নেই।",
            "WAIT",
            "USD trend পর্যবেক্ষণ করুন।",
            "এটি ICE DXY নয়; broad trade-weighted USD index।"
        )

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    vix = metric_value(
        metrics,
        "vix"
    )

    if vix is None:

        reports["vix"] = report_unavailable(
            "VIX"
        )

    elif vix >= 30:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX অত্যন্ত উচ্চ; Equity volatility risk elevated.",
            "REDUCE RISK",
            "Market volatility elevated—নতুন ঝুঁকিপূর্ণ BUY সীমিত রাখুন।",
            "VIX equity volatility মাপে; Crypto volatility সরাসরি মাপে না।"
        )

    elif vix >= 25:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX উচ্চ range-এ রয়েছে।",
            "WAIT",
            "নতুন BUY-তে সতর্ক থাকুন এবং BTC volatility পর্যবেক্ষণ করুন।",
            "VIX একা Crypto market direction নির্ধারণ করে না।"
        )

    elif vix >= 18:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX elevated range-এ রয়েছে।",
            "WAIT",
            "Market volatility ও equity trend পর্যবেক্ষণ করুন।",
            "VIX একা Crypto market direction নির্ধারণ করে না।"
        )

    else:

        reports["vix"] = make_report(
            {"value": vix},
            "VIX তুলনামূলক কম।",
            "HOLD / SELECTIVE",
            "কম VIX-কে একমাত্র BUY signal হিসেবে ব্যবহার করবেন না।",
            "কম VIX থাকা সত্ত্বেও Crypto-specific risk থাকতে পারে।"
        )

    # --------------------------------------------------------
    # EQUITY MARKET
    # --------------------------------------------------------

    sp = metric_value(
        metrics,
        "sp500"
    )

    nq = metric_value(
        metrics,
        "nasdaq"
    )

    sp_change = metrics.get(
        "sp500",
        {}
    ).get("change_percent")

    nq_change = metrics.get(
        "nasdaq",
        {}
    ).get("change_percent")

    if (
        sp is None
        or nq is None
        or sp_change is None
        or nq_change is None
    ):

        reports["equity_market"] = report_unavailable(
            "Equity Market"
        )

    else:

        both_negative = (
            sp_change <= -1.0
            and nq_change <= -1.0
        )

        reports["equity_market"] = make_report(
            {
                "sp500": sp,
                "nasdaq": nq,
                "sp500_daily_change_percent": sp_change,
                "nasdaq_daily_change_percent": nq_change
            },
            (
                "S&P 500 ও Nasdaq উভয়ই সর্বশেষ session-এ "
                "দুর্বল হয়েছে।"
                if both_negative
                else "S&P 500 ও Nasdaq-এর সর্বশেষ observations পাওয়া গেছে।"
            ),
            (
                "WAIT"
                if both_negative
                else "HOLD / SELECTIVE"
            ),
            (
                "Equity weakness-এর সময়ে নতুন ঝুঁকিপূর্ণ BUY সীমিত রাখুন।"
                if both_negative
                else "Equity trend-কে VIX, yields ও BTC trend-এর সঙ্গে মিলিয়ে দেখুন।"
            ),
            "একটি session-এর পরিবর্তন দীর্ঘমেয়াদি equity trend নয়।"
        )

    # --------------------------------------------------------
    # COMMODITIES
    # --------------------------------------------------------

    oil = metric_value(
        metrics,
        "oil"
    )

    gold = metrics.get(
        "gold",
        {}
    )

    reports["commodities"] = make_report(
        {
            "wti_oil_usd_per_barrel": oil,
            "gold_usd_per_oz": None,
            "gold_status": gold.get(
                "status",
                "UNAVAILABLE"
            ),
            "gold_note": gold.get("error")
        },
        (
            "WTI oil data পাওয়া গেছে; Gold source unavailable."
            if oil is not None
            else "Commodity data incomplete; Gold source unavailable."
        ),
        (
            "HOLD / SELECTIVE"
            if oil is not None
            else "WAIT — INSUFFICIENT DATA"
        ),
        (
            "Oil-এর inflation impact পর্যবেক্ষণ করুন; "
            "Gold-এর জন্য verified source প্রয়োজন।"
        ),
        "Gold-এর কোনো কৃত্রিম বা পুরোনো মান ব্যবহার করা হচ্ছে না।"
    )

    # --------------------------------------------------------
    # YEN
    # --------------------------------------------------------

    yen = metric_value(
        metrics,
        "usd_jpy"
    )

    if yen is None:

        reports["yen"] = report_unavailable(
            "USD/JPY"
        )

    else:

        reports["yen"] = make_report(
            {
                "jpy_per_usd": yen,
                "observation_date": metrics[
                    "usd_jpy"
                ]["observation_date"]
            },
            "USD/JPY latest observation পাওয়া গেছে।",
            "WAIT",
            "Yen movement-এর সঙ্গে BOJ policy ও Japanese bond yield পর্যবেক্ষণ করুন।",
            "JGB yield curve ছাড়া carry-trade unwind নিশ্চিত করা যায় না।"
        )

    # --------------------------------------------------------
    # US LIQUIDITY
    # --------------------------------------------------------

    reports["liquidity"] = build_liquidity_report(
        metrics,
        observations_by_key
    )

    return reports


# ============================================================
# MULTI-FACTOR MACRO DECISION ENGINE
# ============================================================

def build_overall_decision(
    metrics,
    inflation,
    liquidity,
    yield_curve
):
    """
    Risk points are grouped to avoid double counting.

    1. Inflation pressure
    2. USD pressure
    3. Volatility
    4. Treasury yield pressure
    5. Equity weakness
    6. Labor deterioration
    7. Liquidity contraction
    8. Yield curve inversion

    This is a transparent rule-based macro assessment.
    It is not a statistically calibrated trading model.
    """

    risk_flags = []
    supportive_flags = []
    unavailable = []

    # --------------------------------------------------------
    # REQUIRED CORE DATA
    # --------------------------------------------------------

    required = (
        "usd_broad_index",
        "vix",
        "yield_10y",
        "cpi",
        "core_pce",
        "unemployment",
        "sp500",
        "nasdaq"
    )

    for key in required:

        if metrics.get(
            key,
            {}
        ).get("status") != "OK":

            unavailable.append(key)

    if unavailable:

        return {
            "DATA": {
                "required_metrics": list(required),
                "missing_metrics": unavailable,
                "risk_flags": [],
                "supportive_flags": []
            },
            "ANALYSIS": (
                "প্রয়োজনীয় Core Macro data incomplete বা stale."
            ),
            "DECISION": "WAIT — INSUFFICIENT DATA",
            "ACTION": (
                "Core Macro data সম্পূর্ণ না হওয়া পর্যন্ত "
                "Risk-on/Risk-off সিদ্ধান্ত স্থগিত রাখুন।"
            ),
            "RISK": (
                "অসম্পূর্ণ data থেকে ভুল market assessment হতে পারে।"
            )
        }

    risk_score = 0
    support_score = 0

    # --------------------------------------------------------
    # 1. INFLATION PRESSURE
    # --------------------------------------------------------

    cpi_yoy = inflation.get(
        "cpi",
        {}
    ).get("yoy_percent")

    core_pce_yoy = inflation.get(
        "core_pce",
        {}
    ).get("yoy_percent")

    cpi_mom = inflation.get(
        "cpi",
        {}
    ).get("mom_percent")

    core_pce_mom = inflation.get(
        "core_pce",
        {}
    ).get("mom_percent")

    inflation_valid = all(
        value is not None
        for value in (
            cpi_yoy,
            core_pce_yoy,
            cpi_mom,
            core_pce_mom
        )
    )

    if not inflation_valid:

        unavailable.append(
            "inflation_history"
        )

    else:

        inflation_pressure = (
            cpi_yoy >= 4.0
            and core_pce_yoy >= 3.0
            and cpi_mom >= 0.30
            and core_pce_mom >= 0.30
        )

        inflation_cooling = (
            cpi_yoy < 3.0
            and core_pce_yoy < 2.5
            and cpi_mom < 0.20
            and core_pce_mom < 0.20
        )

        if inflation_pressure:

            risk_score += 1

            risk_flags.append(
                "Broad inflation pressure: CPI and Core PCE elevated"
            )

        elif inflation_cooling:

            support_score += 1

            supportive_flags.append(
                "CPI and Core PCE show comparatively lower pressure"
            )

    # --------------------------------------------------------
    # 2. BROAD USD
    # --------------------------------------------------------

    usd_change = metrics[
        "usd_broad_index"
    ].get("change_percent")

    if usd_change is None:

        unavailable.append(
            "usd_change"
        )

    elif usd_change >= 0.30:

        risk_score += 1

        risk_flags.append(
            "Broad USD daily increase >= +0.30%"
        )

    elif usd_change <= -0.30:

        support_score += 1

        supportive_flags.append(
            "Broad USD daily decrease <= -0.30%"
        )

    # --------------------------------------------------------
    # 3. VIX
    # --------------------------------------------------------

    vix = metric_value(
        metrics,
        "vix"
    )

    if vix is None:

        unavailable.append("vix")

    elif vix >= 30:

        risk_score += 2

        risk_flags.append(
            "VIX >= 30: high volatility stress"
        )

    elif vix >= 25:

        risk_score += 1

        risk_flags.append(
            "VIX >= 25: elevated volatility"
        )

    elif vix < 18:

        support_score += 1

        supportive_flags.append(
            "VIX < 18"
        )

    # --------------------------------------------------------
    # 4. TREASURY YIELD
    # --------------------------------------------------------

    y10_change = metrics[
        "yield_10y"
    ].get("change")

    if y10_change is None:

        unavailable.append(
            "10y_yield_change"
        )

    elif y10_change >= 0.05:

        risk_score += 1

        risk_flags.append(
            "10Y yield daily increase >= +0.05 pp"
        )

    elif y10_change <= -0.05:

        support_score += 1

        supportive_flags.append(
            "10Y yield daily decrease <= -0.05 pp"
        )

    # --------------------------------------------------------
    # 5. EQUITY MARKET
    # --------------------------------------------------------

    sp_change = metrics[
        "sp500"
    ].get("change_percent")

    nq_change = metrics[
        "nasdaq"
    ].get("change_percent")

    if sp_change is None or nq_change is None:

        unavailable.append(
            "equity_change"
        )

    elif sp_change <= -1.5 and nq_change <= -1.5:

        risk_score += 1

        risk_flags.append(
            "S&P 500 and Nasdaq both down >= 1.5%"
        )

    elif sp_change > 0 and nq_change > 0:

        support_score += 1

        supportive_flags.append(
            "S&P 500 and Nasdaq both positive"
        )

    # --------------------------------------------------------
    # 6. LABOR MARKET
    # --------------------------------------------------------

    unemployment = metric_value(
        metrics,
        "unemployment"
    )

    payroll_change = metrics.get(
        "nonfarm_payrolls",
        {}
    ).get("monthly_change_thousands")

    if unemployment is None or payroll_change is None:

        unavailable.append(
            "labor_market"
        )

    elif unemployment >= 5.0 or payroll_change < 0:

        risk_score += 1

        risk_flags.append(
            "Labor market deterioration"
        )

    elif unemployment < 4.5 and payroll_change > 0:

        support_score += 1

        supportive_flags.append(
            "Labor market comparatively stable"
        )

    # --------------------------------------------------------
    # 7. NET LIQUIDITY
    # --------------------------------------------------------

    liquidity_change = liquidity.get(
        "change_30d"
    )

    if liquidity.get("status") != "OK":

        unavailable.append(
            "net_liquidity"
        )

    elif liquidity_change is None:

        unavailable.append(
            "net_liquidity_30d"
        )

    elif liquidity_change < -50:

        risk_score += 1

        risk_flags.append(
            "US Net Liquidity 30D contraction exceeds $50B"
        )

    elif liquidity_change > 50:

        support_score += 1

        supportive_flags.append(
            "US Net Liquidity 30D expansion exceeds $50B"
        )

    # --------------------------------------------------------
    # 8. YIELD CURVE
    # --------------------------------------------------------

    if yield_curve.get("status") != "OK":

        unavailable.append(
            "yield_curve"
        )

    elif yield_curve.get("inverted"):

        risk_score += 1

        risk_flags.append(
            "10Y-2Y yield curve inverted"
        )

    # --------------------------------------------------------
    # DECISION CONFIDENCE
    # --------------------------------------------------------

    if unavailable:

        decision = "WAIT — INSUFFICIENT DATA"

        analysis = (
            "কিছু প্রয়োজনীয় Macro calculation অনুপস্থিত; "
            "সম্পূর্ণ Risk Assessment সম্ভব নয়।"
        )

        action = (
            "Missing data ঠিক না হওয়া পর্যন্ত নতুন বড় "
            "Risk Exposure নেওয়া স্থগিত রাখুন।"
        )

        risk = (
            "Risk Score অসম্পূর্ণ ডেটার কারণে পূর্ণাঙ্গ নয়।"
        )

    elif risk_score >= 3:

        decision = "REDUCE RISK"

        analysis = (
            "একাধিক স্বাধীন Macro risk category একই সময়ে "
            "চাপ তৈরি করছে।"
        )

        action = (
            "Macro risk elevated—ঝুঁকিপূর্ণ Altcoin exposure "
            "কম রাখুন এবং নতুন BUY সীমিত করুন।"
        )

        risk = (
            "BTC trend, ETF flows, crypto liquidity ও "
            "on-chain data ছাড়া এটি চূড়ান্ত Crypto Sell signal নয়।"
        )

    elif risk_score >= 1:

        decision = "WAIT"

        analysis = (
            "Macro environment-এ risk pressure রয়েছে, "
            "কিন্তু পূর্ণ Risk-Off confirmation নেই।"
        )

        action = (
            "নতুন বড় Risk Exposure নেবেন না; BTC trend "
            "ও পরবর্তী Macro release পর্যবেক্ষণ করুন।"
        )

        risk = (
            "কিছু supportive indicator থাকলেও risk pressure "
            "সম্পূর্ণ দূর হয়নি।"
        )

    elif support_score >= 3:

        decision = "HOLD / SELECTIVE"

        analysis = (
            "একাধিক Macro category তুলনামূলক supportive "
            "এবং উল্লেখযোগ্য risk flag নেই।"
        )

        action = (
            "Macro environment তুলনামূলক সহায়ক; "
            "তবু BTC trend ও market breadth ছাড়া aggressive BUY নয়।"
        )

        risk = (
            "Macro support নিশ্চিত Crypto Bull Market signal নয়।"
        )

    else:

        decision = "WAIT"

        analysis = (
            "Macro signal এখনো যথেষ্ট শক্তিশালী নয়।"
        )

        action = (
            "নতুন বড় Risk Exposure নেওয়ার আগে "
            "Macro ও BTC trend-এর confirmation অপেক্ষা করুন।"
        )

        risk = (
            "স্বল্প Risk Score মানেই market risk অনুপস্থিত নয়।"
        )

    return {
        "DATA": {
            "risk_score": risk_score,
            "support_score": support_score,
            "risk_flags": risk_flags,
            "supportive_flags": supportive_flags,
            "unavailable_calculations": unavailable,
            "risk_categories": 8,
            "model_type": "RULE_BASED_MULTI_FACTOR",
            "calibrated_probability": None
        },
        "ANALYSIS": analysis,
        "DECISION": decision,
        "ACTION": action,
        "RISK": risk
    }


# ============================================================
# FETCH ALL SERIES
# ============================================================

def fetch_worker(key, config):

    observations, source = fetch_series(
        config["id"]
    )

    metric = build_metric(
        key,
        config,
        observations,
        source
    )

    return key, metric, observations


def fetch_all_series():

    metrics = {}
    observations_by_key = {}

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                fetch_worker,
                key,
                config
            ): key

            for key, config in SERIES.items()
        }

        for future in as_completed(futures):

            key = futures[future]

            try:

                result_key, metric, observations = (
                    future.result()
                )

                metrics[result_key] = metric

                observations_by_key[result_key] = (
                    observations
                )

                LOGGER.info(
                    "%s | %s | %s",
                    result_key,
                    metric["status"],
                    metric["observation_date"]
                )

            except Exception as exc:

                config = SERIES[key]

                LOGGER.error(
                    "%s fetch failed: %s",
                    key,
                    exc
                )

                metrics[key] = build_metric(
                    key,
                    config,
                    [],
                    "FRED"
                )

                metrics[key]["error"] = str(
                    exc
                )[:500]

                observations_by_key[key] = []

    # Gold is disabled.
    # No unverified replacement is used.

    gold_config = DISABLED_SERIES["gold"]

    metrics["gold"] = {
        "key": "gold",
        "name": gold_config["name"],
        "value": None,
        "unit": gold_config["unit"],
        "observation_date": None,
        "previous_value": None,
        "previous_date": None,
        "change": None,
        "change_percent": None,
        "source": gold_config["source"],
        "fetched_at": iso_now(),
        "status": "UNAVAILABLE",
        "error": gold_config["reason"]
    }

    observations_by_key["gold"] = []

    return metrics, observations_by_key


# ============================================================
# DATA QUALITY
# ============================================================

def build_data_quality(metrics):

    critical_missing = []

    for key in CRITICAL_SERIES:

        if metrics.get(
            key,
            {}
        ).get("status") != "OK":

            critical_missing.append(key)

    optional_unavailable = [
        key
        for key, item in metrics.items()
        if item.get("status") == "UNAVAILABLE"
        and key not in CRITICAL_SERIES
    ]

    stale = [
        key
        for key, item in metrics.items()
        if item.get("status") == "STALE"
    ]

    if critical_missing:

        quality = (
            "PARTIAL"
            if len(critical_missing) <= 5
            else "POOR"
        )

    elif stale:

        quality = "PARTIAL"

    elif optional_unavailable:

        quality = "GOOD_WITH_OPTIONAL_GAPS"

    else:

        quality = "GOOD"

    return {
        "data_quality": quality,
        "critical_missing": critical_missing,
        "optional_unavailable": optional_unavailable,
        "stale_metrics": stale,
        "critical_series_count": len(CRITICAL_SERIES),
        "critical_series_available": (
            len(CRITICAL_SERIES)
            - len(critical_missing)
        )
    }


# ============================================================
# BUILD FINAL PAYLOAD
# ============================================================

def build_payload():

    LOGGER.info(
        "Starting Macro Engine v%s",
        VERSION
    )

    metrics, observations = fetch_all_series()

    payroll_change = calculate_payroll_change(
        observations.get(
            "nonfarm_payrolls",
            []
        )
    )

    if "nonfarm_payrolls" in metrics:

        metrics["nonfarm_payrolls"][
            "monthly_change_thousands"
        ] = payroll_change

    inflation = build_inflation_report(
        metrics,
        observations
    )

    liquidity = build_liquidity_analysis(
        metrics,
        observations
    )

    yield_curve = build_yield_curve_analysis(
        metrics,
        observations
    )

    reports = build_indicator_reports(
        metrics,
        inflation,
        observations
    )

    overall = build_overall_decision(
        metrics,
        inflation,
        liquidity,
        yield_curve
    )

    ok_count = sum(
        1
        for item in metrics.values()
        if item.get("status") == "OK"
    )

    stale_count = sum(
        1
        for item in metrics.values()
        if item.get("status") == "STALE"
    )

    unavailable_count = sum(
        1
        for item in metrics.values()
        if item.get("status") == "UNAVAILABLE"
    )

    data_quality = build_data_quality(
        metrics
    )

    return {
        "schema_version": 2,
        "engine": "Crypto Macro Engine",
        "engine_version": VERSION,
        "fetched_at": iso_now(),
        "source": "Federal Reserve Economic Data (FRED)",

        "source_mode": (
            "FRED API with CSV fallback"
            if FRED_API_KEY
            else "FRED CSV export"
        ),

        "summary": {
            "total_series": len(metrics),
            "ok": ok_count,
            "stale": stale_count,
            "unavailable": unavailable_count,
            **data_quality
        },

        "metrics": metrics,

        "inflation": inflation,

        "liquidity": liquidity,

        "yield_curve": yield_curve,

        "reports": reports,

        "overall_macro_decision": overall,

        "limitations": [
            "DTWEXBGS is a broad trade-weighted USD proxy, not ICE DXY.",
            "FRED observations are released with delays.",
            "Freshness limits are series-specific.",
            "Gold is unavailable because the previous FRED endpoint returned HTTP 404.",
            "No unverified Gold replacement is used.",
            "US Net Liquidity is a proxy calculated as WALCL - TGA - RRP.",
            "Net Liquidity is not a complete Global Liquidity Composite.",
            "Economic calendar forecast/actual/surprise is not integrated.",
            "BOJ policy and Japanese government bond yield curves are not integrated.",
            "JPY carry-trade risk model is not integrated.",
            "Crypto ETF flows are not integrated.",
            "BTC market structure and technical confirmation are not integrated.",
            "Crypto-specific on-chain data are not integrated.",
            "Rule-based Macro Risk Score is not a calibrated probability.",
            "Macro decision is not a standalone crypto trading signal."
        ],

        "not_integrated_yet": [
            "Economic calendar with verified forecast and actual",
            "BOJ policy and JGB yields",
            "JPY carry-trade risk model",
            "Global central-bank liquidity composite",
            "Verified live Gold market price source",
            "Crypto ETF flows",
            "BTC market structure and technical confirmation",
            "Crypto-specific on-chain data",
            "Macro event surprise analysis"
        ]
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_payload(payload):

    if not isinstance(payload, dict):
        raise ValueError(
            "Payload must be a dictionary."
        )

    if payload.get("engine_version") != VERSION:
        raise ValueError(
            "Incorrect engine version."
        )

    required_top_level = (
        "summary",
        "metrics",
        "inflation",
        "liquidity",
        "yield_curve",
        "reports",
        "overall_macro_decision"
    )

    for key in required_top_level:

        if key not in payload:
            raise ValueError(
                f"Missing required payload field: {key}"
            )

    summary = payload["summary"]

    if (
        summary["ok"]
        + summary["stale"]
        + summary["unavailable"]
        != summary["total_series"]
    ):

        raise ValueError(
            "Series summary counts do not match."
        )

    for key, metric in payload["metrics"].items():

        if metric.get("status") not in (
            "OK",
            "STALE",
            "UNAVAILABLE"
        ):

            raise ValueError(
                f"Invalid status for {key}"
            )

        value = metric.get("value")

        if value is not None:

            if not math.isfinite(float(value)):
                raise ValueError(
                    f"Non-finite metric value: {key}"
                )

    for key, report in payload["reports"].items():

        for field in (
            "DATA",
            "ANALYSIS",
            "DECISION",
            "ACTION",
            "RISK"
        ):

            if field not in report:
                raise ValueError(
                    f"Missing {field} in report {key}"
                )

    overall = payload[
        "overall_macro_decision"
    ]

    for field in (
        "DATA",
        "ANALYSIS",
        "DECISION",
        "ACTION",
        "RISK"
    ):

        if field not in overall:
            raise ValueError(
                f"Missing overall decision field: {field}"
            )

    json.dumps(
        payload,
        allow_nan=False
    )

    return True


# ============================================================
# ATOMIC JSON WRITER
# ============================================================

def save_json(payload):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    fd, temp_path = tempfile.mkstemp(
        prefix="macro_data_",
        suffix=".tmp",
        dir=str(DATA_DIR)
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                payload,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )

            file.write("\n")

        os.replace(
            temp_path,
            OUTPUT_FILE
        )

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

        validate_payload(
            payload
        )

        save_json(
            payload
        )

        summary = payload["summary"]

        LOGGER.info(
            "Macro Engine completed | OK=%s | STALE=%s | UNAVAILABLE=%s",
            summary["ok"],
            summary["stale"],
            summary["unavailable"]
        )

        LOGGER.info(
            "Data quality: %s",
            summary["data_quality"]
        )

        LOGGER.info(
            "Critical series available: %s/%s",
            summary["critical_series_available"],
            summary["critical_series_count"]
        )

        LOGGER.info(
            "US Net Liquidity status: %s",
            payload["liquidity"]["status"]
        )

        LOGGER.info(
            "Yield Curve status: %s",
            payload["yield_curve"]["status"]
        )

        LOGGER.info(
            "Overall decision: %s",
            payload["overall_macro_decision"]["DECISION"]
        )

        LOGGER.info(
            "Output: %s",
            OUTPUT_FILE
        )

        if summary["critical_missing"]:

            LOGGER.warning(
                "Critical missing series: %s",
                ", ".join(
                    summary["critical_missing"]
                )
            )

        # Preserve output for inspection, but fail workflow
        # when core macro data are incomplete.

        if summary["critical_missing"]:

            LOGGER.error(
                "Critical macro data incomplete."
            )

            return 1

        return 0

    except Exception:

        LOGGER.exception(
            "Macro Engine failed"
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
