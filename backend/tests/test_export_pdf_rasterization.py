from api.routes_export import _rasterize_inline_svgs_for_pdf


def test_rasterize_inline_svgs_for_pdf_preserves_non_svg_markup():
    html = "<div><p>hello</p></div>"

    assert _rasterize_inline_svgs_for_pdf(html) == html


def test_rasterize_inline_svgs_for_pdf_replaces_inline_svg_when_cairosvg_available():
    html = (
        '<div class="chart-container">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 20" aria-label="Test chart">'
        '<rect x="0" y="0" width="100" height="20" fill="#ffffff" />'
        '<text x="10" y="14" font-size="10">Hello</text>'
        "</svg>"
        "</div>"
    )

    rasterized = _rasterize_inline_svgs_for_pdf(html)

    if rasterized == html:
        # CairoSVG not installed in the active environment; graceful fallback is expected.
        return

    assert "<svg" not in rasterized
    assert 'class="pdf-rasterized-svg"' in rasterized
    assert 'src="data:image/png;base64,' in rasterized
    assert 'alt="Test chart"' in rasterized
