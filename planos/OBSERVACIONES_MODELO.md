# Observaciones del modelo IFC (Proyect sj.ifc)

Revisión automática del modelo exportado de Revit 2027. Los planos E-01 a E-10 dibujan la
geometría y el acero tal como están en el modelo, **salvo** el acero longitudinal de vigas
(punto 1), que se dibuja en su posición de diseño.

## 1. Acero longitudinal de vigas desplazado hacia el interior (nodo 12) — CRÍTICO

El buscador de posiciones libres de choque del nodo 12 baja o sube la capa completa cuando una
barra choca en algún punto del eje, y si no encuentra lugar la manda a la 3ra o 4ta capa
(`z0 = z_base - (0, .058, .145, .203)[ic]`). Resultado medido en el IFC (544 barras):

| Vigas | Capa | Desplazamiento hacia el interior |
|---|---|---|
| Cimentación 0.25x0.40 | 1ra (C1) | 1.6 – 3.6 cm |
| Cimentación 0.25x0.40 | siguientes (C2–C5) | 5.8 – 23.1 cm |
| Entrepiso 0.30x0.50 | 1ra (C1) | 2.1 – 5.7 cm |
| Entrepiso 0.30x0.50, superiores | C4–C5 | 22.5 – 25.3 cm (acero superior a media altura) |

Peor caso: vigas del eje A (N-1 a N-3) en Nivel 2, barras superiores 25.3 cm bajo su posición.
Con eso el peralte efectivo de la viga cae casi a la mitad.

**Corrección sugerida en el nodo 12:** fijar la cota de cada capa en su valor de diseño
(1ra capa a r + Ø estribo + db/2 de la cara; 2da capa a 5.8 cm entre centros) y resolver los
cruces solo con desplazamiento lateral y, en el nudo, pasando las barras de los ejes A una capa
por dentro de las de los ejes N únicamente dentro de la columna (bayoneta), no en todo el eje.

## 2. Losas

- La losa se modela maciza de 0.20 **por criterio**: el aligerado (bloque 0.15 + losita 0.05, viguetas
  0.10 @ 0.40) se representa con su acero y el concreto se metra aparte. En E-04 a E-07 se dibuja como
  aligerada, con el sentido de viguetas tomado del acero del modelo (VIG_* en X; LAT_* en Y en las franjas
  laterales con viga chata 0.30 x 0.20) y la zona maciza e = 0.15 de la plataforma de llegada de la escalera.
- Malla de temperatura Ø1/4" a la misma cota que bastones y barras superiores: ~5 mm de interferencia en
  cruces (se resuelve en obra apoyando la malla sobre los bastones).
- Viga chata VCH: barras superiores 3.3 cm bajo la esquina del estribo; una barra cruza la rama del estribo
  (5.8 mm) en Niveles 2 y 5.

## 3. Límite de propiedad

Las zapatas Z-1 del eje N-4 (hasta v = -0.60) y las columnas de escalera (hasta -0.15) quedan
fuera de la línea de propiedad del modelo (v ≈ 0.03–0.39). Verificar con el levantamiento.

## 4. Escalera — recubrimientos (nodo 13)

Mínimo de proyecto: 2.5 cm en tramos, descansos y plataformas; 5 cm en el cimiento de arranque.
En el modelo el acero de escalera tiene 2.0 cm libres en casi todas las barras (83 de 86 en N1-N2, 75 de 76
en cada piso típico) y 1.1–1.3 cm en las patas superiores del tramo 1 y en las barras de borde del descanso
y la plataforma de N1-N2. Las 6 mechas del cimiento tienen 2.2 cm al tope del bloque y la extrema (id 228658)
queda sin recubrimiento lateral. Lista completa: `ESCALERA_RECUBRIMIENTOS.csv`.

En E-09 (y E-01) el acero se dibuja corregido y las mechas se reemplazan por 5 centradas @ 0.20, a ≥ 5 cm de
las caras, con traslape de 0.45 con el acero superior del tramo ("corregir posición de mechas según detalle").
El modelo se ajustará con el nodo 13. Los anclajes del tramo 2 atraviesan un vacío de 5 cm del modelo bajo la
plataforma (nudo J1) en todos los pisos: en obra se vacía monolítico.

## 5. Otros

- Revit exporta el peso del acero en 0; los pesos de las láminas se calculan con la longitud de
  cada barra y el peso nominal por metro.
- Las barras de un conjunto se exportan como entidades separadas pero con la cantidad y longitud
  total del conjunto copiadas; sumar esos campos directamente da ~522 t en vez de 18.8 t.
- f'c no está en el modelo; se tomó de la especificación del proyecto: 210 kg/cm² en elementos
  estructurales, 175 en falso piso y 100 en solados (fy = 4200 kg/cm²).
