"""Validation and immutable private receipt files. OCR never authorizes a cost."""
from datetime import date
from io import BytesIO
from pathlib import Path
import hashlib
import os
import re
import shutil
import tempfile
import warnings
from PIL import Image, UnidentifiedImageError

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_CENTS = 1_000_000_000

class ValidationError(ValueError):
    pass

def parse_cents(value, optional=False):
    value = str(value or '').strip()
    if optional and not value:
        return None
    if not re.fullmatch(r'(?:\d{1,8}|\d{1,3}(?:[ \u00a0]\d{3})+)(?:[,.]\d{1,2})?', value):
        raise ValidationError('Zadajte platnú sumu, napríklad 1 234,56.')
    whole, *decimal = re.sub(r'[ \u00a0]', '', value).replace(',', '.').split('.')
    cents = int(whole) * 100 + int((decimal[0] if decimal else '').ljust(2, '0') or '0')
    if cents > MAX_CENTS:
        raise ValidationError('Suma je príliš vysoká.')
    return cents

def parse_date(value, optional=False):
    if optional and not value:
        return None
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
            raise ValueError
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError('Zadajte platný dátum.') from None

def clean_text(value, maximum, label, required=False):
    value = str(value or '').strip()
    if (required and not value) or len(value) > maximum:
        raise ValidationError(f'Skontrolujte pole {label} (najviac {maximum} znakov).')
    return value

def validate_image(upload):
    if not upload or not upload.filename:
        raise ValidationError('Vyberte fotografiu bločka.')
    content = upload.stream.read(MAX_FILE_BYTES + 1)
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValidationError('Fotografia môže mať najviac 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                mime = {'JPEG':'image/jpeg', 'PNG':'image/png', 'WEBP':'image/webp'}.get(image.format)
                if not mime or image.width * image.height > 30_000_000 or getattr(image, 'n_frames', 1) != 1:
                    raise ValidationError('Vyberte jednu fotografiu JPG, PNG alebo WebP do 30 megapixelov.')
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Súbor nie je platná fotografia JPG, PNG alebo WebP.') from None
    return content, mime, hashlib.sha256(content).hexdigest()

def store_original(folder, user_id, digest, content):
    # The hash is generated on the server. Neither the filename nor OCR text becomes a path.
    object_name = f'{int(user_id)}/{digest}'
    destination = Path(folder) / object_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise OSError('Receipt object integrity mismatch')
        return object_name
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.receipt-')
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return object_name


def ensure_storage_capacity(folder, size, maximum):
    """Bound the small VPS pilot's disk use without touching other services."""
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    used = sum(path.stat().st_size for path in root.rglob('*') if path.is_file())
    if used + size > maximum:
        raise ValidationError('Pilot dosiahol limit úložiska bločkov. Pred ďalším nahrávaním skontrolujte zálohy a úložisko.')
    if shutil.disk_usage(root).free < size + 256 * 1024 * 1024:
        raise ValidationError('Na serveri nie je dostatok voľného miesta na ďalší bloček.')

def original_path(folder, receipt):
    expected = f'{receipt.user_id}/{receipt.sha256}'
    if not re.fullmatch(r'\d+/[0-9a-f]{64}', receipt.object_name) or receipt.object_name != expected:
        raise ValidationError('Originál bločka nie je dostupný.')
    root = Path(folder).resolve()
    path = (root / expected).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValidationError('Originál bločka nie je dostupný.')
    return path

def format_money(cents):
    if cents is None:
        return 'Nezadaná'
    sign = '−' if cents < 0 else ''
    value = abs(int(cents))
    whole = f'{value // 100:,}'.replace(',', ' ')
    return f'{sign}{whole},{value % 100:02d} €'
