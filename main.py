import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime
import pytz

# 環境変数（設定済みを想定）
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')

def send_line(text):
    if not text: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}
    try:
        res = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def is_market_safe():
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    if jst.weekday() >= 5: return False, "土日休止"
    if jst.weekday() == 0 and 6 <= jst.hour < 9: return False, "月曜早朝リスク"
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30): return False, "早朝メンテ"
    return True, "取引可能"

def analyze_and_send():
    is_safe, reason = is_market_safe()
    if not is_safe: return

    # 1. データ取得（期間を少し長めに設定して計算を安定させる）
    gold_1h = yf.download("GC=F", interval="60m", period="7d", progress=False)
    gold_15m = yf.download("GC=F", interval="15m", period="5d", progress=False)
    gold_d = yf.download("GC=F", period="2y", progress=False)
    tnx = yf.download("^TNX", interval="60m", period="5d", progress=False)
    dxy = yf.download("DX-Y.NYB", interval="60m", period="5d", progress=False)

    if gold_1h.empty or gold_15m.empty or dxy.empty: return

    messages = []
    score = 0
    now_p = float(gold_15m['Close'].iloc[-1].item())
    
    # --- 指標計算 (15分足 / 1時間足 / 日足) ---
    # 長期トレンド (日足200MA)
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # 15分足 RSI
    delta_15 = gold_15m['Close'].diff()
    gain = (delta_15.where(delta_15 > 0, 0)).rolling(window=14).mean()
    loss = (-delta_15.where(delta_15 < 0, 0)).rolling(window=14).mean()
    loss = loss.replace(0, 0.00001)
    rsi_15 = (100 - (100 / (1 + (gain / loss)))).iloc[-1].item()
    
    # 15分足 ボリンジャーバンド (-2σ)
    std_15 = gold_15m['Close'].rolling(window=20).std()
    ma20_15 = gold_15m['Close'].rolling(window=20).mean()
    lower_2_15 = (ma20_15 - (std_15 * 2)).iloc[-1].item()
    
    # 1時間足 MACD
    exp1 = gold_1h['Close'].ewm(span=12, adjust=False).mean()
    exp2 = gold_1h['Close'].ewm(span=26, adjust=False).mean()
    macd_1h = exp1 - exp2
    sig_1h = macd_1h.ewm(span=9, adjust=False).mean()
    
    # ATR (1h) - 損切・利確幅用
    high_low = gold_1h['High'] - gold_1h['Low']
    high_close = (gold_1h['High'] - gold_1h['Close'].shift()).abs()
    low_close = (gold_1h['Low'] - gold_1h['Close'].shift()).abs()
    atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean().iloc[-1].item()

    # マクロ要因変位
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    dxy_diff = dxy['Close'].iloc[-1].item() - dxy['Close'].iloc[-2].item()

    # --- 判定ロジック：トレンド & マクロ ---
    if now_p > sma200:
        messages.append("🟢長期上昇トレンド継続")
        score += 2
    else:
        messages.append("🔴長期下落トレンド継続")
        score -= 2

    if macd_1h.iloc[-1].item() > sig_1h.iloc[-1].item():
        score += 1
    else:
        score -= 1

    if t_diff < 0 and dxy_diff < 0:
        messages.append("🌍マクロ追い風（金利安・ドル安）")
        score += 2
    elif t_diff > 0 and dxy_diff > 0:
        messages.append("⛔マクロ逆風（金利高・ドル高）")
        score -= 2

    # --- 【新規追加】判定ロジック：押し目買い・戻り売りボーナス ---
    # 長期上昇中の「売られすぎ（押し目）」を検知
    if now_p > sma200:
        if rsi_15 <= 30:
            messages.append(f"🔥絶好の押し目（RSI売られすぎ: {rsi_15:.1f}）")
            score += 3  # 急落時のマイナスを打ち消す加点
        if now_p <= lower_2_15:
            messages.append("⚡ボリバン-2σ到達（短期反発期待）")
            score += 2

    # 長期下落中の「買われすぎ（戻り売り）」を検知
    if now_p < sma200:
        if rsi_15 >= 70:
            messages.append(f"❄️戻り売りの好機（RSI買われすぎ: {rsi_15:.1f}）")
            score -= 3
        if now_p >= (ma20_15 + (std_15 * 2)).iloc[-1].item():
            messages.append("⚡ボリバン+2σ到達（短期的な天井）")
            score -= 2

    # --- 通知実行 ---
    total_score = abs(score)
    if total_score >= 3:
        direction = "BUY" if score > 0 else "SELL"
        
        # ボラティリティが高い時は損切りを少し深めにする調整
        sl_mult = 3.5 if rsi_15 < 30 or rsi_15 > 70 else 2.5
        sl = now_p - (atr * sl_mult) if direction == "BUY" else now_p + (atr * sl_mult)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)
        
        title = f"👑【極・{direction}推奨】" if total_score >= 5 else f"📢 【{direction}チャンス】"
        output_text = f"{title}\n信頼スコア:{total_score}\n\n"
        output_text += "\n".join([f"・{m}" for m in messages])
        output_text += f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}"
        output_text += f"\n\n⏱️15m RSI: {rsi_15:.1f}"
        output_text += f"\n📊DXY変位: {dxy_diff:+.3f}"
        
        send_line(output_text)

if __name__ == "__main__":
    analyze_and_send()
