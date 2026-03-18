"""
DC Feasibility Tool v4 - PDF Export
===================================
Converts rendered HTML into a PDF document using weasyprint.
Includes robust error handling and logging.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Ensure Homebrew libraries are discoverable on macOS.
# WeasyPrint depends on pango/cairo which are typically installed via
# `brew install pango`.  When Python is running inside conda or a
# virtualenv the default DYLD_FALLBACK_LIBRARY_PATH may not include
# /opt/homebrew/lib (Apple Silicon) or /usr/local/lib (Intel Mac).
if sys.platform == "darwin":
    _brew_lib_dirs = ["/opt/homebrew/lib", "/usr/local/lib"]
    _current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    _missing = [d for d in _brew_lib_dirs if d not in _current and os.path.isdir(d)]
    if _missing:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            ":".join(_missing) + (":" + _current if _current else "")
        )


def html_to_pdf_bytes(html: str) -> bytes:
    """Convert an HTML string to PDF bytes using WeasyPrint.

    Raises OSError if WeasyPrint / its system deps are not available.
    Raises RuntimeError if PDF generation returns empty output.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise OSError(
            "WeasyPrint is not installed or its system dependencies are missing. "
            "Install with: pip install weasyprint. "
            "On macOS you also need: brew install pango. "
            f"Original error: {exc}"
        ) from exc

    try:
        logger.info("Starting PDF generation (%d chars of HTML)", len(html))
        pdf_bytes = HTML(string=html).write_pdf()
        if pdf_bytes is None:
            raise RuntimeError("WeasyPrint returned no PDF bytes")
        logger.info("PDF generation complete: %d bytes", len(pdf_bytes))
        return pdf_bytes
    except OSError:
        raise
    except Exception as exc:
        logger.exception("PDF generation failed")
        raise RuntimeError(
            f"PDF generation failed: {type(exc).__name__}: {exc}"
        ) from exc
