from .settings import *

if not os.environ.get('POSTGRES_DB'):
    DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DJANGO_DB_PATH', BASE_DIR / 'db2.sqlite3'),
        'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'},
    }
}
