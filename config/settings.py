import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasındaki verileri sisteme yükler
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'drf_spectacular',
    'corsheaders',
    'identity',
    'departments',
    'tickets',
    'notifications',
    'reports',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # CorsMiddleware mümkün olduğunca üstte olmalı (CommonMiddleware'den önce)
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # i18n: kullanıcı dilini session/cookie/Accept-Language'tan tespit eder
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'notifications.context_processors.notification_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'tr'

TIME_ZONE = 'Europe/Istanbul'

USE_I18N = True

USE_TZ = True

# Desteklenen diller (navbar dil seçici için)
from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('tr', _('Türkçe')),
    ('en', _('English')),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Özel Kullanıcı Modeli Tanımlaması
AUTH_USER_MODEL = 'identity.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Kimlik Doğrulama Yönlendirmeleri
LOGIN_URL = 'identity:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'identity:login'

# Django REST Framework Ayarları
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': '%d.%m.%Y %H:%M',
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Brute-force koruması — anonim/hatalı isteklerde IP/kullanıcı bazlı limit.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',         # genel anonim trafik
        'user': '1000/hour',      # giriş yapmış kullanıcı
        'login': '10/min',        # login: dakikada 10 deneme (IP başına)
        'register': '5/hour',     # register: saatte 5 (kötüye kullanım önleme)
        'password_change': '5/hour',
        'ticket_create': '30/hour',   # bilet oluşturma — kullanıcı başına spam koruması
    },
}

# drf-spectacular (OpenAPI/Swagger) Ayarları
SPECTACULAR_SETTINGS = {
    'TITLE': 'ESMS API',
    'DESCRIPTION': 'Kurumsal Talep Yönetim Sistemi REST API dokümantasyonu',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': r'/api/v1',
    'COMPONENT_SPLIT_REQUEST': True,
    'SORT_OPERATIONS': False,
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
    'TAGS': [
        {'name': 'auth', 'description': 'Kimlik doğrulama (login, logout, register, profil, JWT)'},
        {'name': 'users', 'description': 'Kullanıcı yönetimi (Admin)'},
        {'name': 'departments', 'description': 'Departman ve kategori yönetimi'},
        {'name': 'tickets', 'description': 'Bilet yaşam döngüsü, yorumlar, transfer'},
        {'name': 'notifications', 'description': 'Bildirim yönetimi'},
        {'name': 'reports', 'description': 'Raporlama ve dışa aktarım'},
        {'name': 'dashboard', 'description': 'Rol bazlı dashboard verisi'},
    ],
}

# JWT Ayarları (djangorestframework-simplejwt)
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),     # access kısa ömürlü
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),        # refresh 1 hafta
    'ROTATE_REFRESH_TOKENS': True,                      # her refresh'te yeni refresh
    'BLACKLIST_AFTER_ROTATION': True,                   # eski refresh blacklist'e
    'UPDATE_LAST_LOGIN': True,                          # last_login güncellenir
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# CORS Ayarları (django-cors-headers)
# Geliştirme: tüm origin'lere izin ver. Production'da CORS_ALLOWED_ORIGINS ile kısıtla.
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True
# CORS sadece API yollarında uygulansın
CORS_URLS_REGEX = r'^/api/.*$'