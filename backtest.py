"""
Gold Trading Bot — バックテストエンジン
=========================================
使い方:
    python backtest.py

出力:
    - コンソール: 勝率・期待値・最大DDなど主要指標
    - backtest_result.csv: 全トレード履歴
    - backtest_equity.png: 資産曲線グラフ
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime


# ─────────────────────────────────────────────
# 指標計算
# ─────────────────────────────────────────────

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low']  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    high_diff  = df['High'].diff()
    minus_move = (-df['Low'].diff())

    plus_dm  = high_diff.where((high_diff > 0) & (high_diff > minus_move), 0.0)
    minus_dm = minus_move.where((minus_move > 0) & (minus_move > high_diff), 0.0)

    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low']  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_adx  = tr.rolling(period).mean()
    plus_di  = 100 * (plus_dm.rolling(period).mean()  / atr_adx.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr_adx.replace(0, np.nan))
    dx  = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.rolling(period).mean()

    return pd.DataFrame({'adx': adx, 'plus_di': plus_di, 'minus_di': minus_di})


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


# ─────────────────────────────────────────────
# シグナル生成（main_revised.py と同じロジック）
# ─────────────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    df: 15分足データ（Close, High, Low, Open, Volume）
    戻り値: signal列 (1=BUY, -1=SELL, 0=なし) + score列 を追加したDataFrame
    """
    df = df.copy()

    # 指標
    atr_series  = calc_atr(df)
    atr_mean    = atr_series.rolling(100).mean()
    adx_df      = calc_adx(df)
    rsi         = calc_rsi(df['Close'])
    sma200      = calc_sma(df['Close'], 200)

    ph = df['High'].rolling(20).max().shift(1)   # 前足までの20本高値
    pl = df['Low'].rolling(20).min().shift(1)    # 前足までの20本安値
    body    = (df['Close'] - df['Open']).abs()
    wick_up = df['High'] - df[['Open', 'Close']].max(axis=1)

    signals = []
    scores  = []

    for i in range(len(df)):
        if i < 200:
            signals.append(0)
            scores.append(0)
            continue

        trend_score = macro_score = logic_score = 0
        now_p  = df['Close'].iloc[i]
        rsi_v  = rsi.iloc[i]
        adx_v  = adx_df['adx'].iloc[i]
        p_di   = adx_df['plus_di'].iloc[i]
        m_di   = adx_df['minus_di'].iloc[i]
        atr_v  = atr_series.iloc[i]
        atrm_v = atr_mean.iloc[i]
        sma_v  = sma200.iloc[i]

        if any(pd.isna(x) for x in [rsi_v, adx_v, atr_v, sma_v]):
            signals.append(0)
            scores.append(0)
            continue

        # 長期トレンド
        is_up = now_p > sma_v
        trend_score += 2 if is_up else -2

        # 押し目・戻り売り
        if is_up and rsi_v <= 35:
            logic_score += 3
        elif not is_up and rsi_v >= 65:
            logic_score -= 3

        # ADX
        if adx_v > 25:
            if p_di > m_di:
                logic_score += 1
            else:
                logic_score -= 1

        # フェイクブレイク
        ph_v = ph.iloc[i]
        pl_v = pl.iloc[i]
        hi   = df['High'].iloc[i]
        lo   = df['Low'].iloc[i]
        bd   = body.iloc[i]
        wu   = wick_up.iloc[i]

        if not pd.isna(ph_v) and hi > ph_v and (hi - ph_v) < atr_v * 0.5:
            if wu > bd * 1.5:
                logic_score -= 1
        if not pd.isna(pl_v) and lo < pl_v and (pl_v - lo) < atr_v * 0.5:
            logic_score += 1

        # ※ マクロ（TNX/DXY）はバックテスト内では省略（15分足に同期させると複雑なため）
        # ※ 時間帯スコアも省略（純粋なシグナル評価のため）

        total = trend_score + macro_score + logic_score
        signals.append(1 if total >= 3 else (-1 if total <= -3 else 0))
        scores.append(total)

    df['signal'] = signals
    df['score']  = scores
    df['atr']    = atr_series
    df['atr_mean'] = atr_mean
    df['rsi']    = rsi
    df['adx']    = adx_df['adx']
    return df


