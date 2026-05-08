"""
Gold Trading Bot — パラメータ最適化
=====================================
backtest.py のロジックを使い、SL乗数・RR比を総当たりで検証して
最も成績のよい組み合わせを見つける。

使い方:
    python optimize.py

出力:
    - コンソール: 上位10パターンの成績一覧
    - optimize_result.csv: 全パターンの結果
    - optimize_heatmap.png: PF・勝率のヒートマップ
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import itertools

from backtest import generate_signals, run_backtest


# ─────────────────────────────────────────────
# 最適化パラメータグリッド
# ─────────────────────────────────────────────
SL_MULT_RANGE = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]   # SL ATR乗数
TP_RR_RANGE   = [1.0, 1.2, 1.5, 1.8, 2.0, 2.5]   # RR比


# ─────────────────────────────────────────────
# ヒートマップ出力
# ─────────────────────────────────────────────
def plot_heatmap(results: pd.DataFrame, output_path: str = 'optimize_heatmap.png') -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor='#0d1117')
    fig.suptitle('Parameter Optimization Heatmap', color='#e6edf3', fontsize=13, fontweight='bold')

    metrics = [('プロフィットファクター', 'PF'), ('勝率(%)', 'Win Rate (%)')]

    for ax, (col, label) in zip(axes, metrics):
        pivot = results.pivot(index='sl_mult', columns='tp_rr', values=col)
        ax.set_facecolor('#161b22')
        im = ax.imshow(pivot.values, cmap='RdYlGn', aspect='auto')
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_yticks(range(len(pivot.index)))
        ax.set_xticklabels([f'{v:.1f}' for v in pivot.columns], color='#8b949e')
        ax.set_yticklabels([f'{v:.1f}' for v in pivot.index], color='#8b949e')
        ax.set_xlabel('TP RR比', color='#8b949e')
        ax.set_ylabel('SL ATR乗数', color='#8b949e')
        ax.set_title(label, color='#e6edf3', fontsize=11)

        for i, j in itertools.product(range(pivot.shape[0]), range(pivot.shape[1])):
            val = pivot.values[i, j]
            text = f'{val:.2f}' if not np.isnan(val) else '-'
            ax.text(j, i, text, ha='center', va='center', fontsize=8,
                    color='#0d1117' if not np.isnan(val) else '#8b949e')

        plt.colorbar(im, ax=ax)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    print(f"ヒートマップ保存: {output_path}")


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────
def main():
    print("=" * 55)
    print("Gold Bot パラメータ最適化")
    print("=" * 55)

    # データ取得（backtest.pyと同じ）
    print("\n📥 データ取得中（GC=F 15分足）...")
    df = yf.download("GC=F", interval="15m", period="60d", progress=False)
    # 長期検証したい場合:
    # df = yf.download("GC=F", interval="60m", period="2y", progress=False)

    if df.empty:
        print("❌ データ取得失敗")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.dropna(subset=['High', 'Low', 'Close', 'Open'], inplace=True)

    print(f"✅ {len(df)}本のデータを取得")
    print(f"   期間: {df.index[0]} 〜 {df.index[-1]}")

    # シグナル生成（1回だけ）
    print("\n⚙️  シグナル生成中...")
    df = generate_signals(df)

    # グリッドサーチ
    total_patterns = len(SL_MULT_RANGE) * len(TP_RR_RANGE)
    print(f"\n🔍 最適化開始（{total_patterns}パターン）...")

    rows = []
    for i, (sl_mult, tp_rr) in enumerate(itertools.product(SL_MULT_RANGE, TP_RR_RANGE), 1):
        trades, metrics = run_backtest(
            df,
            sl_atr_mult=sl_mult,
            tp_rr=tp_rr,
            initial_capital=10000.0,
            risk_per_trade=0.01,
        )
        if 'error' in metrics or trades.empty:
            continue

        rows.append({
            'sl_mult':              sl_mult,
            'tp_rr':                tp_rr,
            'トレード数':            metrics['トレード数'],
            '勝率(%)':              metrics['勝率(%)'],
            'プロフィットファクター': metrics['プロフィットファクター'],
            '期待値($/trade)':      metrics['期待値($/trade)'],
            'トータルリターン(%)':   metrics['トータルリターン(%)'],
            '最大DD(%)':            metrics['最大DD(%)'],
            '実RR比':               metrics['実RR比'],
        })

        print(f"  [{i:>2}/{total_patterns}] SL={sl_mult:.1f} × RR={tp_rr:.1f}"
              f"  →  勝率:{metrics['勝率(%)']:.1f}%  PF:{metrics['プロフィットファクター']:.2f}"
              f"  DD:{metrics['最大DD(%)']:.1f}%")

    if not rows:
        print("❌ 有効なトレードなし")
        return

    results = pd.DataFrame(rows)

    # ── ランキング表示（PF順）──
    print("\n" + "=" * 55)
    print("🏆 上位10パターン（プロフィットファクター順）")
    print("=" * 55)
    top10 = results.sort_values('プロフィットファクター', ascending=False).head(10)
    for _, r in top10.iterrows():
        print(
            f"  SL={r['sl_mult']:.1f} × RR={r['tp_rr']:.1f}"
            f"  |  勝率:{r['勝率(%)']:.1f}%"
            f"  |  PF:{r['プロフィットファクター']:.2f}"
            f"  |  DD:{r['最大DD(%)']:.1f}%"
            f"  |  リターン:{r['トータルリターン(%)']:.1f}%"
        )

    best = top10.iloc[0]
    print(f"\n✅ 推奨パラメータ")
    print(f"   sl_atr_mult = {best['sl_mult']}")
    print(f"   tp_rr       = {best['tp_rr']}")
    print(f"\n   ⚠️  過去データへの最適化です。必ずリアルで検証してください。")

    # CSV出力
    csv_path = 'optimize_result.csv'
    results.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n💾 全結果: {csv_path}")

    # ヒートマップ
    img_path = 'optimize_heatmap.png'
    plot_heatmap(results, img_path)

    print("\n✅ 完了")


if __name__ == "__main__":
    main()
