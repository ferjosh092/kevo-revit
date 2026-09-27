"""Correccion del acero de escalera al recubrimiento minimo del proyecto:
  - tramos, descansos y plataformas: 2.5 cm libres;
  - cimiento de arranque: 5 cm libres; 5 mechas centradas en el bloque, traslape 0.45 con el acero superior
    del tramo (detalle fig. 107).
Cada barra conserva su forma: se traslada hacia el interior de la pieza lo necesario en cada cara exterior
(las barras a menos de 7 cm de una cara se mueven juntas, asi las dos capas de la malla no se montan).
El modelo se ajustara despues con el nodo 13; esto solo corrige el dibujo."""
import numpy as np

C_ESC = 0.025
C_CIM = 0.05
ZONA = 0.07
RADM = {"1/4": 0.00318, "3/8": 0.00476, "1/2": 0.00635, "5/8": 0.00794, "3/4": 0.00953}


def _halfspaces(el):
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


def _faces(el):
    """caras planas de la pieza: (normal exterior, d, centroide aproximado)"""
    V = np.asarray(el["v"], float)
    N, D = _halfspaces(el)
    out = []
    for n, d in zip(N, D):
        on = np.abs(V @ n - d) < 1e-5
        out.append((n, d, V[on].mean(0) if on.any() else V.mean(0)))
    return out