# ─────────────────────────────────────────────
# バックテスト実行
# ─────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    sl_atr_mult: float = 2.5,
    tp_rr: float = 1.5,
    initial_capital: float = 10000.0,
    risk_per_trade: float = 0.01,   # 1トレードで資金の1%をリスク
) -> tuple[pd.DataFrame, dict]:
    """
    Returns:
        trades_df: 全トレード履歴
        metrics:   勝率・期待値などの辞書
    """
    trades = []
    equity = initial_capital
    in_trade = False
    entry_price = sl = tp = direction = entry_idx = None

    for i in range(len(df)):
        row = df.iloc[i]

        # ── ポジション保有中の決済チェック ──
        if in_trade:
            hi = row['High']
            lo = row['Low']
            closed = False

            if direction == 1:   # BUY
                if lo <= sl:
                    pnl_pts = sl - entry_price
                    closed = True; result = 'LOSS'
                elif hi >= tp:
                    pnl_pts = tp - entry_price
                    closed = True; result = 'WIN'
            else:                # SELL
                if hi >= sl:
                    pnl_pts = entry_price - sl
                    closed = True; result = 'LOSS'
                elif lo <= tp:
                    pnl_pts = entry_price - tp
                    closed = True; result = 'WIN'

            if closed:
                # 損益計算（リスク額ベース）
                risk_amount = equity * risk_per_trade
                sl_dist = abs(entry_price - sl)
                if sl_dist > 0:
                    size = risk_amount / sl_dist
                    pnl  = pnl_pts * size
                else:
                    pnl = 0

                equity += pnl
                trades.append({
                    'entry_time': df.index[entry_idx],
                    'exit_time':  df.index[i],
                    'direction':  'BUY' if direction == 1 else 'SELL',
                    'entry_price': entry_price,
                    'sl': sl,
                    'tp': tp,
                    'pnl': pnl,
                    'result': result,
                    'equity': equity,
                    'score': df['score'].iloc[entry_idx],
                    'rsi': df['rsi'].iloc[entry_idx],
                    'adx': df['adx'].iloc[entry_idx],
                })
                in_trade = False

        # ── 新規エントリー ──
        if not in_trade and row['signal'] != 0:
            atr_v    = row['atr']
            atrm_v   = row['atr_mean']
            rsi_v    = row['rsi']

            if pd.isna(atr_v) or atr_v == 0:
                continue

            # 動的SL乗数
            mult = sl_atr_mult
            if not pd.isna(atrm_v) and atrm_v > 0:
                if atr_v > atrm_v * 1.3:
                    mult += 0.5
                elif atr_v < atrm_v * 0.7:
                    mult -= 0.3
            if rsi_v < 30 or rsi_v > 70:
                mult += 0.5
            mult = max(mult, 1.5)

            price = row['Close']
            sig   = row['signal']
            sl_price = price - atr_v * mult if sig == 1 else price + atr_v * mult
            tp_price = price + atr_v * mult * tp_rr if sig == 1 else price - atr_v * mult * tp_rr

            in_trade    = True
            direction   = sig
            entry_price = price
            sl          = sl_price
            tp          = tp_price
            entry_idx   = i

    trades_df = pd.DataFrame(trades)
    metrics = _calc_metrics(trades_df, initial_capital)
    return trades_df, metrics


# ─────────────────────────────────────────────
# パフォーマンス指標計算
# ─────────────────────────────────────────────

def _calc_metrics(trades: pd.DataFrame, initial_capital: float) -> dict:
    if trades.empty:
        return {'error': 'トレードなし'}

    total      = len(trades)
    wins       = (trades['result'] == 'WIN').sum()
    losses     = (trades['result'] == 'LOSS').sum()
    win_rate   = wins / total * 100

    avg_win    = trades.loc[trades['result'] == 'WIN',  'pnl'].mean()
    avg_loss   = trades.loc[trades['result'] == 'LOSS', 'pnl'].mean()
    rr_actual  = abs(avg_win / avg_loss) if avg_loss != 0 else np.nan

    total_pnl  = trades['pnl'].sum()
    final_eq   = trades['equity'].iloc[-1]
    total_ret  = (final_eq - initial_capital) / initial_capital * 100

    # 最大ドローダウン
    equity_curve = trades['equity']
    peak = equity_curve.cummax()
    dd   = (equity_curve - peak) / peak * 100
    max_dd = dd.min()

    # プロフィットファクター
    gross_profit = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gross_loss   = trades.loc[trades['pnl'] < 0, 'pnl'].abs().sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else np.nan

    # 期待値（1トレードあたり平均損益）
    expectancy = trades['pnl'].mean()

    return {
        'トレード数':       total,
        '勝ちトレード':     int(wins),
        '負けトレード':     int(losses),
        '勝率(%)':         round(win_rate, 1),
        '平均利益':        round(avg_win, 2),
        '平均損失':        round(avg_loss, 2),
        '実RR比':          round(rr_actual, 2),
        'プロフィットファクター': round(pf, 2),
        '期待値($/trade)': round(expectancy, 2),
        '総損益($)':       round(total_pnl, 2),
        '最終資産($)':     round(final_eq, 2),
        'トータルリターン(%)': round(total_ret, 1),
        '最大DD(%)':       round(max_dd, 1),
    }


