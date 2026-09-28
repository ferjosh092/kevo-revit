"""Acero por nivel y diametro, desde el modelo; corte optimizado en varillas de 9 m (FFD + mejor ajuste). Solo lectura."""
import pickle, json, collections, numpy as np, sys
sys.path.insert(0, '.')
from q_concreto_lib import nivel_de, partida
M = pickle.load(open('../model_all.pkl', 'rb')); E = M['elements']; B = M['bars']
KGM = {'1/4': 0.250, '3/8': 0.560, '1/2': 0.994, '5/8': 1.552, '3/4': 2.235}
STOCK = 9.0; KERF = 0.0
def cut(lengths):
    """Best-fit decreasing. Piezas > 9 m: se reportan aparte (no se cortan de una varilla)."""
    bins = []
    for L in sorted(lengths, reverse=True):
        best = None
        for i, r in enumerate(bins):
            if r >= L + KERF and (best is None or r < bins[best]): best = i
        if best is None: bins.append(STOCK - L - KERF)
        else: bins[best] -= L + KERF
    return bins
rows = []
grp = collections.defaultdict(list)
for b in B:
    h = E[b['host']]
    grp[(nivel_de(h), partida(h), b['d'])].append(b['L'])
json.dump({'|'.join(k): v for k, v in grp.items()}, open('q_acero_piezas.json', 'w'))
out = collections.defaultdict(lambda: dict(n=0, m=0.0, largas=0, var=0, retazo=0.0, reus=0.0))
g2 = collections.defaultdict(list)
for (niv, par, d), Ls in grp.items(): g2[(niv, d)] += Ls
for (niv, d), Ls in g2.items():
    k = (niv, d); o = out[k]
    ok = [L for L in Ls if L <= STOCK]; lg = [L for L in Ls if L > STOCK]
    bins = cut(ok)
    o['n'] += len(Ls); o['m'] += sum(Ls); o['largas'] += len(lg); o['var'] += len(bins)
    o['retazo'] += sum(bins); o['reus'] += sum(r for r in bins if r >= 1.0)
res = []
for (niv, d), o in sorted(out.items()):
    res.append(dict(nivel=niv, d=d, **o, kg=o['m'] * KGM[d]))
json.dump(res, open('q_acero.json', 'w'), indent=1)