def correct(M):
    E = M["elements"]
    conc = {}
    for t, e in E.items():
        if e["cat"] == "escalera" and "PELDANOS" in (e["com"] or ""):
            continue
        if e["cat"] in ("escalera", "columna", "viga", "losa", "zapata"):
            conc[t] = (_halfspaces(e), np.asarray(e["bbox"][0]), np.asarray(e["bbox"][1]))

    def depth_excl(P, excl=None):
        best = np.full(len(P), -1.0)
        for t, ((N, D), b0, b1) in conc.items():
            if t == excl:
                continue
            if (b1 < P.min(0) - 0.1).any() or (b0 > P.max(0) + 0.1).any():
                continue
            best = np.maximum(best, (D[None, :] - P @ N.T).min(1))
        return best

    cim = [t for t, e in E.items() if e["tipo"] == "CIM_ESCALERA_ARRANQUE_R1"][0]
    pieces = [t for t, e in E.items() if e["cat"] == "escalera" and "PELDANOS" not in (e["com"] or "")] + [cim]
    faces = {}
    for t in pieces:
        fl = []
        for n, d, c in _faces(E[t]):
            ext = depth_excl(np.array([c + n * 0.01]), excl=t)[0] <= 0 and depth_excl(np.array([c + n * 0.01]))[0] <= 0
            if ext:
                fl.append((n, d))
        faces[t] = fl

    def piece_of(p):
        best, bt = 0.0, None
        for t in pieces:
            (N, D), b0, b1 = conc[t]
            dd = (D - N @ p).min()
            if dd > best:
                best, bt = dd, t
        return bt

    SB = [b for b in M["bars"] if b["grp"] == "SJ_ACERO_ESCALERA_R1" and not b["role"].startswith("MECHA")]

    def densify(pl, step=0.02):
        out = [pl[0]]
        for a_, c_ in zip(pl[:-1], pl[1:]):
            n = max(1, int(np.ceil(np.linalg.norm(c_ - a_) / step)))
            out += [a_ + (c_ - a_) * s_ for s_ in np.linspace(0, 1, n + 1)[1:]]
        return np.array(out)

    out = []
    moved = {}
    for b in M["bars"]:
        if b["grp"] == "SJ_ACERO_ESCALERA_R1" and b["role"].startswith("MECHA"):
            continue                      # se reemplazan por las 5 mechas corregidas
        if b["grp"] != "SJ_ACERO_ESCALERA_R1":
            out.append(b)
            continue
        r = RADM[b["d"]]
        P = densify(np.asarray(b["pl"], float))
        Q = P.copy()
        for k, p in enumerate(P):
            if piece_of(p) is None:
                continue                  # punto en el vacio del modelo (nudo J1): no se corrige
            for _ in range(2):
                for t in pieces:
                    (N, D), b0, b1 = conc[t]
                    if (Q[k] < b0 - 0.06).any() or (Q[k] > b1 + 0.06).any():
                        continue
                    c = C_CIM if t == cim else C_ESC
                    for n, d in faces[t]:
                        dist = d - n @ Q[k]
                        if dist < -0.001 or dist >= c + r:
                            continue
                        proj = Q[k] + n * dist
                        others = D - N @ proj
                        if (others < -0.002).any():
                            continue      # la proyeccion cae fuera de la cara
                        Q[k] -= n * (c + r - dist)
        mv = float(np.abs(Q - P).max())
        if mv > 1e-4:
            # simplificar: quitar puntos alineados
            keep = [0]
            for k in range(1, len(Q) - 1):
                a_, b_, c_ = Q[keep[-1]], Q[k], Q[k + 1]
                u1, u2 = b_ - a_, c_ - b_
                if np.linalg.norm(np.cross(u1, u2)) > 1e-6 * max(np.linalg.norm(u1) * np.linalg.norm(u2), 1e-12) * 50:
                    keep.append(k)
            keep.append(len(Q) - 1)
            nb = dict(b, pl=Q[keep], corregida=True)
            moved[b["id"]] = mv
        else:
            nb = b
        out.append(nb)

    # pasada final: medir el recubrimiento real (a la union de todo el concreto) y empujar los puntos que no cumplen
    import stair_cover as SC
    (Ncim, Dcim) = _halfspaces(E[cim])
    for j, b in enumerate(out):
        if b["grp"] != "SJ_ACERO_ESCALERA_R1":
            continue
        r = RADM[b["d"]]
        Q = densify(np.asarray(b["pl"], float))
        changed = False
        for it in range(4):
            cv, dm = SC.cover(Q, r)
            incim = (Dcim[None, :] - Q @ Ncim.T).min(1) > 0
            req = np.where(incim, C_CIM, C_ESC) + 0.0006
            bad = (cv >= 0) & (cv < req)
            if not bad.any():
                break
            Q[bad] -= dm[bad] * (req[bad] - cv[bad] + 0.001)[:, None]
            changed = True
        if changed:
            keep = [0]
            for k in range(1, len(Q) - 1):
                a_, b_, c_ = Q[keep[-1]], Q[k], Q[k + 1]
                u1, u2 = b_ - a_, c_ - b_
                if np.linalg.norm(np.cross(u1, u2)) > 5e-5 * max(np.linalg.norm(u1) * np.linalg.norm(u2), 1e-12):
                    keep.append(k)
            keep.append(len(Q) - 1)
            out[j] = dict(b, pl=Q[keep], corregida=True)
            moved[b["id"]] = max(moved.get(b["id"], 0.0), 0.001)

    # mechas: 5, centradas en el bloque
    mech = sorted([b for b in M["bars"] if b["host"] == cim and b["role"].startswith("MECHA")], key=lambda b: b["role"])
    tmpl = np.asarray(mech[0]["pl"], float)
    b0, b1 = E[cim]["bbox"]
    vc = (b0[1] + b1[1]) / 2
    # linea del acero superior del tramo 1 (N1-N2) en el plano (u, z), ya corregida
    t1 = [t for t in pieces if (E[t]["com"] or "").endswith("|N1-N2|LOSA_T1")][0]
    S1 = [nb for nb in out if nb.get("host") == t1 and nb["role"].startswith("S")]
    sp = np.asarray(min(S1, key=lambda b: abs(np.asarray(b["pl"])[:, 1].mean() - vc))["pl"], float)
    i0 = int(np.argmin(sp[:, 0]))
    s0 = sp[i0]
    s1 = sp[i0 + 1] if i0 + 1 < len(sp) else sp[i0 - 1]
    dd = (s1[[0, 2]] - s0[[0, 2]])
    dd /= np.linalg.norm(dd)
    u_v = E[t1]["bbox"][0][0] + C_CIM + RADM["3/8"] + 0.005      # rama vertical bajo el arranque del tramo
    z_b = s0[2] + (u_v - s0[0]) * dd[1] / dd[0]
    e_ = s0[[0, 2]] + 0.45 * dd
    z_bot = b0[2] + 0.10
    tr_v0, tr_v1 = E[t1]["bbox"][0][1], E[t1]["bbox"][1][1]
    lo = max(b0[1] + C_CIM, tr_v0 + C_ESC) + RADM["3/8"]
    hi = min(b1[1] - C_CIM, tr_v1 - C_ESC) - RADM["3/8"]
    half = min(vc - lo, hi - vc)
    sep = min(0.20, 2 * half / 4)
    vs = [vc + (i - 2) * sep for i in range(5)]
    for k, v in enumerate(vs):
        pl = np.array([[u_v, v, z_bot], [u_v, v, z_b], [e_[0], v, e_[1]]])
        L = float(np.linalg.norm(pl[1] - pl[0]) + np.linalg.norm(pl[2] - pl[1]))
        out.append(dict(mech[0], id=f"MECHA-{k + 1}", role=f"MECHA_SUP{k + 1}", pl=pl, L=L,
                        segs=[float(pl[1, 2] - pl[0, 2]), float(np.linalg.norm(pl[2] - pl[1])), None, None, None, None],
                        corregida=True, nueva=True))
    info = {"moved": moved, "mechas_modelo": [b["id"] for b in mech], "mechas_v": vs, "mecha_sep": sep,
            "mecha_u": u_v, "mecha_zb": z_b, "mecha_top": e_.tolist(), "lap": 0.45}
    return out, info


if __name__ == "__main__":
    from sheetcommon import load_model
    import json
    M = load_model()
    bars, info = correct(M)
    print(len(info["moved"]), "barras trasladadas; mechas v =", np.round(info["mechas_v"], 3), "sep", info["mecha_sep"],
          "u", round(info["mecha_u"], 3))
    json.dump({"moved": info["moved"]}, open("stair_moved.json", "w"))


def load_corrected(M, cache="stair_fixed.pkl"):
    """acero de escalera corregido (con cache: la pasada de verificacion tarda varios minutos)."""
    import os, pickle
    if os.path.exists(cache):
        esc, info = pickle.load(open(cache, "rb"))
    else:
        bars, info = correct(M)
        esc = [b for b in bars if b["grp"] == "SJ_ACERO_ESCALERA_R1"]
        pickle.dump((esc, info), open(cache, "wb"))
    out = [b for b in M["bars"] if b["grp"] != "SJ_ACERO_ESCALERA_R1"] + esc
    return out, info
