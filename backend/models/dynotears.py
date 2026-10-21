"""DYNOTEARS — structure learning for time series (Pamfil et al., AISTATS 2020).

Learns, from a multivariate time series X (T x d), a structural VAR

    X_t = X_t W + X_{t-1} A_1 + ... + X_{t-p} A_p + noise

where W (d x d) holds contemporaneous edges and must be acyclic, and A_k holds
lagged edges (always acyclic in time). Acyclicity is the smooth NOTEARS
constraint h(W) = tr(exp(W o W)) - d = 0, enforced with an augmented Lagrangian;
sparsity comes from L1 penalties. Each subproblem is solved with L-BFGS-B on the
positive/negative split of the weights, exactly as in the paper.

Pure numpy/scipy — no heavy dependency — so it runs anywhere KAIROS runs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import scipy.linalg as sla
import scipy.optimize as sopt

logger = logging.getLogger("kairos.model.dynotears")


@dataclass
class DynotearsResult:
    W: np.ndarray        # (d, d)    W[i, j]: i(t)     -> j(t)
    A: np.ndarray        # (p*d, d)  A[k*d + i, j]: i(t-k-1) -> j(t)
    h: float             # final acyclicity violation
    lags: int


def _lagged(X: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    T = X.shape[0]
    Xt = X[p:]
    Xlags = np.hstack([X[p - k - 1: T - k - 1] for k in range(p)])
    return Xt, Xlags


def dynotears(
    X: np.ndarray,
    p: int = 1,
    lambda_w: float = 0.05,
    lambda_a: float = 0.05,
    max_iter: int = 100,
    h_tol: float = 1e-8,
    rho_max: float = 1e16,
    w_threshold: float = 0.0,
) -> DynotearsResult:
    X = np.asarray(X, dtype=float)
    T, d = X.shape
    if T <= p + 1:
        raise ValueError("Not enough samples for the requested lag order")
    Xt, Xlags = _lagged(X, p)
    n = Xt.shape[0]
    pd_ = p * d

    def unpack(x):
        w = (x[: d * d] - x[d * d: 2 * d * d]).reshape(d, d)
        a = (x[2 * d * d: 2 * d * d + pd_ * d] - x[2 * d * d + pd_ * d:]).reshape(pd_, d)
        return w, a

    def h_func(W):
        E = sla.expm(W * W)
        return np.trace(E) - d, E

    def objective(x, rho, alpha):
        W, A = unpack(x)
        R    = Xt - Xt @ W - Xlags @ A
        loss = 0.5 / n * np.sum(R ** 2)
        h, E = h_func(W)
        obj  = loss + 0.5 * rho * h * h + alpha * h + lambda_w * x[: 2 * d * d].sum() \
            + lambda_a * x[2 * d * d:].sum()
        g_w  = -1.0 / n * Xt.T @ R + (rho * h + alpha) * (E.T * 2 * W)
        g_a  = -1.0 / n * Xlags.T @ R
        grad = np.concatenate([
            (g_w + lambda_w).ravel(), (-g_w + lambda_w).ravel(),
            (g_a + lambda_a).ravel(), (-g_a + lambda_a).ravel(),
        ])
        return obj, grad

    # no self-loops in W; lagged self-effects (autoregression) are allowed
    bnds_w = [(0, 0) if i == j else (0, None) for i in range(d) for j in range(d)]
    bounds = bnds_w * 2 + [(0, None)] * (2 * pd_ * d)

    x   = np.zeros(2 * d * d + 2 * pd_ * d)
    rho, alpha, h = 1.0, 0.0, np.inf
    for _ in range(max_iter):
        h_new = np.inf
        while rho < rho_max:
            sol = sopt.minimize(objective, x, args=(rho, alpha), jac=True,
                                method="L-BFGS-B", bounds=bounds)
            x_new = sol.x
            h_new, _ = h_func(unpack(x_new)[0])
            if h_new > 0.25 * h:
                rho *= 10
            else:
                break
        x, h = x_new, h_new
        alpha += rho * h
        if h <= h_tol or rho >= rho_max:
            break

    W, A = unpack(x)
    if w_threshold > 0:
        W[np.abs(W) < w_threshold] = 0
        A[np.abs(A) < w_threshold] = 0
    return DynotearsResult(W=W, A=A, h=float(h), lags=p)


def granger_matrix(X: np.ndarray, p: int = 1) -> np.ndarray:
    """Cheap fallback: |partial lagged regression coefficient| of i(t-1..p) on j(t)."""
    Xt, Xlags = _lagged(np.asarray(X, float), p)
    coef, *_ = np.linalg.lstsq(Xlags, Xt, rcond=None)      # (p*d, d)
    d = X.shape[1]
    return np.abs(coef.reshape(p, d, d)).max(axis=0)
