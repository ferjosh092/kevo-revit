"""Posicion de DISENO del acero longitudinal de vigas (E.060), segun las reglas del nodo 12.

El modelo IFC tiene las cantidades, diametros, longitudes, traslapes y ganchos correctos, pero el
buscador de posiciones libres de choque del nodo 12 desplazo verticalmente muchas capas (hasta 25 cm
hacia el interior). Este modulo conserva cada barra tal cual (planta, largo, traslapes, ganchos) y solo
la traslada a su capa y posicion lateral de diseno:
  - 1ra capa: recubrimiento 4 cm + estribo 3/8" + db/2 desde la cara.
  - 2da capa: 5.8 cm entre centros hacia el interior (db + 2.5 cm libres + 1.4 cm, como el nodo 12).
  - reparto lateral uniforme; la 2da capa usa las posiciones extremas de la 1ra.
  - capas: layer_split del nodo 12 (maximo de barras por capa con 2.5 cm libres).
"""
import math, re, collections
import numpy as np

COVER = 0.04
D38 = 0.009525
LIBRE = 0.025
SEG_CAPA = 0.058


def layer_split(n, inner, db):
    paso = db + max(LIBRE, db)
    cap = int(math.floor((inner + 1e-9) / paso)) + 1
    if n <= cap:
        return [n]
    l1 = min(int(math.ceil(n / 2.0)), cap)
    return [l1, n - l1]


def lateral_positions(n_layer, n_ref, half):
    grid = [0.0] if n_ref == 1 else [-half + 2.0 * half * i / float(n_ref - 1) for i in range(n_ref)]
    if n_layer >= n_ref:
        return grid
    idx, lo, hi = [], 0, n_ref - 1
    while len(idx) < n_layer:
        idx.append(lo)
        if len(idx) < n_layer:
            idx.append(hi)
        lo += 1
        hi -= 1
    return sorted(grid[i] for i in idx)


def line_of(com):
    """eje de la viga a partir del comentario: 'N-1-A-1-N-1-A-4' -> 'N-1'; 'N-1-A-2-N-2-A-2' -> 'A-2'."""
    m = re.search(r"(N-\d)-(A-\d)-(N-\d)-(A-\d)", com)
    if not m:
        return None
    n1, a1, n2, a2 = m.groups()
    return n1 if n1 == n2 else a1


def beam_info(el):
    ps = el["psets"]
    b = ps["Cotas"]["b"]
    h = ps["Cotas"]["h"]
    top = ps["Cotas"]["Elevación en parte superior"]
    bot = ps["Cotas"]["Elevación en parte inferior"]
    v = el["v"]
    horiz = np.ptp(v[:, 0]) > np.ptp(v[:, 1])
    return {"b": b, "h": h, "top": top, "bot": bot, "horiz": horiz,
            "c_lat": float((v[:, 1].min() + v[:, 1].max()) / 2 if horiz else (v[:, 0].min() + v[:, 0].max()) / 2)}


def runs(model):
    """agrupa las vigas por (nivel, eje, tipo)"""
    out = collections.defaultdict(list)
    for tag, el in model["elements"].items():
        if el["cat"] != "viga":
            continue
        ln = line_of(el["com"])
        if "COLLARIN" in el["com"]:
            ln = "COLL-" + el["level"]
        out[(el["level"], ln, el["tipo"])].append(tag)
    return out


def design_positions(model):
    """devuelve {bar_id: dict(dz, dlat, capa, t, z)} para las barras SUP/INF de vigas."""
    els = model["elements"]
    by_host = collections.defaultdict(list)
    for b in model["bars"]:
        if b["grp"] == "SJ_ACERO_VIGAS_R1" and b["role"] in ("SUP", "INF"):
            by_host[b["host"]].append(b)
    res = {}
    for key, tags in runs(model).items():
        info = beam_info(els[tags[0]])
        for role in ("SUP", "INF"):
            bl = [b for t in tags for b in by_host.get(t, []) if b["role"] == role]
            if not bl:
                continue
            bidx = sorted({b["rest"][1] for b in bl}, key=lambda s: int(s[1:]))
            n = len(bidx)
            db = bl[0]["db"]
            inner = info["b"] - 2 * (COVER + D38) - db
            half = inner / 2.0
            capas = layer_split(n, inner, db)
            z1 = (info["top"] - COVER - D38 - db / 2) if role == "SUP" else (info["bot"] + COVER + D38 + db / 2)
            sg = -1 if role == "SUP" else 1
            slot = {}
            k = 0
            for ic, nl in enumerate(capas):
                ts = lateral_positions(nl, capas[0], half)
                for t in ts:
                    slot[bidx[k]] = (ic, t, z1 + sg * ic * SEG_CAPA)
                    k += 1
            for b in bl:
                ic, t, z = slot[b["rest"][1]]
                pl = np.asarray(b["pl"], float)
                # tramo recto mas largo = cota y posicion lateral actuales
                i = max(range(len(pl) - 1), key=lambda j: np.linalg.norm(pl[j + 1, :2] - pl[j, :2]))
                zc = (pl[i, 2] + pl[i + 1, 2]) / 2
                lat_ax = 1 if info["horiz"] else 0
                latc = (pl[i, lat_ax] + pl[i + 1, lat_ax]) / 2
                # en la pieza B de un traslape el tramo recto largo esta a su cota; la bayoneta se conserva
                res[b["id"]] = {"dz": z - zc, "dlat": (info["c_lat"] + t) - latc, "lat_ax": lat_ax, "capa": ic + 1,
                                "t": t, "z": z, "n": n, "capas": capas, "run": key}
    return res


def corrected_bars(model):
    """copia de model['bars'] con las barras longitudinales de vigas en su posicion de diseno."""
    pos = design_positions(model)
    out = []
    for b in model["bars"]:
        p = pos.get(b["id"])
        if p is None:
            out.append(b)
            continue
        nb = dict(b)
        pl = np.array(b["pl"], float)
        pl[:, 2] += p["dz"]
        pl[:, p["lat_ax"]] += p["dlat"]
        nb["pl"] = pl
        nb["design"] = p
        out.append(nb)
    return out, pos


if __name__ == "__main__":
    import pickle
    m = pickle.load(open("model_all.pkl", "rb"))
    bars, pos = corrected_bars(m)
    dz = np.array([abs(p["dz"]) for p in pos.values()]) * 100
    print("barras corregidas", len(pos), "desplazamiento vertical cm: med %.1f max %.1f" % (np.median(dz), dz.max()))
    summ = collections.Counter((p["run"][0], p["run"][1], tuple(p["capas"])) for p in pos.values())
    for k, v in sorted(summ.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        print(k, v)
