# Dispatch

Dispatch is a Django-based internal service and ticket management system.

## Highlights

- Role-based access control
- Ticket lifecycle management
- Comments, tags, and attachments
- Notifications and reporting
- SSR-first interface with a limited REST API
- TR/EN localization and dark mode support

## Project Structure

- `identity` for authentication and user management
- `departments` for department and category management
- `tickets` for ticket workflows and API endpoints
- `notifications` for notification handling
- `reports` for reporting views and exports
- `dashboard` for the main landing page

## Setup

### Requirements

- Python 3.14+
- PostgreSQL
- WeasyPrint system dependencies for PDF export

Linux example:

```bash
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
```

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

```env
SECRET_KEY=django-insecure-change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=dispatch_db
DB_USER=postgres
DB_PASSWORD=postgres
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

### Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Run the Application

```bash
python manage.py runserver
```

### Optional Demo Data

```bash
python manage.py seed_demo --reset
```

Default users:

- `admin / admin123` (ADMIN)
- Manager, agent, and employee sample users: `pass123`

### Basic Maintenance

```bash
python manage.py check
python -m compileall -q .
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full text.
