# --- main.py (テスト用：必ず送信版) ---
import yfinance as yf
import requests
import json
import os

ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    res = requests.post(url, headers=headers, data=json.dumps(data))
    print(f"Status: {res.status_code}")

def analyze_gold():
    # 動作確認用に、価格だけ取得して必ず送る
    df = yf.download("GLD", period="1d")
    latest_price = df['Close'].iloc[-1].item()
    
    send_line(f"✅ システム稼働テスト\n現在のGLD価格: ${latest_price:.2f}\nこのメッセージが届いたら自動化成功です！")

if __name__ == "__main__":
    analyze_gold()
