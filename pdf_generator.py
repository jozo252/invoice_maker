import pdfkit
import tempfile
from flask import render_template, url_for, current_app

def render_invoice_to_pdf(template_name, context):
    # Vyrenderuj HTML z Flask templatu
    html = render_template(template_name, **context)

    # Nastav cestu k wkhtmltopdf binárke – uprav podľa svojej inštalácie
    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

    # Nastav základné voľby, hlavne povolenie načítania lokálnych súborov
    options = {
        'enable-local-file-access': None,
        'quiet': '',
    }

    # Dočasný PDF súbor
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as pdf_file:
        pdfkit.from_string(html, pdf_file.name, configuration=config, options=options)
        return pdf_file.name
