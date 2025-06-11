# [Your Project Name - e.g., TalentVisaNavigator / GlobalTalentKey]

**Elevator Pitch:** [Your Project Name] is a comprehensive platform designed to empower individuals seeking the Global Talent Visa. It combines AI-powered document analysis tools (CVs, Personal Statements) with access to expert human consultations, a robust points and referral system, and secure payment processing, all aimed at simplifying and enhancing the visa application journey.

---

## Table of Contents

1.  [Overview](#overview)
2.  [Key Features](#key-features)
    *   [Client Features](#client-features)
    *   [Expert Features](#expert-features)
    *   [Admin Features](#admin-features)
3.  [Technology Stack](#technology-stack)
4.  [Project Structure](#project-structure)
5.  [Prerequisites](#prerequisites)
6.  [Installation & Setup](#installation--setup)
    *   [Clone Repository](#1-clone-repository)
    *   [Set Up Virtual Environment](#2-set-up-virtual-environment)
    *   [Install Dependencies](#3-install-dependencies)
    *   [Environment Variables](#4-environment-variables)
    *   [Database Setup](#5-database-setup)
    *   [Static Files](#6-static-files)
    *   [Stripe CLI & Webhooks (Development)](#7-stripe-cli--webhooks-development)
7.  [Running the Application](#running-the-application)
    *   [Development Server](#development-server)
    *   [Celery Worker (for background tasks)](#celery-worker-for-background-tasks)
8.  [Admin Panel](#admin-panel)
9.  [Key Configuration Points](#key-configuration-points)
10. [Usage Highlights](#usage-highlights)
11. [Deployment Considerations](#deployment-considerations)
12. [Contributing](#contributing)
13. [License](#license)
14. [Contact](#contact)

---

## Overview

This platform serves as a one-stop solution for individuals navigating the complexities of the Global Talent Visa application process. It provides:
*   **AI-Driven Tools:** For initial CV analysis and Personal Statement generation/enhancement.
*   **Expert Consultations:** Direct access to experienced consultants for personalized guidance, strategy, and in-depth feedback.
*   **Community & Rewards:** A referral system to encourage growth and reward users.
*   **Secure & Seamless Experience:** User-friendly interface with secure payment integration.

The primary goal is to increase applicants' chances of success by providing accessible, high-quality resources and expert support.

---

## Key Features

### Client Features
*   **Account Management:** Secure signup, login, password reset, personalized dashboard.
*   **AI Tools:**
    *   CV Analysis (points/free use based).
    *   Personal Statement Generation (points/free use based).
*   **Points System:** Purchase points (Stripe), view balance, earn initial bonus points.
*   **Referral Program:** Unique referral code, track referrals, earn free uses for AI tools.
*   **Consultation Booking:**
    *   Multi-step booking form (select expertise, schedule date/time, provide info).
    *   View consultant profiles.
    *   Secure payment via Stripe.
    *   Email confirmations.
*   **Booking Management:** View upcoming/past bookings, cancel/reschedule (per policy).
*   **Feedback:** Leave reviews and ratings for experts post-consultation.
*   **Support:** Contact form for inquiries.
*   **Document Access:** Download analyzed CVs and generated statements.

### Expert Features
*   **Profile Management:** Update personal details, bio, expertise, profile image, availability (JSON).
*   **Stripe Connect Onboarding:** Securely link bank accounts for payouts.
*   **Consultation Management:** Dashboard for assigned bookings, client details, mark consultations complete.
*   **Earnings:** View total earnings, pending payouts, detailed history.
*   **Feedback & Disputes:** View client ratings/reviews, respond to no-show disputes.

### Admin Features
*   **Centralized Dashboard:** Key metrics, user activity, financial summaries.
*   **User & Expert Management:** Full CRUD, link user accounts to experts, approve experts, manage profiles, tiers, commissions, Stripe status.
*   **Booking & Consultation Oversight:** View/filter/search bookings, manual expert assignment, manage booking statuses, process refunds.
*   **Financial Administration:** Monitor Stripe transactions, manage platform fees, expert earnings, payouts, bonuses.
*   **Referral Program Management:** Monitor activity, view codes, track signups, ensure reward processing.
*   **Review & Dispute Moderation:** View/moderate reviews, manage no-show disputes.
*   **Support Management:** Access and respond to contact form inquiries.
*   **System Configuration:** (Potentially) Manage site-wide settings, email templates.

---

## Technology Stack

*   **Backend:** Python 3.x, Django 4.x+
*   **Frontend:** HTML5, CSS3 (Tailwind CSS), JavaScript (Vanilla JS, jQuery for specific widgets like datepicker)
*   **Database:** PostgreSQL (recommended for production), SQLite (for development)
*   **Payments:** Stripe (Stripe Payments, Stripe Connect)
*   **Background Tasks:** Celery with Redis (or RabbitMQ) as a message broker
*   **Caching:** Redis (optional, for performance)
*   **AI Integration:** OpenAI API (for CV analysis, Personal Statement generation)
*   **Web Server (Production):** Gunicorn / Uvicorn
*   **Reverse Proxy (Production):** Nginx
*   **Containerization (Optional but Recommended):** Docker, Docker Compose

---

## Project Structure

The project follows a standard Django application structure:
[your_project_root]/
├── [your_project_name]/ # Main Django project configuration (settings.py, urls.py, wsgi.py, asgi.py, celery.py)
├── accounts/ # User authentication, profiles, points
├── ai_tools/ # CV analysis, Personal Statement generation logic (interacts with OpenAI)
├── bookings/ # Consultation booking, scheduling, payments
├── consultations/ # Managing the actual consultation sessions, reviews
├── expert_marketplace/ # Expert profiles, availability, earnings
├── referrals/ # Referral code generation, tracking, rewards
├── payments/ # Stripe integration, payment processing logic, webhooks
├── site_admin/ # Custom admin views or specific admin functionalities
├── static/ # Global static files (CSS, JS, images)
├── templates/ # Global base templates and app-specific templates
├── media/ # User-uploaded files (profile images, CVs) - configure storage (local/Cloudinary)
├── .env.example # Example environment variables file
├── manage.py # Django's command-line utility
├── requirements.txt # Python dependencies
└── README.md # This file

*(Adjust the app names in the structure above if they differ in your project.)*

---

## Prerequisites

Before you begin, ensure you have the following installed:
*   Python (3.8+ recommended)
*   Pip (Python package installer)
*   Git
*   PostgreSQL (or ensure SQLite is available if preferred for local dev)
*   Redis (if using Celery with Redis)
*   Docker and Docker Compose (Optional, but highly recommended for easier setup and deployment)
*   Stripe CLI (for testing webhooks locally)

---

## Installation & Setup

### 1. Clone Repository
```bash
git clone [your-repo-url]
cd [your-project-directory-name]
```
## 2. Set Up Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
## 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## 4. Environment Variables
```bash
cp .env.example .env
```

Now, edit the .env file with your actual configuration values. Key variables include
```bash
# Django Settings
SECRET_KEY='your_strong_secret_key_here'
DEBUG=True  # Set to False in production
ALLOWED_HOSTS=127.0.0.1,localhost # Add your domain in production

# Database Settings (Example for PostgreSQL)
DATABASE_URL=postgres://user:password@host:port/dbname

# Email Settings (Example for Gmail - use app password for security)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER='your_email@example.com'
EMAIL_HOST_PASSWORD='your_email_password_or_app_password'
DEFAULT_FROM_EMAIL='Your Platform Name <your_email@example.com>'

# Stripe Settings
STRIPE_PUBLISHABLE_KEY=pk_test_yourpublishablekey
STRIPE_SECRET_KEY=sk_test_yoursecretkey
STRIPE_WEBHOOK_SECRET=whsec_yourwebhooksecret # For verifying webhook events
STRIPE_CONNECT_CLIENT_ID=ca_yourconnectclientid # For Stripe Connect onboarding

# OpenAI API Key
OPENAI_API_KEY='sk-youropenaiapikey'

# Celery Settings (Example for Redis)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Cloudinary Settings (If using Cloudinary for media storage)
# CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name

# Other settings
SITE_URL=http://localhost:8000 # Your site's base URL (update for production)
```
Note: For production, DEBUG must be False and SECRET_KEY must be a strong, unique key.

## 5. Database Setup
Ensure your database server (e.g., PostgreSQL, Redis) is running.
```bash
python manage.py makemigrations
python manage.py migrate
```
Create a superuser to access the Django admin panel:
```bash
python manage.py createsuperuser
```

## 6. Static Files
For development, Django usually serves static files automatically if DEBUG=True. For production, or to test:
```bash
python manage.py collectstatic --noinput
```

## 7. Stripe CLI & Webhooks (Development)
To test Stripe webhooks locally (e.g., for payment confirmations, subscription updates):

  1. Install the Stripe CLI.
  2. Log in: stripe login
  3. Forward webhook events to your local development server
     ```bash
     stripe listen --forward-to localhost:8000/payments/stripe-webhook/
     ```
     The Stripe CLI will provide you with a webhook signing secret. Update STRIPE_WEBHOOK_SECRET in your .env file with this secret for local testing.
  4. In your Stripe Dashboard, ensure you have webhook endpoints configured for the events your application handles (e.g., payment_intent.succeeded, charge.refunded, checkout.session.completed, account.updated for Connect).


## Running the Application
**Development Server**
Start the Django development server:
```bash
python manage.py runserver
```
