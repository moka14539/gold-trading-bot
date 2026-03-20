import yfinance as yf
import pandas as pd
import mplfinance as mpf
import requests
import json
import os
from datetime import datetime
import pytz

# --- 設定（GitHubのSecretsに登録してください） ---
ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
USER_ID = os.getenv('LINE_USER_ID')
IMGBB_API_KEY = os.getenv('IMGBB_API_KEY') # 画像送信に必須

def send_line_with_chart(text, image_url=None):
    """LINEにテキストと画像を送る"""
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}
    messages = [{"type": "text", "text": text}]
    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })
    data = {"to": USER_ID, "messages": messages}
    requests.post(url, headers=headers, data=json.dumps(data))

def create_chart(df_1h):
    """分析用チャート画像を生成して保存する"""
    file_path = "chart.png"
    # 200日線とボリバンを計算（描画用）
    sma200 = df_1h['Close'].rolling(window=200).mean()
    ma20 = df_1h['Close'].rolling(window=20).mean()
    std = df_1h['Close'].rolling(window=20).std()
    upper = ma20 + (std * 2)
    lower = ma20 - (std * 2)

    ap = [
        mpf.make_addplot(sma200, color='orange', width=1.5), # 200日線
        mpf.make_addplot(upper, color='cyan', linestyle='--', width=0.8), # BB上限
        mpf.make_addplot(lower, color='cyan', linestyle='--', width=0.8), # BB下限
    ]
    
    # 直近50本分を描画
    mpf.plot(df_1h.tail(50), type='candle', style='charles', 
             savefig=file_path, addplot=ap, volume=False,
             title="GOLD (XAU/USD) 1H Chart", tight_layout=True)
    return file_path

def upload_to_imgbb(file_path):
    """画像をURL化する（LINE送信に必須）"""
    url = "https://api.imgbb.com/1/upload"
    with open(file_path, "rb") as f:
        payload = {"key": IMGBB_API_KEY, "image": f.read()}
        res = requests.post(url, data=payload)
    return res.json()['data']['url']

def is_market_safe():
    """取引禁止時間の判定"""
    jst = datetime.now(pytz.timezone('Asia/Tokyo'))
    if jst.weekday() >= 5: return False, "土日休止中"
    if jst.weekday() == 0 and 6 <= jst.hour < 9: return False, "月曜早朝リスク"
    if 6 <= jst.hour <= 7:
        if jst.hour == 6 or (jst.hour == 7 and jst.minute < 30): return False, "早朝メンテ"
    return True, "取引可能"

def main():
    # 1. 安全チェック
    is_safe, reason = is_market_safe()
    if not is_safe:
        print(f"Skipping: {reason}")
        return

    # 2. データ取得
    gold_1h = yf.download("GC=F", interval="60m", period="7d")
    gold_15m = yf.download("GC=F", interval="15m", period="2d")
    gold_d = yf.download("GC=F", period="2y")
    tnx = yf.download("^TNX", interval="60m", period="5d")
    usdjpy = yf.download("JPY=X", interval="60m", period="5d")

    if gold_1h.empty or gold_15m.empty: return

    # 3. 分析（ハイブリッド戦略）
    now_p = gold_1h['Close'].iloc[-1].item()
    sma200 = gold_d['Close'].rolling(window=200).mean().iloc[-1].item()
    
    # 15分足RSI（短期タイミング）
    delta_15 = gold_15m['Close'].diff()
    gain_15 = (delta_15.where(delta_15 > 0, 0)).rolling(window=14).mean()
    loss_15 = (-delta_15.where(delta_15 < 0, 0)).rolling(window=14).mean()
    rsi_15 = (100 - (100 / (1 + gain_15/loss_15))).iloc[-1].item()

    # 外部要因
    t_diff = tnx['Close'].iloc[-1].item() - tnx['Close'].iloc[-2].item()
    u_diff = usdjpy['Close'].iloc[-1].item() - usdjpy['Close'].iloc[-2].item()

    messages = []
    score = 0

    # 判定ロジック
    if now_p > sma200: # 上昇トレンド
        score += 2
        if rsi_15 < 35: messages.append("⚡15分足で絶好の押し目"); score += 1
    elif now_p < sma200: # 下落トレンド
        score -= 2
        if rsi_15 > 65: messages.append("⚡15分足で絶好の戻り売り場"); score -= 1
        
    if t_diff < 0 and u_diff < 0: messages.append("🌍マクロ追い風"); score += 2
    elif t_diff > 0 and u_diff > 0: messages.append("⛔マクロ逆風"); score -= 2

    # 4. 通知判定（スコア3以上）
    total_score = abs(score)
    if total_score >= 3:
        # チャート作成 & アップロード
        try:
            img_path = create_chart(gold_1h)
            img_url = upload_to_imgbb(img_path)
        except Exception as e:
            print(f"Image Error: {e}")
            img_url = None

        direction = "BUY" if score > 0 else "SELL"
        # ATR簡易計算(損切り・利確用)
        atr = (gold_1h['High'] - gold_1h['Low']).rolling(14).mean().iloc[-1].item()
        sl = now_p - (atr * 2.5) if direction == "BUY" else now_p + (atr * 2.5)
        tp = now_p + (atr * 4.0) if direction == "BUY" else now_p - (atr * 4.0)

        title = f"📢 【{direction}チャンス】"
        if total_score >= 4: title = f"🔥 【強・{direction}推奨】"
        if total_score >= 5: title = f"👑 【極・{direction}推奨】"

        text = f"{title}\nスコア:{total_score}\n\n" + "\n".join([f"・{m}" for m in messages])
        text += f"\n\n💰価格: ${now_p:.2f}\n🛡️損切: ${sl:.2f}\n🎯利確: ${tp:.2f}\n⏱️RSI15: {rsi_15:.1f}"
        
        send_line_with_chart(text, img_url)

if __name__ == "__main__":
    main()
