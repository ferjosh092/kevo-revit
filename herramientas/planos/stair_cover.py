"""Recubrimiento libre de cada barra de la escalera contra el concreto del modelo (resolucion 1 mm).
Salida: stair_cover.json  {bar_id: {piso, pieza, role, d, cover_min, punto, dir_falla}}"""
import itertools, json
from sheetcommon import *

M = load_model(design=False)
E = M["elements"]


def halfspaces(el):
    V = np.asarray(el["v"], float)
    F = np.asarray(el["f"])
    c = V.mean(0)
    H = []
    for t in F:
        a, b, cc = V[t]
        n = np.cross(b - a, cc - a)
        L = np.linalg.norm(n)
        if L < 1e-10:
            continue
        n /= L
        d = n @ a
        if n @ c > d:
            n, d = -n, -d
        if not any(np.allclose(n, h[0], atol=1e-6) and abs(d - h[1]) < 1e-6 for h in H):
            H.append((n, d))
    return np.array([h[0] for h in H]), np.array([h[1] for h in H])


conc = {}
for t, e in E.items():
    if e["cat"] == "escalera" and "PELDANOS" in (e["com"] or ""):
        continue
    if e["cat"] in ("escalera", "columna", "viga", "losa", "zapata"):
        conc[t] = (halfspaces(e), np.asarray(e["bbox"][0]), np.asarray(e["bbox"][1]))


def depth(P):
    best = np.full(len(P), -1.0)
    lo, hi = P.min(0) - 0.1, P.max(0) + 0.1
    for t, ((N, D), b0, b1) in conc.items():
        if (b1 < lo).any() or (b0 > hi).any():
            continue
        best = np.maximum(best, (D[None, :] - P @ N.T).min(1))
    return best


DIRS = np.array([p for p in itertools.product((-1, 0, 1), repeat=3) if any(p)], float)
DIRS /= np.linalg.norm(DIRS, axis=1)[:, None]


def cover(P, r, maxc=0.06):
    """recubrimiento libre en cada punto (m) y la direccion que lo limita"""
    cv = np.full(len(P), maxc)
    dmin = np.zeros((len(P), 3))
    for d in DIRS:
        # distancia a la superficie en la direccion d, por pasos de 1 mm
        free = np.full(len(P), maxc)
        found = np.zeros(len(P), bool)
        for s in np.arange(0.0, maxc + 1e-9, 0.001):
            out = depth(P + d * (r + s)) <= 0
            new = out & ~found
            free[new] = s
            found |= out
            if found.all():
                break
        upd = free < cv
        cv[upd] = free[upd]
        dmin[upd] = d
    cv[depth(P) <= 0] = -0.001
    return cv, dmin


if __name__ == "__main__":
    B = [b for b in M["bars"] if b["grp"] == "SJ_ACERO_ESCALERA_R1"]
    out = {}
    for b in B:
        pl = np.asarray(b["pl"], float)
        pts = []
        for a, c in zip(pl[:-1], pl[1:]):
            n = max(2, int(np.linalg.norm(c - a) / 0.03))
            pts += [a + (c - a) * s for s in np.linspace(0, 1, n)]
        P = np.array(pts)
        cv, dm = cover(P, RAD[b["d"]])
        i = int(np.argmin(cv))
        host = E[b["host"]]
        piso, pieza = (host["com"].split("|")[1:3] + ["", ""])[:2]
        if host["cat"] == "zapata":
            piso, pieza = "N1-N2", "CIMIENTO"
        out[b["id"]] = {"piso": piso, "pieza": pieza, "role": b["role"], "d": b["d"], "cover_min": round(float(cv[i]), 4),
                        "punto": np.round(P[i], 3).tolist(), "dir": np.round(dm[i], 2).tolist(),
                        "n_bajo_25": int((cv < 0.0245).sum()), "n_pts": len(P)}
    json.dump(out, open("stair_cover.json", "w"), indent=1)
    import collections
    c = collections.Counter((v["piso"], v["cover_min"] < 0.0245) for v in out.values())
    print(sorted(c.items()))
