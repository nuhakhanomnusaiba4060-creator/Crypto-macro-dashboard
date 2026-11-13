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

# ২. ডলার ইনডেক্স (DXY) ডেটা আনা (ডেমো ডেটা)
def get_dxy():
    return 104.50 

# ৩. সিদ্ধান্ত নির্ধারণের লজিক (Action Plan)
def get_action_plan(fng_value, dxy_value):
    if fng_value < 25 and dxy_value < 105:
        return "BUY: চরম ভয় এবং ডলার দুর্বল। ধীরে ধীরে DCA করুন।", "text-green-500"
    elif fng_value > 75 and dxy_value > 105:
        return "SELL/HOLD: চরম লোভ এবং ডলার শক্তিশালী। নতুন কেনা বন্ধ করুন, কিছু লাভ নিন।", "text-red-500"
    else:
        return "HOLD: বাজার স্বাভাবিক। রেগুলার প্ল্যান অনুযায়ী হোল্ড করুন।", "text-yellow-500"

# ডেটা প্রসেসিং
fng_val, fng_class = get_fear_and_greed()
dxy_val = get_dxy()
action_text, action_color = get_action_plan(fng_val, dxy_val)
current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ৪. HTML টেমপ্লেট তৈরি ও ফাইল রাইট করা
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
            <!-- Fear & Greed Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Market Sentiment (Fear & Greed)</h2>
                <div class="text-4xl font-bold mb-1 { 'text-red-500' if fng_val > 75 else 'text-green-500' if fng_val < 25 else 'text-yellow-500' }">{fng_val}</div>
                <p class="text-gray-400">{fng_class}</p>
            </div>

            <!-- DXY Card -->
            <div class="bg-gray-800 p-4 rounded-lg shadow-lg border border-gray-700">
                <h2 class="text-lg font-semibold mb-2 text-gray-300">Dollar Index (DXY)</h2>
                <div class="text-4xl font-bold mb-1 { 'text-green-500' if dxy_val < 105 else 'text-red-500' }">{dxy_val}</div>
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
