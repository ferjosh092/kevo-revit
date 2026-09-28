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

