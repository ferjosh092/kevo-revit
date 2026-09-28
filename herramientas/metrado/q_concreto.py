"""Metrado de concreto y encofrado por elemento, leido del IFC (model_all.pkl). Solo lectura."""
import pickle, json, collections, numpy as np, trimesh, sys
M = pickle.load(open('../model_all.pkl', 'rb')); E = M['elements']

def nivel_de(e):
    c = e['com'] or ''; cat = e['cat']; lv = e['level']
    if cat == 'zapata': return 'CIMENTACION'
    if cat == 'viga': return 'CIMENTACION' if lv == 'Cimentacion' else lv.upper().replace('NIVEL ', 'NIVEL ')
    if cat == 'columna':
        top = c.split('|')[-1].split('-')[-1]            # 'Nivel 2'
        return top.upper()
    if cat == 'losa': return lv.upper()
    if cat == 'falsopiso': return 'NIVEL 1'
    if cat == 'escalera':
        seg = c.split('|')[1]                              # N1-N2
        return 'NIVEL ' + seg.split('-')[1][1:]
    return '?'

def partida(e):
    c = e['com'] or ''; cat = e['cat']
    if cat == 'zapata': return 'Cimiento de escalera' if 'CIMIENTO_ESCALERA' in c else 'Zapatas'
    if cat == 'viga':
        if e['level'] == 'Cimentacion': return 'Vigas de conexion'
        return 'Vigas'
    if cat == 'columna': return 'Columnas'
    if cat == 'losa': return 'Losa'
    if cat == 'falsopiso': return 'Falso piso'
    if cat == 'escalera': return 'Escalera'

conc = {}
for t, e in E.items():
    V = np.asarray(e['v'], float); F = np.asarray(e['f'])
    if len(F) == 0: continue
    m = trimesh.Trimesh(V, F, process=True)
    conc[t] = m
print('watertight', sum(m.is_watertight for m in conc.values()), '/', len(conc), file=sys.stderr)
ids = list(conc)
bbs = {t: conc[t].bounds for t in ids}

def inside_any(P, own):
    res = np.zeros(len(P), bool)
    lo, hi = P.min(0) - 0.05, P.max(0) + 0.05
    for t in ids:
        if t == own: continue
        b = bbs[t]
        if (b[1] < lo).any() or (b[0] > hi).any(): continue
        if E[t]['cat'] == 'escalera' and 'PELDANOS' in (E[t]['com'] or '') and E[own]['cat'] != 'escalera': pass
        r = conc[t].contains(P)
        res |= r
    return res

GROUND = {'zapata', 'falsopiso'}
out = []
for t in ids:
    e = E[t]; m0 = conc[t]
    v2, f2 = trimesh.remesh.subdivide_to_size(m0.vertices, m0.faces, max_edge=0.08)
    m = trimesh.Trimesh(v2, f2, process=False)
    cat = e['cat']; c = e['com'] or ''
    n = m.face_normals; A = m.area_faces; C = m.triangles_center
    probe = C + n * 0.015
    touch = inside_any(probe, t)
    nz = n[:, 2]
    top = nz > 0.7; bot = nz < -0.7; side = ~top & ~bot
    free = ~touch
    # encofrado segun tipo de elemento
    f_side = f_bot = 0.0
    zmin = m.bounds[0][2]
    if cat == 'zapata':
        f_side = A[side & free].sum()          # opcional (vaciado contra terreno)
    elif cat == 'viga' and e['level'] == 'Cimentacion':
        f_side = A[side & free].sum()          # VC: costados; fondo sobre solado/terreno
    elif cat == 'falsopiso':
        pass
    elif cat == 'columna':
        f_side = A[side & free].sum()
    elif cat in ('viga', 'losa'):
        f_side = A[side & free].sum(); f_bot = A[bot & free].sum()
    elif cat == 'escalera':
        low = A[(nz < -0.3) & free].sum()      # fondo de tramos, descansos, plataforma (inclinado u horizontal)
        f_bot = low
        f_side = A[side & free & ~(nz < -0.3)].sum()   # costados, contrapasos
    out.append(dict(id=t, nivel=nivel_de(e), partida=partida(e), tipo=e['tipo'], com=c,
                    vol=float(abs(m0.volume)), enc_lat=float(f_side), enc_fondo=float(f_bot),
                    area_planta=float(A[top].sum()), sup_libre=float(A[top & free].sum()), lat_libre_total=float(A[side & free].sum()), cat=cat))
json.dump(out, open('q_concreto.json', 'w'), indent=1)
tab = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])
for r in out:
    k = (r['nivel'], r['partida']); tab[k][0] += 1; tab[k][1] += r['vol']; tab[k][2] += r['enc_lat']; tab[k][3] += r['enc_fondo']
for k in sorted(tab): print(k, tab[k][0], [round(x, 2) for x in tab[k][1:]])
print('TOTAL vol', round(sum(r['vol'] for r in out), 2))
