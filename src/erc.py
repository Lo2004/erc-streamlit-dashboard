from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def hedge_gold_series(
    prices: pd.DataFrame,
    gold_code: str,
    equity_code: str,
    spot_gold_code: str,
) -> tuple[pd.Series, dict[str, float]]:
    panel = prices[[gold_code, equity_code, spot_gold_code]].dropna().sort_index()
    ret_reg = np.log(panel).diff().dropna()
    x = np.column_stack(
        [
            np.ones(len(ret_reg)),
            ret_reg[equity_code].values,
            ret_reg[spot_gold_code].values,
        ]
    )
    y = ret_reg[gold_code].values
    alpha, beta_equity, beta_spot = np.linalg.lstsq(x, y, rcond=None)[0]

    hedged_ret = ret_reg[gold_code] - beta_equity * ret_reg[equity_code]
    hedged_px = np.exp(hedged_ret.cumsum())
    hedged_px = hedged_px / hedged_px.iloc[0] * panel.loc[hedged_ret.index, gold_code].iloc[0]
    return hedged_px.rename("gold_hedged"), {
        "alpha": float(alpha),
        "beta_equity": float(beta_equity),
        "beta_spot_gold": float(beta_spot),
    }


def solve_erc_weights(cov: np.ndarray, w_init: np.ndarray | None = None) -> np.ndarray:
    n = cov.shape[0]
    cov = np.asarray(cov, dtype=float)
    cov = (cov + cov.T) / 2.0 + np.eye(n) * 1e-8

    if w_init is None:
        w_init = np.full(n, 1.0 / n)

    bounds = [(1e-6, 1.0)] * n
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)

    def objective(w: np.ndarray) -> float:
        port_var = float(w @ cov @ w)
        if port_var <= 0:
            return 1e6
        mrc = cov @ w
        risk_contrib = w * mrc / np.sqrt(port_var)
        return float(np.sum((risk_contrib - risk_contrib.mean()) ** 2))

    res = minimize(
        objective,
        w_init,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-12},
    )
    if not res.success:
        w = np.full(n, 1.0 / n)
    else:
        w = np.clip(res.x, 0.0, 1.0)
        if w.sum() <= 0:
            w = np.full(n, 1.0 / n)
    return w / w.sum()


def compute_erc_weights(
    returns: pd.DataFrame,
    lookback: int = 60,
    rebalance: str = "M",
) -> pd.DataFrame:
    idx = returns.index
    weights = pd.DataFrame(np.nan, index=idx, columns=returns.columns)
    prev_w = None

    if rebalance == "D":
        rebalance_dates = idx[lookback - 1 :]
    elif rebalance == "M":
        rebalance_dates = idx.to_series().groupby(pd.Grouper(freq="ME")).max().dropna()
    else:
        raise ValueError("rebalance must be 'D' or 'M'.")

    for dt in rebalance_dates:
        pos = idx.get_loc(dt)
        if pos < lookback - 1:
            continue
        win = returns.iloc[pos - lookback + 1 : pos + 1]
        w = solve_erc_weights(win.cov().values, prev_w)
        weights.loc[dt] = w
        prev_w = w

    weights = weights.ffill().fillna(1.0 / returns.shape[1])
    return weights.shift(1).fillna(weights.iloc[0])


def run_erc_backtest(
    asset_prices: pd.DataFrame,
    lookback: int = 60,
    rebalance: str = "M",
) -> dict[str, pd.DataFrame | pd.Series]:
    returns = asset_prices.pct_change().dropna()
    weights = compute_erc_weights(returns, lookback=lookback, rebalance=rebalance)
    port_ret = (weights * returns).sum(axis=1)
    nav = (1.0 + port_ret).cumprod().rename("ERC")
    drawdown = (nav / nav.cummax() - 1.0).rename("ERC")
    turnover = (weights.diff().abs().sum(axis=1) / 2.0).fillna(0.0).rename("turnover")
    return {
        "returns": port_ret,
        "weights": weights,
        "nav": nav,
        "drawdown": drawdown,
        "turnover": turnover,
    }
