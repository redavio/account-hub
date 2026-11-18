"""Exact stratified test and sample-size check. Standard library only."""
from math import comb, erf, sqrt


def _hypergeom(n_total, n_success, n_draw):
    """P(k) for k successes in n_draw draws without replacement."""
    denom = comb(n_total, n_draw)
    lo, hi = max(0, n_draw - (n_total - n_success)), min(n_draw, n_success)
    return {k: comb(n_success, k) * comb(n_total - n_success, n_draw - k) / denom for k in range(lo, hi + 1)}


def exact_stratified(strata):
    """Program vs holdout (or any exposed vs control), compared within strata, exactly.

    strata: list of (exposed_n, exposed_advanced, control_n, control_advanced).
    Lift = weighted average of (exposed rate - control rate) within strata, weighted by exposed counts.
    p-value: the exact stratified (Cochran-Mantel-Haenszel) test. With each stratum's totals fixed,
    exposed advancers follow a hypergeometric distribution; their sum's distribution is the
    convolution of those, which is cheap to compute exactly at any size.
    """
    usable = [s for s in strata if s[0] > 0 and s[2] > 0]
    if not usable:
        return None
    n1_total = sum(s[0] for s in usable)
    lift = sum((n1 / n1_total) * (a1 / n1 - a0 / n0) for n1, a1, n0, a0 in usable)
    dist = {0: 1.0}
    observed = 0
    for n1, a1, n0, a0 in usable:
        piece = _hypergeom(n1 + n0, a1 + a0, n1)
        nxt = {}
        for k1, p1 in dist.items():
            for k2, p2 in piece.items():
                nxt[k1 + k2] = nxt.get(k1 + k2, 0.0) + p1 * p2
        dist = nxt
        observed += a1
    mean = sum(k * p for k, p in dist.items())
    dev = abs(observed - mean) - 1e-9
    p = sum(pr for k, pr in dist.items() if abs(k - mean) >= dev)
    return _result(usable, lift, p)


def _result(usable, lift, p):
    n1 = sum(s[0] for s in usable)
    n0 = sum(s[2] for s in usable)
    return {"lift": lift, "p": min(1.0, p), "n_exposed": n1, "n_control": n0,
            "rate_exposed": sum(s[1] for s in usable) / n1, "rate_control": sum(s[3] for s in usable) / n0}


def holm(pvalues):
    """Holm adjustment for testing several channels and roles at once."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adj, running = [0.0] * len(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[i]))
        adj[i] = running
    return adj


def _phi(z):
    return 0.5 * (1 + erf(z / sqrt(2)))


def _z(p):
    """Inverse normal CDF by bisection (no scipy)."""
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def sample_check(lift, rate_control, n1, n0, alpha=0.05, power=0.8):
    """Could groups this size detect a lift this big? If not, how many more accounts?

    Uses the customer's own control rate and the lift observed, with the usual
    conventions (5% false-alarm rate, 80% chance of detecting a real effect).
    Returns (enough_data, more_accounts_needed).
    """
    if n1 == 0 or n0 == 0 or lift == 0:
        return True, 0
    lift = abs(lift)   # a small sample can't rule out an effect either way
    var = max(rate_control * (1 - rate_control), 1e-6)
    se = sqrt(var * (1 / n1 + 1 / n0))
    za = _z(1 - alpha / 2)
    achieved = _phi(lift / se - za)
    if achieved >= power:
        return True, 0
    # Growing both groups by the same factor s shrinks (1/n1 + 1/n0) by s.
    scale = ((za + _z(power)) * sqrt(var) / lift) ** 2 * (1 / n1 + 1 / n0)
    more = int(round((n1 + n0) * (scale - 1)))
    return False, max(more, 1)


def logit(X, y, ridge=1e-4, iters=50):
    """Logistic regression by Newton steps. Returns (coefficients, standard errors).
    A tiny ridge keeps it stable when a factor perfectly predicts the outcome."""
    k = len(X[0])
    b = [0.0] * k
    for _ in range(iters):
        g = [-ridge * bj for bj in b]
        H = [[(ridge if i == j else 0.0) for j in range(k)] for i in range(k)]
        for xi, yi in zip(X, y):
            eta = sum(bj * xj for bj, xj in zip(b, xi))
            eta = max(-30.0, min(30.0, eta))
            p = 1 / (1 + _exp(-eta))
            w = p * (1 - p)
            for i in range(k):
                if xi[i]:
                    g[i] += (yi - p) * xi[i]
                    for j in range(k):
                        if xi[j]:
                            H[i][j] += w * xi[i] * xi[j]
        step = _solve(H, g)
        b = [bj + sj for bj, sj in zip(b, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    inv = _inverse(H)
    se = [sqrt(max(inv[i][i], 1e-12)) for i in range(k)]
    return b, se


def predict(b, x):
    eta = max(-30.0, min(30.0, sum(bj * xj for bj, xj in zip(b, x))))
    return 1 / (1 + _exp(-eta))


def wald_p(coef, se):
    return 2 * (1 - _phi(abs(coef) / se)) if se > 0 else 1.0


def _exp(x):
    from math import exp
    return exp(x)


def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-15:
            continue
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                if f:
                    for j in range(c, n + 1):
                        M[r][j] -= f * M[c][j]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-15 else 0.0 for i in range(n)]


def _inverse(A):
    n = len(A)
    cols = [_solve(A, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]
