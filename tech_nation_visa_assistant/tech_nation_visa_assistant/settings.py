import os
from pathlib import Path
from dotenv import load_dotenv
from django.contrib.messages import constants as messages


load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/


SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
RECAPTCHA_PUBLIC_KEY = os.getenv('RECAPTCHA_PUBLIC_KEY')
RECAPTCHA_PRIVATE_KEY = os.getenv('RECAPTCHA_PRIVATE_KEY')
RECAPTCHA_REQUIRED_SCORE = 0.5  # Threshold (0.0 to 1.0, where 1.0 is very likely a human)

# SECURITY WARNING: keep the secret key used in production secret!
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Required for allauth
    # Third-party apps
    'channels',
    'allauth',
    'allauth.account',
    'crispy_forms',
    'corsheaders',
    'payments',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Project apps
    'accounts',
    'document_manager',
    'ai_assistant',
    'expert_marketplace',
    'notion_monitor',
    'widget_tweaks',
    'referrals',
    'django_apscheduler'
]


# APScheduler settings
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"  # Default
SCHEDULER_DEFAULT = True
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds


ACCOUNT_FORMS = {
    'signup': 'accounts.forms.CustomSignupForm'
}



MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.AssessmentRequiredMiddleware',

    'allauth.account.middleware.AccountMiddleware',
    'csp.middleware.CSPMiddleware',  # Content Security Policy
]

ROOT_URLCONF = 'tech_nation_visa_assistant.urls'

SITE_ID = 1  # Make sure this matches the ID of your site

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'APP': {
            'client_id': '1001374382394-ed1f4t72366a09hdagequ11v51omha03.apps.googleusercontent.com',
            'secret': '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',
            'key': ''
        }
    }
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.recaptcha_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'tech_nation_visa_assistant.wsgi.application'
ASGI_APPLICATION = 'tech_nation_visa_assistant.asgi.application'
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}



# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Add these to your settings.py if they don't exist
SITE_NAME = 'Tech Nation Visa Assistant'
SITE_URL = 'http://localhost:8000'

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'



# Django AllAuth settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']

LOGIN_REDIRECT_URL = 'accounts:dashboard'  # Add namespace
ACCOUNT_LOGOUT_REDIRECT_URL = 'home'
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_SIGNUP_REDIRECT_URL = 'accounts:dashboard'  # Add this line

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')  # This should be your Gmail App Password
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL')
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'



# Additional AllAuth Email Settings
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'  # Change to 'optional' if you don't want to force email verification
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_EMAIL_SUBJECT_PREFIX = "Tech Nation Visa Assistant - "  # Customize this prefix
ACCOUNT_PASSWORD_RESET_TIMEOUT = 259200  # 3 days in seconds
ADMIN_EMAIL = 'support@technationvisaapp.com'
ACCOUNT_AUTHENTICATION_METHOD = 'email'

GOOGLE_SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'credentials', 'service-account-key.json')

# Crispy Forms
CRISPY_TEMPLATE_PACK = 'bootstrap4'

DEFAULT_FROM_EMAIL = "chidozie.managwu@gmail.com"  # Hardcoded for testing



# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    # Add production domains here
]
CORS_ALLOW_CREDENTIALS = True

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net")
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://js.stripe.com")
CSP_FONT_SRC = ("'self'", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:", "https://cdn.jsdelivr.net")
CSP_CONNECT_SRC = ("'self'", "https://api.stripe.com")
CSP_FRAME_SRC = ("'self'", "https://js.stripe.com")

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# In production, enable these
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True



OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')


BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')
# Stripe settings
STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', '')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')



# Allauth settings
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True

# Add these new settings instead
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
# Login/logout URLs
LOGIN_URL = 'account_login'


# Cloudflare Turnstile settings
TURNSTILE_SITE_KEY = '0x4AAAAAABXoW-U0A35vm-b8'  # Replace with your actual site key
TURNSTILE_SECRET_KEY = '0x4AAAAAABXoW_2kl3w3rzs0wXfU6mFsczE'  # Replace with your actual secret key


MESSAGE_TAGS = {
    messages.DEBUG: 'debug',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'error',
}


STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'debug.log'),
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'expert_marketplace': {  # Add this for your app
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}