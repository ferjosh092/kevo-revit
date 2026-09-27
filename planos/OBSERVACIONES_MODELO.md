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

- Modeladas como piso macizo de 0.20 (`PISO_ESTRUCTURAL_MACIZO_200mm_VOLADO`); los casetones no
  están modelados. El volumen de concreto del modelo (73.9 m³) no representa el aligerado
  (≈ 32.3 m³ estimado con 0.0875 m³/m²).
- Las viguetas principales van paralelas a los ejes N (apoyadas en A-1/A-4/A-2/A-3); el
  docstring del nodo 14 dice "paralelas a los ejes A". Los planos dibujan lo modelado.
- Malla de temperatura Ø1/4" a la misma cota que bastones y barras superiores: ~5 mm de
  interferencia en cientos de cruces.
- Viga chata VCH: barras superiores 3.3 cm bajo la esquina del estribo; una barra cruza la rama
  del estribo (5.8 mm) en Niveles 2 y 5.
- Diferencias puntuales entre niveles (barras L2 rectas en Nivel 3, LAT_SUPR25 recta en Nivel 2,
  pieza de VCH 4.4 cm más baja en Niveles 3 y 4).
- TEMP_U43/44 prácticamente sobre el borde inclinado A-1 (recubrimiento lateral ~0).

## 3. Límite de propiedad

Las zapatas Z-1 del eje N-4 (hasta v = -0.60) y las columnas de escalera (hasta -0.15) quedan
fuera de la línea de propiedad del modelo (v ≈ 0.03–0.39). Verificar con el levantamiento.

## 4. Otros

- Revit exporta el peso del acero en 0; los pesos de las láminas se calculan con la longitud de
  cada barra y el peso nominal por metro.
- Las barras de un conjunto se exportan como entidades separadas pero con la cantidad y longitud
  total del conjunto copiadas; sumar esos campos directamente da ~522 t en vez de 18.8 t.
- f'c no está en el modelo; se tomó de la especificación del proyecto: 210 kg/cm² en elementos
  estructurales, 175 en falso piso y 100 en solados (fy = 4200 kg/cm²).
