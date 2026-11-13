import requests
import datetime

# ১. ফিয়ার অ্যান্ড গ্রিড ডেটা
def get_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/").json()
        return int(res['data'][0]['value']), res['data'][0]['value_classification']
    except:
        return 50, "Neutral"

# ২. ডলার ইনডেক্স (DXY)
def get_dxy():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).json()
        return round(res['chart']['result'][0]['meta']['regularMarketPrice'], 2)
    except:
        return 104.50

# ৩. বিটকয়েনের দাম
def get_btc_price():
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd").json()
        return res['bitcoin']['usd']
    except:
        return 0

# ৪. সাইকেল স্টেজ নির্ধারণ (Cycle Stage)
def get_cycle_stage(fng, dxy):
    if fng < 30 and dxy < 105:
        return "ACCUMULATION (Buy Zone)", "text-green-500"
    elif fng > 70:
        return "MARKUP / DISTRIBUTION (Caution)", "text-red-500"
    else:
        return "NEUTRAL / GRINDING", "text-yellow-500"

# ৫. সিগন্যাল টেবিলের ডেটা তৈরি
def get_signals(fng, dxy, btc, etf_flow=50.5):
    # লজিক: fng (sentiment), dxy (macro), etf (liquidity)
    signals = []

    # ১. Price Structure
    signals.append({
        "name": "Price Structure", "match": "Holding above key support",
        "current": f"${btc:,}", "status": "NEUTRAL", "color": "text-yellow-500"
    })

    # ২. ETF Flows (Inflow হলে Buy, Outflow হলে Sell)
    etf_color = "text-green-500" if etf_flow > 0 else "text-red-500"
    etf_status = "BULLISH" if etf_flow > 0 else "BEARISH"
    signals.append({
        "name": "ETF Flows", "match": "Institutional Demand",
        "current": f"${etf_flow}M", "status": etf_status, "color": etf_color
    })

    # ৩. Market Sentiment (Fear & Greed)
    fng_color = "text-green-500" if fng < 30 else "text-red-500" if fng > 75 else "text-yellow-500"
    fng_status = "BUY" if fng < 30 else "SELL" if fng > 75 else "NEUTRAL"
    signals.append({
        "name": "Market Sentiment", "match": "Retail Mania / Fear",
        "current": f"{fng} ({fng})", "status": fng_status, "color": fng_color
    })

    # ৪. Macro Liquidity (DXY)
    dxy_color = "text-green-500" if dxy < 105 else "text-red-500"
    dxy_status = "BULLISH" if dxy < 105 else "BEARISH"
    signals.append({
        "name": "Dollar Index (DXY)", "match": "Macro Liquidity",
        "current": f"{dxy}", "status": dxy_status, "color": dxy_color
    })

    return signals

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_dxy()
btc_val = get_btc_price()
cycle_text, cycle_color = get_cycle_stage(fng_val, dxy_val)
signals_data = get_signals(fng_val, dxy_val, btc_val)
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

# HTML জেনারেশন
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Dada Style Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white font-sans p-4">
    <div class="max-w-5xl mx-auto">
        <h1 class="text-2xl font-bold mb-1 text-center text-blue-400">My Crypto Spot Dashboard</h1>
        <p class="text-center text-gray-400 mb-6 text-sm">Last Updated: {current_date} (UTC)</p>

        <!-- Top Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">BTC Price</p>
                <p class="text-xl font-bold text-orange-400">${btc_val:,}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">Fear & Greed</p>
                <p class="text-xl font-bold { 'text-green-500' if fng_val < 30 else 'text-red-500' if fng_val > 75 else 'text-yellow-500' }">{fng_val}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">DXY</p>
                <p class="text-xl font-bold { 'text-green-500' if dxy_val < 105 else 'text-red-500' }">{dxy_val}</p>
            </div>
            <div class="bg-gray-800 p-3 rounded-lg border border-gray-700 text-center">
                <p class="text-xs text-gray-400">ETF Flow</p>
                <p class="text-xl font-bold text-green-500">$50.5M</p>
            </div>
        </div>

        <!-- Cycle Stage Banner -->
        <div class="bg-gray-800 p-4 rounded-lg border border-gray-700 mb-6 text-center">
            <h2 class="text-sm font-semibold text-gray-400 mb-1">Current Cycle Stage</h2>
            <p class="text-2xl font-bold {cycle_color}">{cycle_text}</p>
        </div>

        <!-- Signal Table -->
        <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            <div class="p-4 bg-gray-700/50 border-b border-gray-600">
                <h2 class="text-lg font-bold text-gray-200 text-center">SIGNAL TABLE (CORE DASHBOARD)</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="text-xs text-gray-400 uppercase bg-gray-800 border-b border-gray-700">
                        <tr>
                            <th scope="col" class="px-3 py-3">Signal</th>
                            <th scope="col" class="px-3 py-3">Current Read</th>
                            <th scope="col" class="px-3 py-3 text-right">Status</th>
                        </tr>
                    </thead>
                    <tbody>
"""

# টেবিলের সারিগুলো তৈরি করা
for sig in signals_data:
    html_content += f"""
                        <tr class="border-b border-gray-700 hover:bg-gray-750">
                            <td class="px-3 py-3 font-medium text-white">{sig['name']}</td>
                            <td class="px-3 py-3">
                                <div class="font-semibold">{sig['current']}</div>
                                <div class="text-xs text-gray-500">{sig['match']}</div>
                            </td>
                            <td class="px-3 py-3 text-right font-bold {sig['color']}">{sig['status']}</td>
                        </tr>
"""

# HTML শেষ করা
html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="mt-6 text-center text-xs text-gray-500">
            Built for Long-Term Spot Trading. Keep patience.
        </div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully! index.html created.")
