import yfinance as yf
import pandas as pd
import requests
import json
import os

# Secretsから読み込み
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(data))

def analyze_gold():
    # データの取得
    df_daily = yf.download("GLD", period="1y")
    df_short = yf.download("GLD", interval="15m", period="5d")
    
    messages = []

    # --- 長期戦略 (200日線 & RSI) ---
    df_daily['SMA200'] = df_daily['Close'].rolling(window=200).mean()
    delta = df_daily['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df_daily['RSI'] = 100 - (100 / (1 + gain/loss))
    
    d_latest = df_daily.iloc[-1]
    d_prev = df_daily.iloc[-2]
    
    try:
        # 長期押し目条件: 200日線上 且つ RSI 50以下 且つ 前日より上昇
        if d_latest['Close'].item() > d_latest['SMA200'].item() and d_latest['RSI'].item() < 50 and d_latest['Close'].item() > d_prev['Close'].item():
            messages.append(f"【長期サイン】押し目チャンス！\n価格: ${d_latest['Close'].item():.2f}")
    except: pass

    # --- デイトレ戦略 (ボリバン突破) ---
    df_short['MA20'] = df_short['Close'].rolling(window=20).mean()
    df_short['STD'] = df_short['Close'].rolling(window=20).std()
    df_short['Upper'] = df_short['MA20'] + (df_short['STD'] * 2)
    s_latest = df_short.iloc[-1]
    
    try:
        # デイトレ条件: ボリンジャーバンド+2σを上抜け
        if s_latest['Close'].item() > s_latest['Upper'].item():
            messages.append(f"【デイトレサイン】ボリバン上限突破！強い勢いです。\n価格: ${s_latest['Close'].item():.2f}")
    except: pass

    # サインがある時だけ送信
    if messages:
        send_line("🔔ゴールド監視報告\n\n" + "\n\n".join(messages))
    else:
        print("現在はサインが出ていません。")

if __name__ == "__main__":
    analyze_gold()
