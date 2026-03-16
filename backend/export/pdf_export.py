"""
DC Feasibility Tool v4 - PDF Export
===================================
Converts rendered HTML into a PDF document using weasyprint.
"""

def html_to_pdf_bytes(html: str) -> bytes:
    from weasyprint import HTML

    pdf_bytes = HTML(string=html).write_pdf()
    if pdf_bytes is None:
        raise RuntimeError("WeasyPrint returned no PDF bytes")
    return pdf_bytes
