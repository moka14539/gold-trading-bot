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

def analyze_gold_pro():
    # 1. データの多角的な取得
    gold_spot = yf.download("GLD", period="5d", interval="60m")    # 現物ETF(1h)
    gold_fut = yf.download("GC=F", period="5d", interval="60m")   # ゴールド先物(1h)
    tnx = yf.download("^TNX", period="5d", interval="60m")         # 米10年債利回り
    usdjpy = yf.download("JPY=X", period="5d", interval="60m")      # ドル円

    # 最新データの抽出 (.item()でエラー回避)
    g_now = gold_spot['Close'].iloc[-1].item()
    g_prev = gold_spot['Close'].iloc[-2].item()
    f_now = gold_fut['Close'].iloc[-1].item()
    t_now = tnx['Close'].iloc[-1].item()
    t_prev = tnx['Close'].iloc[-2].item()
    u_now = usdjpy['Close'].iloc[-1].item()
    u_prev = usdjpy['Close'].iloc[-2].item()

    # --- 2. 高度なインテリジェンス判定 ---
    
    # 金利フィルター：金利が低下中（または横ばい）か？
    rates_falling = t_now <= t_prev
    # 先物フィルター：先物も現物と一緒に上がっているか？（同調確認）
    futures_bullish = f_now > gold_fut['Close'].iloc[-2].item()
    # ドル円フィルター：ドル安（円高）方向か？
    usd_weakening = u_now < u_prev

    # --- 3. ロジック合体 ---
    # 条件：現物が上昇 且つ 金利が下落 且つ 先物も強い 
    if g_now > g_prev and rates_falling and futures_bullish:
        status = "🟢 優位性あり"
        if usd_weakening:
            status = "🔥【超絶チャンス】全条件合致！"
        
        text = f"{status}\n\n"
        text += f"💰ゴールド現物: ${g_now:.2f}\n"
        text += f"📈ゴールド先物: ${f_now:.2f} (上昇)\n"
        text += f"📉米10年債金利: {t_now:.2f}% (低下中)\n"
        text += f"💴ドル円為替: {u_now:.2f} (ドル安傾向)\n\n"
        text += "💡解説: 金利低下と先物の買いが一致しており、ゴールドの上昇に強い根拠があります。"
        
        send_line(text)
    else:
        print("条件未達成（金利上昇または先物弱含み）")

if __name__ == "__main__":
    analyze_gold_pro()
