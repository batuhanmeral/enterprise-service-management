# Dispatch

> Track internal support requests from open to close — with role-based access, business-hours SLAs, auto-assignment, and full TR/EN support, all in a hardened, server-rendered Django app.

Dispatch is a Django help-desk platform that takes an internal support request from open to close. Employees raise tickets, the system routes each one to the right department and auto-assigns an available agent, and managers watch the whole pipeline against business-hours SLAs — with escalation, satisfaction ratings, and CSV/Excel/PDF reporting built in.

## 🚀 Features

- **Full ticket lifecycle** — Open → In Progress → Resolved → Closed (+ Escalated), with reopen limits, requester confirmation, and auto-close of stale tickets.
- **Kanban board** — drag-and-drop tickets across status columns for an at-a-glance view of the whole queue.
- **Smart auto-assignment** — routes each ticket to the **least-loaded** agent in the department (round-robin as a tie-breaker), with a per-agent active-ticket cap so no one gets overloaded.
- **Role-based access** — Employee, Agent, Manager, Admin; each role sees and does only what it should.
- **Business-hours SLAs** — due dates from working hours (Mon–Fri, 09:00–18:00) per priority (Urgent 4h / High 24h / Normal 72h / Low 168h), with overdue tracking and early warnings.
- **Collaboration** — threaded comments, file attachments, color-coded tags, and a full per-ticket audit trail.
- **In-app notifications** — live unread badge with alerts for assignments, status changes, and SLA warnings.
- **Reporting** — metrics dashboard with one-click **CSV / Excel / PDF** export.
- **Bilingual (TR / EN) + dark mode**, remembered per user.

## 🛠️ Tech Stack

| Layer | Technologies |
| --- | --- |
| **Backend** | Python 3.13, Django 6.0 |
| **Frontend** | Server-rendered templates, vanilla JS, custom CSS (light/dark) |
| **Database** | PostgreSQL 17 (`psycopg2`) |
| **Security** | django-axes (brute-force lockout), Django password validators, hardened upload validation, HSTS / secure cookies |
| **Documents** | WeasyPrint (PDF), openpyxl (Excel), Pillow (images) |
| **DevOps** | Gunicorn, Docker, Docker Compose, gettext (i18n) |

## 📦 Installation

**Prerequisites:** Python ≥ 3.13, PostgreSQL (or the bundled Docker setup). The Docker image installs everything itself; for a non-Docker Linux setup, PDF export needs WeasyPrint's system libraries:

```bash
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2
```

### 1. Clone & install

```bash
git clone https://github.com/batuhanmeral/Dispatch.git
cd Dispatch
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in `SECRET_KEY`, `ALLOWED_HOSTS`, and the `DB_*` values. Generate a key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

> When `DEBUG=False`, Dispatch auto-enables HTTPS redirects, HSTS, and `Secure`/`HttpOnly` cookies (see [Security](#-security)).

### 3. Run

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver        # http://localhost:8000
```

### Or with Docker (app + PostgreSQL)

```bash
docker compose up -d --build
```

Provisions PostgreSQL 17 with healthcheck and persistent volumes, runs migrations + `collectstatic` on boot, and serves via Gunicorn as a non-root user. Web is published only on `127.0.0.1:8000`; the database is never exposed to the host.

## 💡 Usage

Seed sample data to explore quickly (`docker compose exec web python …` inside Docker):

```bash
python manage.py seed_demo --reset
```

Demo accounts: `admin` / `admin123` (Admin); sample manager · agent · employee / `pass123`.

### Roles & permissions

| Capability | Admin | Manager | Agent | Employee |
| --- | :---: | :---: | :---: | :---: |
| Open & track own tickets | ✓ | ✓ | ✓ | ✓ |
| Work / resolve assigned tickets | ✓ | ✓ | ✓ | — |
| Manage departments & assignments | ✓ | ✓ | — | — |
| Reports & exports | ✓ | ✓ | — | — |
| User & system administration | ✓ | — | — | — |

## 🔒 Security

- **Brute-force protection** — django-axes locks an account/IP after 5 failed logins for 15 minutes.
- **Strong passwords** — Django's full validator suite.
- **Hardened file uploads** — validated by extension, size, **and** real content.
- **Production headers** (auto on `DEBUG=False`) — HSTS preload, HTTPS redirect, `Secure`/`HttpOnly`/`SameSite` cookies, `X-Frame-Options: DENY`, `nosniff`, strict referrer policy.
- **CSRF protection** on every form; secrets stay in `.env` and never enter the image.
- **Hardened container** — unprivileged user, all Linux capabilities dropped, `no-new-privileges`.

## 🧪 Tests

Unit tests cover the business-hours SLA math, least-loaded / round-robin auto-assignment, and the ticket lifecycle (reopen limits, escalation, CSAT):

```bash
python manage.py test                                          # against PostgreSQL
DB_ENGINE=django.db.backends.sqlite3 python manage.py test     # no DB server needed
```

## 🗂️ Project Structure

| App | Responsibility |
| --- | --- |
| `identity` | User model, authentication, roles, audit logging |
| `departments` | Departments, categories, auto-assignment config |
| `tickets` | Ticket lifecycle, SLAs, assignment, comments, attachments, history |
| `notifications` | In-app notifications and the unread-count badge |
| `reports` | Dashboard metrics and CSV / Excel / PDF exports |
| `config` | Project settings, URLs, role-based landing dashboard |

## 📸 Screenshots

| Dashboard | Reports | Kanban |
| :---: | :---: | :---: |
| ![Dashboard](docs/dashboard.png) | ![Reports](docs/reports.png) | ![Kanban Board](docs/kanban.png) |

## 📄 License

[MIT License](LICENSE). © 2026 Batuhan Meral.
