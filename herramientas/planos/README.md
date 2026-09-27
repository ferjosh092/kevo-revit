# Planos estructurales generados desde el IFC

Genera las láminas a partir del modelo IFC exportado de Revit (`Proyect sj.ifc`).
El IFC no se versiona aquí (40 MB).

```bash
pip install ifcopenshell ezdxf shapely pymupdf
# copiar el IFC a src/Proyect sj.ifc (relativo a la carpeta donde se ejecuta)
python extract_cim.py     # datos de cimentación -> cim.json
python extract_mesh.py    # mallas para los cortes -> mesh.pkl
python gen_e01.py         # E-01_Cimentacion.dxf y .pdf
python extract_all.py     # modelo completo -> model_all.pkl (usado por las demás láminas y el visor)
python gen_e02.py; python gen_e03.py; python gen_losas.py; python gen_e08.py; python gen_e09.py; python gen_e10.py
```

- DXF: el espacio modelo está en metros reales; la hoja A1 está en el layout `E-01`
  con ventanas a escala (planta 1:50, zapatas 1:25, viga 1:10, elevaciones 1:50).
- Coordenadas locales alineadas a los ejes: origen en A-1/N-4, X a lo largo de los ejes N.

- `beamdesign.py` coloca el acero longitudinal de vigas en su posición de diseño (el modelo lo tiene
  desplazado por el nodo 12; ver planos/OBSERVACIONES_MODELO.md).
- Visor 3D: `herramientas/visor/build_viewer.py` genera model.bin/model.json para `index.html`.
