import os
from django.core.exceptions import ValidationError


AVATAR_ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']

AVATAR_MAX_FILE_SIZE = 2 * 1024 * 1024

_IMAGE_SIGNATURES = {
    b'\x89PNG\r\n\x1a\n': '.png',
    b'\xff\xd8\xff': '.jpg',
    b'RIFF': '.webp',
}


def validate_avatar_extension(value):
    ext = os.path.splitext(value.name)[1].lower()
    if ext not in AVATAR_ALLOWED_EXTENSIONS:
        allowed = ', '.join(AVATAR_ALLOWED_EXTENSIONS)
        raise ValidationError(
            f'Geçersiz görsel formatı. İzin verilen türler: {allowed}'
        )


def validate_avatar_size(value):
    if value.size > AVATAR_MAX_FILE_SIZE:
        max_mb = AVATAR_MAX_FILE_SIZE // (1024 * 1024)
        raise ValidationError(
            f'Görsel boyutu {max_mb} MB sınırını aşıyor. '
            f'Mevcut: {value.size / (1024 * 1024):.1f} MB'
        )


def validate_avatar_content(value):
    header = value.read(12)
    value.seek(0)

    ext = os.path.splitext(value.name)[1].lower()

    if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        if ext == '.webp':
            return
        raise ValidationError('Dosya içeriği uzantı ile uyuşmuyor.')

    for magic, expected_ext in _IMAGE_SIGNATURES.items():
        if expected_ext == '.webp':
            continue
        if header.startswith(magic):
            if expected_ext == '.jpg' and ext in ('.jpg', '.jpeg'):
                return
            if ext == expected_ext:
                return

    raise ValidationError('Geçerli bir görsel dosyası yükleyin (PNG, JPG, WEBP).')
