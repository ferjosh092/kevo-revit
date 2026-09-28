"""Plan de corte en varillas de 9 m por nivel y diametro (best-fit decreasing). Barras > 9 m: 9.00 + (L - 9 + traslape)."""
import pickle, json, collections, sys
sys.path.insert(0, '.')
from q_concreto_lib import nivel_de, partida
M = pickle.load(open('../model_all.pkl', 'rb')); E = M['elements']; B = M['bars']
STOCK = 9.0; TRASL = {'3/4': 1.15}          # traslape sup. 3/4" clase B, lamina E-10 nota 8
piezas = collections.defaultdict(list)       # (nivel, d) -> [(L, id, elemento)]
largas = []
for b in B:
    h = E[b['host']]; niv = nivel_de(h); el = partida(h)
    if b['L'] > STOCK:
        l2 = b['L'] - STOCK + TRASL[b['d']]
        largas.append(dict(id=b['id'], nivel=niv, d=b['d'], L=round(b['L'], 3), p1=STOCK, p2=l2))
        piezas[(niv, b['d'])] += [(STOCK, b['id'] + 'a', el), (l2, b['id'] + 'b', el)]
    else:
        piezas[(niv, b['d'])].append((b['L'], b['id'], el))
plan = []
for (niv, d), P in piezas.items():
    bins = []                                  # [resto, [piezas]]
    for L, i, el in sorted(P, key=lambda x: -x[0]):
        best = None
        for k, bn in enumerate(bins):
            if bn[0] >= L - 1e-9 and (best is None or bn[0] < bins[best][0]): best = k
        if best is None: bins.append([STOCK - L, [(L, i, el)]])
        else: bins[best][0] -= L; bins[best][1].append((L, i, el))
    for k, (r, ps) in enumerate(bins):
        plan.append(dict(nivel=niv, d=d, varilla=k + 1, piezas=[p[0] for p in ps], ids=[p[1] for p in ps],
                         elementos=sorted(set(p[2] for p in ps)), usado=STOCK - r, retazo=r))
json.dump(dict(plan=plan, largas=largas), open('q_corte.json', 'w'))
t = collections.defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])
for p in plan:
    x = t[(p['nivel'], p['d'])]; x[0] += 1; x[1] += len(p['piezas']); x[2] += p['usado']; x[3] += p['retazo']; x[4] += p['retazo'] if p['retazo'] >= 1.0 else 0
tot = collections.defaultdict(lambda: [0, 0.0, 0])
for (n, d), x in sorted(t.items()):
    print(n, d, 'var', x[0], 'piezas', x[1], 'desp%', round(100 * x[3] / (9 * x[0]), 1), 'reutil m', round(x[4], 1))
    tot[d][0] += x[0]; tot[d][1] += x[3]; tot[d][2] += x[1]
for d, v in tot.items(): print(d, 'varillas', v[0], 'piezas', v[2], 'desp%', round(100 * v[1] / (9 * v[0]), 1))
print('largas', len(largas))
