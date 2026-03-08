import pdfkit
import os,shutil,tempfile
import tempfile
from flask import render_template, url_for, current_app

def _wkhtml_path():
    # 1) explicit env
    p = os.getenv("WKHTMLTOPDF_PATH")
    if p and os.path.exists(p):
        return p
    # 2) PATH lookup with stdlib (no shell)
    p = shutil.which("wkhtmltopdf")
    if p:
        return p
    # 3) common fallbacks
    for cand in ("/usr/bin/wkhtmltopdf", "/usr/local/bin/wkhtmltopdf"):
        if os.path.exists(cand):
            return cand
    raise RuntimeError(
        "wkhtmltopdf not found. Install with `apt install wkhtmltopdf` or set WKHTMLTOPDF_PATH."
    )

def render_invoice_to_pdf(template_name, context):
    # Vyrenderuj HTML z Flask templatu
    html = render_template(template_name, **context)

    # Nastav cestu k wkhtmltopdf binárke – uprav podľa svojej inštalácie
    
    config = pdfkit.configuration(wkhtmltopdf=_wkhtml_path())

    # Nastav základné voľby, hlavne povolenie načítania lokálnych súborov
    options = {
        'enable-local-file-access': None,
        'quiet': '',
    }

    # Dočasný PDF súbor
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
        pdfkit.from_string(html, pdf_file.name, configuration=config, options=options)
        return pdf_file.name
