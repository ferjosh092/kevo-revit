import json, collections, re
from stair_cover import *          # cover(), depth(), M, E
from stair_fix import correct
bars, info = correct(M)
cimtag = [t for t, e in E.items() if e["tipo"] == "CIM_ESCALERA_ARRANQUE_R1"][0]
(Nc, Dc) = __import__("stair_fix")._halfspaces(E[cimtag])
res = {}
for b in bars:
    if b["grp"] != "SJ_ACERO_ESCALERA_R1":
        continue
    pl = np.asarray(b["pl"], float)
    pts = []
    for a, c in zip(pl[:-1], pl[1:]):
        n = max(2, int(np.linalg.norm(c - a) / 0.03))
        pts += [a + (c - a) * s for s in np.linspace(0, 1, n)]
    P = np.array(pts)
    cv, dm = cover(P, RAD[b["d"]])
    incim = (Dc[None, :] - P @ Nc.T).min(1) > 0
    req = np.where(incim, 0.0495, 0.0245)
    bad = (cv < req) & (cv >= 0)
    void = cv < 0
    host = E[b["host"]]
    piso = "N1-N2" if host["cat"] == "zapata" else host["com"].split("|")[1]
    res[b["id"]] = {"piso": piso, "role": b["role"], "min_ok": bool(not bad.any()), "void": bool(void.any()),
                    "cmin": round(float(cv[cv >= 0].min()) if (cv >= 0).any() else -1, 4)}
json.dump(res, open("stair_verify.json", "w"))
c = collections.Counter((v["piso"], v["min_ok"], v["void"]) for v in res.values())
print(sorted(c.items()))
print([ (k, v) for k, v in res.items() if not v["min_ok"]][:20])
