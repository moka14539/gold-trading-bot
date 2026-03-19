import yfinance as yf
import pandas as pd
import requests
import json
import os

# --- GitHubのSecretsから設定を読み込む ---
ACCESS_TOKEN = os.getenv('OcCe50iI/ARdbPZbAm4+BqEwqNL3BC5l+HabJ56a7f4OnHtLoA3y3zMvyNk38NLn3kKRv7FrNF7VHz55p/9RFKHb29G09UkHdqwwbC/ieuhZgCdb/nlmw9GcZZf2YjZF7oadKvJNdHC6awkq4QRaOwdB04t89/1O/w1cDnyilFU=')
USER_ID = os.getenv('71d9922a7127351436b04a0393f14586')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OcCe50iI/ARdbPZbAm4+BqEwqNL3BC5l+HabJ56a7f4OnHtLoA3y3zMvyNk38NLn3kKRv7FrNF7VHz55p/9RFKHb29G09UkHdqwwbC/ieuhZgCdb/nlmw9GcZZf2YjZF7oadKvJNdHC6awkq4QRaOwdB04t89/1O/w1cDnyilFU=}"
    }
    data = {
        "to": 71d9922a7127351436b04a0393f14586,
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
    
    if d_latest['Close'] > d_latest['SMA200'] and d_latest['RSI'] < 50 and d_latest['Close'] > d_prev['Close']:
        messages.append(f"【長期サイン】200日線上の押し目です！\n価格: ${d_latest['Close']:.2f} / RSI: {d_latest['RSI']:.1f}")

    # --- 戦略②：デイトレ (15分足) ---
    df_short['MA20'] = df_short['Close'].rolling(window=20).mean()
    df_short['STD'] = df_short['Close'].rolling(window=20).std()
    df_short['Upper'] = df_short['MA20'] + (df_short['STD'] * 2)
    
    s_latest = df_short.iloc[-1]
    
    if s_latest['Close'] > s_latest['Upper']:
        messages.append(f"【デイトレサイン】ボリバン上限を突破！強い勢いです。\n現在値: ${s_latest['Close']:.2f}")

    # --- 通知の実行 ---
    if messages:
        final_msg = "\n\n".join(messages)
        send_line(f"🔔ゴールド監視レポート\n\n{final_msg}")
    else:
        print("条件を満たしたサインはありません。")

if __name__ == "__main__":
    analyze_gold()
