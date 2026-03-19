import yfinance as yf
import pandas as pd
import requests
import json
import os

# --- GitHubのSecretsから設定を読み込む ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }
    data = {
        "to": USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    requests.post(url, headers=headers, data=json.dumps(data))

def analyze_gold():
    # 1. データの取得 (日足と15分足の両方)
    df_daily = yf.download("GLD", period="1y")
    df_short = yf.download("GLD", interval="15m", period="5d")
    
    messages = []

    # --- 戦略①：長期押し目買い (日足) ---
    df_daily['SMA200'] = df_daily['Close'].rolling(window=200).mean()
    # RSI計算
    delta = df_daily['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df_daily['RSI'] = 100 - (100 / (1 + gain/loss))
    
    d_latest = df_daily.iloc[-1]
    d_prev = df_daily.iloc[-2]
    
    current_close = d_latest['Close'].item()
sma200_val = d_latest['SMA200'].item()
rsi_val = d_latest['RSI'].item()
prev_close = d_prev['Close'].item()

    # --- 戦略②：デイトレ (15分足) ---
    df_short['MA20'] = df_short['Close'].rolling(window=20).mean()
    df_short['STD'] = df_short['Close'].rolling(window=20).std()
    df_short['Upper'] = df_short['MA20'] + (df_short['STD'] * 2)
    
    s_latest = df_short.iloc[-1]
    
    if current_close > sma200_val and rsi_val < 50 and current_close > prev_close:
    messages.append(f"【長期サイン】200日線上の押し目です！\n価格: ${current_close:.2f} / RSI: {rsi_val:.1f}")

    # --- 通知の実行 ---
    if messages:
        final_msg = "\n\n".join(messages)
        send_line(f"🔔ゴールド監視レポート\n\n{final_msg}")
    else:
        print("条件を満たしたサインはありません。")

if __name__ == "__main__":
    analyze_gold()
