import requests
import datetime

# ১. ফিয়ার অ্যান্ড গ্রিড ডেটা আনা
def get_fear_and_greed():
    try:
        response = requests.get("https://api.alternative.me/fng/")
        data = response.json()
        value = int(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        return value, classification
    except:
        return "N/A", "Error"

# ২. ডলার ইনডেক্স (DXY) লাইভ ডেটা আনা
def get_dxy():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        price = data['chart']['result'][0]['meta']['regularMarketPrice']
        return round(price, 2)
    except:
        return "N/A"

# ৩. বিটকয়েনের লাইভ দাম আনা
def get_btc_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url)
        data = response.json()
        return data['bitcoin']['usd']
    except:
        return "N/A"

# ৪. বিটকয়েন ETF ফান্ড ফ্লো (ডেমো/সিমুলেটেড ডেটা)
# নোট: ফ্রি ও নির্ভরযোগ্য API না থাকায় এখানে একটি সিমুলেটেড ডেটা দেওয়া হলো। 
# পরবর্তীতে আপনি CoinGlass বা Farside থেকে আসল ডেটা যুক্ত করতে পারবেন।
def get_etf_flow():
    # ধরুন, আজ ৫০ মিলিয়ন ডলার ইনফ্লো হয়েছে (পজিটিভ মানে ইনফ্লো)
    return 50.5 

# ৫. সিদ্ধান্ত নির্ধারণের লজিক (Action Plan)
def get_action_plan(fng_value, dxy_value, etf_flow):
    if fng_value == "N/A" or dxy_value == "N/A":
        return "ERROR: ডেটা লোড হয়নি।", "text-gray-500"
        
    # অত্যন্ত বুলিশ (চরম ভয় + ডলার দুর্বল + ETF ইনফ্লো)
    if fng_value < 30 and dxy_value < 105 and etf_flow > 0:
        return "STRONG BUY: চরম ভয়, ডলার দুর্বল এবং প্রাতিষ্ঠানিক ইনফ্লো। DCA করুন।", "text-green-500"
    # বেয়ারিশ (চরম লোভ + ডলার শক্তিশালী + ETF আউটফ্লো)
    elif fng_value > 75 and dxy_value > 105 and etf_flow < 0:
        return "SELL: চরম লোভ, ডলার শক্তিশালী এবং প্রাতিষ্ঠানিক আউটফ্লো। লাভ নিন।", "text-red-500"
    # সাধারণ বুলিশ
    elif fng_value < 40 and etf_flow > 0:
        return "BUY: বাজার ভয়ের মধ্যে আছে কিন্তু ফান্ড ইনফ্লো হচ্ছে। কিছু কিনতে পারেন।", "text-green-400"
    # সাধারণ বেয়ারিশ
    elif fng_value > 60 and etf_flow < 0:
        return "CAUTION: বাজারে লোভ আছে কিন্তু ফান্ড বের হচ্ছে। সতর্ক থাকুন।", "text-orange-400"
    # নিরপেক্ষ
    else:
        return "HOLD: বাজার স্বাভাবিক। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।", "text-yellow-500"

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_dxy()
btc_val = get_btc_price()
etf_val = get_etf_flow()
action_text, action_color = get_action_plan(fng_val, dxy_val, etf_val)
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ৬. HTML টেমপ্লেট তৈরি ও ফাইল রাইট করা
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Macro Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white font-sans p-6">
    <div class="max-w-4xl mx-auto">
        <h1 class="text-2xl font-bold mb-2 text-center text-blue-400">My Crypto Spot Dashboard</h1>
        <p class="text-center text-gray-400 mb-6 text-sm">Last Updated: {current_date} (UTC)</p>

        <div class="grid grid-cols-1 gap-4 mb-6">
            
            <!-- BTC Price Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Bitcoin Price (USD)</h2>
                <div class="text-4xl font-bold mb-1 text-orange-500">${btc_val:,}</div>
                <p class="text-gray-400">Live Spot Price</p>
            </div>

            <!-- ETF Flow Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Spot ETF Fund Flow (Daily)</h2>
                <div class="text-4xl font-bold mb-1 { 'text-green-500' if etf_val > 0 else 'text-red-500' }">${etf_val}M</div>
                <p class="text-gray-400">Institutional Liquidity</p>
            </div>

            <!-- Fear & Greed Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Market Sentiment (Fear & Greed)</h2>
                <div class="text-4xl font-bold mb-1 { 'text-red-500' if fng_val > 75 else 'text-green-500' if fng_val < 25 else 'text-yellow-500' }">{fng_val}</div>
                <p class="text-gray-400">{fng_class}</p>
            </div>

            <!-- DXY Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Dollar Index (DXY)</h2>
                <div class="text-4xl font-bold mb-1 { 'text-green-500' if dxy_val != 'N/A' and dxy_val < 105 else 'text-red-500' if dxy_val != 'N/A' else 'text-gray-500' }">{dxy_val}</div>
                <p class="text-gray-400">Macro Liquidity Indicator</p>
            </div>
        </div>

        <!-- Action Plan Card -->
        <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
            <h2 class="text-lg font-semibold mb-2 text-gray-300">My Action Plan</h2>
            <p class="text-xl font-bold {action_color}">{action_text}</p>
        </div>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as file:
    file.write(html_content)

print("Dashboard updated successfully! index.html created.")
