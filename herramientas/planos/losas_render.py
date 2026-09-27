"""Render propio de las laminas de losas: igual a sheetcommon.save_and_render pero con los tipos de linea
(oculta, eje) visibles en el PDF ."""
from sheetcommon import W_, H_


def save_and_render_lt(doc, ps, basename, dpi=110):
    doc.set_modelspace_vport(height=20, center=(5, 5))
    doc.saveas(basename + ".dxf")
    # el addon de dibujo de ezdxf escala los patrones de linea del espacio modelo (en metros) como si fueran mm
    # al verlos por una ventana: solo para el render se compensa con ltscale (el DXF ya quedo guardado sin esto)
    for e in doc.modelspace():
        if e.dxf.hasattr("linetype") and e.dxf.linetype.upper() not in ("BYLAYER", "CONTINUOUS", "BYBLOCK"):
            e.dxf.ltscale = e.dxf.get("ltscale", 1.0) * 1000.0
    from ezdxf.addons.drawing import Frontend, RenderContext, pymupdf, layout, config
    ctx = RenderContext(doc)
    be = pymupdf.PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.COLOR,
                               lineweight_policy=config.LineweightPolicy.ABSOLUTE,
                               lineweight_scaling=1.0, min_lineweight=0.09,
                               hatch_policy=config.HatchPolicy.NORMAL,
                               line_policy=config.LinePolicy.ACCURATE)
    Frontend(ctx, be, config=cfg).draw_layout(ps, filter_func=lambda e: e.dxf.layer != "E-VPORT" or e.dxftype() == "VIEWPORT")
    page = layout.Page(W_, H_, layout.Units.mm, margins=layout.Margins.all(0))
    st_ = layout.Settings(fit_page=True)
    open(basename + ".pdf", "wb").write(be.get_pdf_bytes(page, settings=st_))
    open(basename + "_preview.png", "wb").write(be.get_pixmap_bytes(page, fmt="png", dpi=dpi, settings=st_))
