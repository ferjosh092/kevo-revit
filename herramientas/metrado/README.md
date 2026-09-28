# Metrado de materiales del casco (solo lectura del IFC)

1. `python ../planos/extract_all.py` → `model_all.pkl` (lectura del IFC, sin tocar Revit).
2. `python q_concreto.py` → volúmenes, encofrado y áreas de curado por elemento (trimesh).
3. `python q_corte.py` → plan de corte en varillas de 9 m (barras > 9 m: 9.00 + L − 9 + 1.15).
4. Los datos auxiliares (`q_acero_elem.json`, `q_areas.json`) se generan con el bloque del final de la sesión
   (acero por nivel/elemento/diámetro y áreas de losa aligerada con shapely).
5. `python build_xlsx.py` → `Lista_Materiales_Casco_SanJeronimo.xlsx` (fórmulas vivas; recalcular con LibreOffice).
