# Dispatch

> Track internal support requests from open to close — with role-based access, business-hours SLAs, auto-assignment, and full TR/EN support, all in a hardened, server-rendered Django app.

Dispatch is a Django help-desk platform that takes an internal support request from open to close. Employees raise tickets, the system routes each one to the right department and auto-assigns an available agent, and managers watch the whole pipeline against business-hours SLAs — with escalation, satisfaction ratings, and CSV/Excel/PDF reporting built in.

## Features

- **Full ticket lifecycle** — Open → In Progress → Resolved → Closed (+ Escalated), with reopen limits, requester confirmation, and auto-close of stale tickets.
- **Kanban board** — drag-and-drop tickets across status columns for an at-a-glance view of the whole queue.
- **Smart auto-assignment** — routes each ticket to the **least-loaded** agent in the department (round-robin as a tie-breaker), with a per-agent active-ticket cap so no one gets overloaded.
- **Role-based access** — Employee, Agent, Manager, Admin; each role sees and does only what it should.
- **Security hardening** — brute-force lockout (django-axes), uploads validated by extension, size, and real content, CSRF on every form, and auto-enabled HTTPS redirect, HSTS, and `Secure`/`HttpOnly` cookies in production.
- **Business-hours SLAs** — due dates from working hours (Mon–Fri, 09:00–18:00) per priority (Urgent 4h / High 24h / Normal 72h / Low 168h), with overdue tracking and early warnings.
- **Collaboration** — threaded comments, file attachments, color-coded tags, and a full per-ticket audit trail.
- **In-app notifications** — live unread badge with alerts for assignments, status changes, and SLA warnings.
- **Reporting** — metrics dashboard with one-click **CSV / Excel / PDF** export.
- **Bilingual (TR / EN) + dark mode**, remembered per user.

## Tech Stack

| Layer | Technologies |
| --- | --- |
| **Backend** | Python 3.13, Django 6.0 |
| **Frontend** | Server-rendered templates, vanilla JS, custom CSS (light/dark) |
| **Database** | PostgreSQL 17 (`psycopg2`) |
| **Security** | django-axes (brute-force lockout), Django password validators, hardened upload validation, HSTS / secure cookies |
| **Documents** | WeasyPrint (PDF), openpyxl (Excel), Pillow (images) |
| **DevOps** | Gunicorn, Docker, Docker Compose, gettext (i18n) |

## Installation

**With Docker** (app + PostgreSQL 17, migrations run on boot, served on `127.0.0.1:8000`):

```bash
docker compose up -d --build
```

**Manual setup** (requires Python ≥ 3.13 and PostgreSQL; PDF export needs [WeasyPrint's system libraries](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)):

```bash
git clone https://github.com/batuhanmeral/Dispatch.git && cd Dispatch
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in SECRET_KEY, ALLOWED_HOSTS, DB_*
python manage.py migrate && python manage.py createsuperuser
python manage.py runserver        # http://localhost:8000
```

## Project Structure

| App | Responsibility |
| --- | --- |
| `identity` | User model, authentication, roles, audit logging |
| `departments` | Departments, categories, auto-assignment config |
| `tickets` | Ticket lifecycle, SLAs, assignment, comments, attachments, history |
| `notifications` | In-app notifications and the unread-count badge |
| `reports` | Dashboard metrics and CSV / Excel / PDF exports |
| `config` | Project settings, URLs, role-based landing dashboard |

## Screenshots

**Dashboard**

<img src="docs/dashboard.png" alt="Dashboard" width="850">

**Reports**

<img src="docs/reports.png" alt="Reports" width="850">

**Kanban Board**

<img src="docs/kanban.png" alt="Kanban Board" width="850">

## License

[MIT License](LICENSE). © 2026 Batuhan Meral.
