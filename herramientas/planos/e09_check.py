"""Verifica recubrimiento del acero de escalera contra el concreto del modelo (piezas convexas)."""
from sheetcommon import *
import collections, itertools
M = load_model()
E = M["elements"]
def halfspaces(el):
    V = np.asarray(el["v"], float); F = np.asarray(el["f"])
    c = V.mean(0); H = []
    for t in F:
        a, b, cc = V[t]
        n = np.cross(b - a, cc - a); L = np.linalg.norm(n)
        if L < 1e-10: continue
        n /= L; d = n @ a
        if n @ c > d: n, d = -n, -d
        if not any(np.allclose(n, h[0], atol=1e-6) and abs(d - h[1]) < 1e-6 for h in H): H.append((n, d))
    return np.array([h[0] for h in H]), np.array([h[1] for h in H])
conc = {}
for t, e in E.items():
    com = e["com"] or ""
    if e["cat"] == "escalera" and "PELDANOS" in com: continue
    if e["cat"] in ("escalera", "columna", "viga", "losa") or (e["cat"] == "zapata"):
        conc[t] = (halfspaces(e), np.asarray(e["bbox"][0]), np.asarray(e["bbox"][1]))
def depth(P):
    """profundidad (m) de cada punto dentro del concreto (max sobre piezas; <0 fuera)"""
    best = np.full(len(P), -1.0)
    lo, hi = P.min(0) - 0.1, P.max(0) + 0.1
    for t, ((N, D), b0, b1) in conc.items():
        if (b1 < lo).any() or (b0 > hi).any(): continue
        dd = (D[None, :] - P @ N.T).min(1)
        best = np.maximum(best, dd)
    return best
dirs = np.array([p for p in itertools.product((-1, 0, 1), repeat=3) if any(p)], float)
dirs /= np.linalg.norm(dirs, axis=1)[:, None]
def cover(P, r):
    """recubrimiento aproximado al exterior de la union de piezas"""
    k = np.zeros(len(P), int)
    inside = depth(P) > 0
    for i in range(1, 16):
        s = 0.0025 * i
        ok = np.ones(len(P), bool)
        for d in dirs:
            ok &= depth(P + d * (r + s)) > 0
        k = np.where(ok & (k == i - 1), i, k)
    cv = k * 0.0025
    return np.where(inside, cv, -1)
if __name__ == "__main__":
    B = [b for b in M["bars"] if b["grp"] == "SJ_ACERO_ESCALERA_R1"]
    res = collections.defaultdict(list)
    for b in B:
        pl = np.asarray(b["pl"], float)
        pts = []
        for a, c in zip(pl[:-1], pl[1:]):
            n = max(2, int(np.linalg.norm(c - a) / 0.02))
            pts += [a + (c - a) * s for s in np.linspace(0, 1, n)]
        P = np.array(pts)
        cv = cover(P, RAD[b["d"]])
        h = E[b["host"]]["com"].split("|", 1)[1]
        i = int(np.argmin(cv))
        res[(h, b["role"].rstrip("0123456789"))].append((round(float(cv.min()), 4), b["role"], np.round(P[i], 3).tolist()))
    for k in sorted(res):
        v = sorted(res[k])
        print(k, "min cover", v[0], " max-of-min", v[-1][0])
