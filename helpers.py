def generate_invoice_number():
    last_invoice = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.id.desc()).first()
    new_number = (int(last_invoice.invoice_number.split("-")[-1]) + 1) if last_invoice else 1
    return f"INV-{datetime.now().year}-{new_number:04d}"