# ─────────────────────────────────────────────
# 資産曲線グラフ出力
# ─────────────────────────────────────────────

def plot_equity(trades: pd.DataFrame, output_path: str = 'backtest_equity.png') -> None:
    if trades.empty:
        return

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), facecolor='#0d1117')
    fig.suptitle('Gold Bot — Backtest Results', color='#e6edf3', fontsize=15, fontweight='bold', y=0.98)

    colors = {'WIN': '#3fb950', 'LOSS': '#f85149'}
    ax_eq, ax_pnl, ax_dd = axes

    # ── 資産曲線 ──
    ax_eq.set_facecolor('#161b22')
    ax_eq.plot(trades['exit_time'], trades['equity'], color='#58a6ff', linewidth=1.5, label='Equity')
    ax_eq.fill_between(trades['exit_time'], trades['equity'], alpha=0.15, color='#58a6ff')
    ax_eq.set_ylabel('Equity ($)', color='#8b949e')
    ax_eq.tick_params(colors='#8b949e')
    ax_eq.set_title('Equity Curve', color='#8b949e', fontsize=10)
    for spine in ax_eq.spines.values():
        spine.set_edgecolor('#30363d')

    # ── 損益バー ──
    ax_pnl.set_facecolor('#161b22')
    bar_colors = [colors[r] for r in trades['result']]
    ax_pnl.bar(trades['exit_time'], trades['pnl'], color=bar_colors, width=0.01, alpha=0.85)
    ax_pnl.axhline(0, color='#30363d', linewidth=0.8)
    ax_pnl.set_ylabel('Trade P&L ($)', color='#8b949e')
    ax_pnl.tick_params(colors='#8b949e')
    ax_pnl.set_title('Per-Trade P&L', color='#8b949e', fontsize=10)
    for spine in ax_pnl.spines.values():
        spine.set_edgecolor('#30363d')

    # ── ドローダウン ──
    ax_dd.set_facecolor('#161b22')
    peak = trades['equity'].cummax()
    dd   = (trades['equity'] - peak) / peak * 100
    ax_dd.fill_between(trades['exit_time'], dd, color='#f85149', alpha=0.4)
    ax_dd.plot(trades['exit_time'], dd, color='#f85149', linewidth=0.8)
    ax_dd.set_ylabel('Drawdown (%)', color='#8b949e')
    ax_dd.tick_params(colors='#8b949e')
    ax_dd.set_title('Drawdown', color='#8b949e', fontsize=10)
    for spine in ax_dd.spines.values():
        spine.set_edgecolor('#30363d')

    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', color='#8b949e')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"グラフ保存: {output_path}")


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("Gold Bot バックテスト開始")
    print("=" * 50)

    # データ取得（2年分の15分足）
    print("\n📥 データ取得中（GC=F 15分足 / 2年）...")
    df = yf.download("GC=F", interval="15m", period="60d", progress=False)
    # ※ yfinanceの15分足は最大60日。長期検証には1時間足を推奨。
    # 1時間足で検証したい場合は下記に切り替え:
    # df = yf.download("GC=F", interval="60m", period="2y", progress=False)

    if df.empty:
        print("❌ データ取得失敗")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(subset=['High', 'Low', 'Close', 'Open'], inplace=True)

    print(f"✅ {len(df)}本のデータを取得")
    print(f"   期間: {df.index[0]} 〜 {df.index[-1]}")

    # シグナル生成
    print("\n⚙️  シグナル生成中...")
    df = generate_signals(df)
    sig_count = (df['signal'] != 0).sum()
    print(f"   シグナル数: {sig_count}")

    # バックテスト実行
    print("\n🔄 バックテスト実行中...")
    trades, metrics = run_backtest(
        df,
        sl_atr_mult=2.5,
        tp_rr=1.5,
        initial_capital=10000.0,
        risk_per_trade=0.01,
    )

    # 結果表示
    print("\n" + "=" * 50)
    print("📊 バックテスト結果")
    print("=" * 50)
    if 'error' in metrics:
        print(f"❌ {metrics['error']}")
    else:
        for k, v in metrics.items():
            print(f"  {k:<25} {v}")

    # CSV出力
    if not trades.empty:
        csv_path = 'backtest_result.csv'
        trades.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"\n💾 トレード履歴: {csv_path}")

        # グラフ出力
        img_path = 'backtest_equity.png'
        plot_equity(trades, img_path)

    print("\n✅ 完了")


if __name__ == "__main__":
    main()
