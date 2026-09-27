"""QA del acero de losas (por nivel): barras fuera de la huella, recubrimientos, interferencias (penetracion > 2 mm)
con el acero de vigas/columnas y entre barras de la propia losa. Solo lectura."""
from sheetcommon import *
import re, collections, sys
from shapely.geometry import Point
import os
M = load_model(design=os.environ.get("DESIGN","1")=="1"); E = M["elements"]

def segs(blist):
    out = []
    for k, b in enumerate(blist):
        pl = np.asarray(b["pl"], float)
        for i in range(len(pl) - 1):
            out.append((pl[i], pl[i + 1], b["db"] / 2, k))
    return out

def sd(p1, q1, p2, q2):
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1 @ d1, d2 @ d2, d2 @ r
    c, b = d1 @ r, d1 @ d2
    den = a * e - b * b
    s = np.clip((b * f - c * e) / den, 0, 1) if den > 1e-12 else 0.0
    t = (b * s + f) / e if e > 1e-12 else 0.0
    if t < 0: t, s = 0.0, np.clip(-c / a, 0, 1) if a > 1e-12 else 0
    elif t > 1: t, s = 1.0, np.clip((b - c) / a, 0, 1) if a > 1e-12 else 0
    return np.linalg.norm((p1 + d1 * s) - (p2 + d2 * t))

def clashes(A, B, same=False, tol=0.002):
    res = []
    bbB = [(np.minimum(p, q) - rr, np.maximum(p, q) + rr) for p, q, rr, _ in B]
    lo = np.array([x[0] for x in bbB]); hi = np.array([x[1] for x in bbB])
    for i, (p, q, r, k) in enumerate(A):
        l1, h1 = np.minimum(p, q) - r, np.maximum(p, q) + r
        cand = np.nonzero(np.all(lo <= h1, 1) & np.all(hi >= l1, 1))[0]
        for j in cand:
            p2, q2, r2, k2 = B[j]
            if same and k2 <= k: continue
            d = sd(p, q, p2, q2)
            pen = r + r2 - d
            if pen > tol:
                res.append((k, k2, pen))
    return res

levels = sys.argv[1:] or ["Nivel 2", "Nivel 3", "Nivel 4", "Nivel 5"]
for lv in levels:
    slab = [t for t, e in E.items() if e["cat"] == "losa" and e["level"] == lv][0]
    el = E[slab]; zb, zt = el["bbox"][0][2], el["bbox"][1][2]
    fp = footprint(el)
    LB = [b for b in M["bars"] if b["grp"] == "SJ_ACERO_LOSAS_R1" and b["host"] == slab]
    out = []
    for b in LB:
        pl = np.asarray(b["pl"], float)
        dout = max((fp.exterior.distance(Point(p[:2])) if not fp.buffer(1e-4).contains(Point(p[:2])) else 0) for p in pl)
        cz = min(pl[:, 2].min() - zb, zt - pl[:, 2].max()) - b["db"] / 2
        cxy = min(fp.exterior.distance(Point(p[:2])) for p in pl) - b["db"] / 2
        if dout > 0.001 or cz < 0.015 or cxy < 0.015:
            out.append((b["role"], b["d"], round(dout, 3), round(cz, 3), round(cxy, 3)))
    print(f"== {lv}: {len(LB)} barras; fuera/recubr<1.5cm: {len(out)}", collections.Counter((re.sub(r'\d+$', '', o[0]), 'fuera' if o[2] > 0.001 else ('rz' if o[3] < 0.015 else 'rxy')) for o in out))
    for o in out[:8]: print("    ", o)
    hosts = [t for t, e in E.items() if e["cat"] in ("viga", "columna") and e["bbox"][0][2] < zt + 0.05 and e["bbox"][1][2] > zb - 0.6]
    OB = [b for b in M["bars"] if b["host"] in hosts]
    c1 = clashes(segs(LB), segs(OB))
    agg = collections.defaultdict(float); cnt = collections.Counter()
    for k, k2, pen in c1:
        key = (re.sub(r'\d+$', '', LB[k]["role"]), OB[k2]["role"], E[OB[k2]["host"]]["cat"])
        agg[key] = max(agg[key], pen); cnt[key] += 1
    print("   interferencias losa vs viga/columna (seg-pares, max penetracion mm):", {k: (cnt[k], round(v * 1000, 1)) for k, v in agg.items()})
    S = segs(LB)
    c2 = clashes(S, S, same=True)
    agg = collections.defaultdict(float); cnt = collections.Counter()
    for k, k2, pen in c2:
        if k == k2: continue
        key = tuple(sorted((re.sub(r'\d+$', '', LB[k]["role"]), re.sub(r'\d+$', '', LB[k2]["role"]))))
        agg[key] = max(agg[key], pen); cnt[key] += 1
    print("   interferencias internas losa:", {k: (cnt[k], round(v * 1000, 1)) for k, v in agg.items()})
