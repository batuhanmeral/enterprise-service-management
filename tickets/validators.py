import os
from django.core.exceptions import ValidationError

# İzin verilen dosya uzantıları
ALLOWED_EXTENSIONS = ['.pdf', '.png', '.jpg', '.jpeg', '.docx']

# Maksimum dosya boyutu: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024


# Dosya uzantısını kontrol eden validator
def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ', '.join(ALLOWED_EXTENSIONS)
        raise ValidationError(
            f'Bu dosya türü desteklenmiyor. İzin verilen türler: {allowed}'
        )


# Dosya boyutunu kontrol eden validator
def validate_file_size(value):
    if value.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ValidationError(
            f'Dosya boyutu {max_mb} MB sınırını aşıyor. '
            f'Mevcut boyut: {value.size / (1024 * 1024):.1f} MB'
        )


# Dosya içeriğini kontrol eden güvenlik validatörü (magic bytes)
def validate_file_content(value):
    # Dosyanın ilk birkaç byte'ını oku
    header = value.read(8)
    value.seek(0)  # Dosya imlecini başa al

    # Bilinen dosya imzaları (magic bytes)
    signatures = {
        b'%PDF': '.pdf',
        b'\x89PNG': '.png',
        b'\xff\xd8\xff': '.jpg',
        b'PK\x03\x04': '.docx',  # ZIP tabanlı (DOCX)
    }

    ext = os.path.splitext(value.name)[1].lower()

    for magic, expected_ext in signatures.items():
        if header.startswith(magic):
            # .jpeg ve .jpg aynı formattır
            if expected_ext == '.jpg' and ext in ('.jpg', '.jpeg'):
                return
            if expected_ext == '.docx' and ext == '.docx':
                return
            if ext == expected_ext:
                return

    raise ValidationError(
        'Dosya içeriği, uzantısı ile uyuşmuyor. '
        'Lütfen geçerli bir dosya yükleyin.'
    )
