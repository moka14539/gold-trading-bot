import yfinance as yf
import pandas as pd
import requests
import json
import os

ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(data))

def analyze_gold_ultimate():
    # 1. データの多角取得
    gold_spot = yf.download("GLD", period="1y")                    # 日足（トレンド用）
    gold_1h = yf.download("GLD", interval="60m", period="5d")      # 1時間足（エントリー用）
    gold_fut = yf.download("GC=F", interval="60m", period="5d")    # 先物
    tnx = yf.download("^TNX", interval="60m", period="5d")         # 米10年債金利
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")      # ドル円

    messages = []

    # --- A. 長期環境認識 (日足 200日線) ---
    gold_spot['SMA200'] = gold_spot['Close'].rolling(window=200).mean()
    is_long_uptrend = gold_spot['Close'].iloc[-1].item() > gold_spot['SMA200'].iloc[-1].item()

    # --- B. MACD計算 (1時間足) ---
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    gold_1h['MACD'] = exp1 - exp2
    gold_1h['Signal'] = gold_1h['MACD'].ewm(span=9, adjust=False).mean()
    
    # ゴールデンクロス判定
    macd_cross = gold_1h['MACD'].iloc[-1].item() > gold_1h['Signal'].iloc[-1].item() and \
                 gold_1h['MACD'].iloc[-2].item() <= gold_1h['Signal'].iloc[-2].item()

    # --- C. 外部要因判定 (金利・先物・為替) ---
    t_now = tnx['Close'].iloc[-1].item()
    t_prev = tnx['Close'].iloc[-2].item()
    f_now = gold_fut['Close'].iloc[-1].item()
    f_prev = gold_fut['Close'].iloc[-2].item()
    u_now = usdjpy['Close'].iloc[-1].item()
    u_prev = usdjpy['Close'].iloc[-2].item()

    rates_falling = t_now < t_prev  # 金利低下
    fut_bullish = f_now > f_prev    # 先物上昇
    usd_weakening = u_now < u_prev  # ドル安

    # --- 4. 究極の合体ロジック ---
    # 条件1：長期が上昇トレンドであること
    # 条件2：MACDがゴールデンクロスした瞬間であること
    # 条件3：金利が低下していること（ゴールドに有利）
    
    if is_long_uptrend and macd_cross:
        status = "🛡️ 堅実な買いサイン"
        if rates_falling and fut_bullish:
            status = "🔥【超絶チャンス】全条件一致！"
        
        text = f"{status}\n\n"
        text += f"💰現物: ${gold_1h['Close'].iloc[-1].item():.2f}\n"
        text += f"📊MACD: ゴールデンクロス発生！\n"
        text += f"📉米金利: {t_now:.2f}% (低下中 ✅)\n"
        text += f"📈先物: ${f_now:.2f} (上昇中 ✅)\n"
        text += f"💴ドル円: {u_now:.2f} ({'ドル安' if usd_weakening else 'ドル高'})\n\n"
        text += "💡長期トレンドに乗り、金利低下を確認した「勝率重視」のタイミングです。"
        
        messages.append(text)

    # 送信
    if messages:
        send_line("👑ゴールド・インテリジェンス報告\n\n" + "\n\n".join(messages))
    else:
        print("現在は全ての条件を満たすチャンス待ちです。")

if __name__ == "__main__":
    analyze_gold_ultimate()
