from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Count, Avg, F, Q
from django.utils import timezone
from datetime import timedelta

from tickets.models import Ticket, Status
from departments.models import Department, Category
from identity.models import User, Role


# Raporlama dashboard'u — istatistiksel verileri hesaplar ve template'e aktarır
class ReportDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # ── Departman Performans Raporları ────────────────────────────────────

        # Departman bazlı bilet sayıları (açık, işlemde, kapalı, toplam)
        departments = Department.objects.annotate(
            total_tickets=Count('tickets'),
            open_tickets=Count('tickets', filter=Q(tickets__status=Status.OPEN)),
            in_progress_tickets=Count('tickets', filter=Q(tickets__status=Status.IN_PROGRESS)),
            closed_tickets=Count('tickets', filter=Q(tickets__status=Status.CLOSED)),
        ).order_by('-total_tickets')

        context['departments'] = departments

        # Departman bazlı ortalama çözüm süresi (saat cinsinden)
        dept_avg_resolution = []
        for dept in departments:
            closed = Ticket.objects.filter(
                department=dept,
                status=Status.CLOSED,
                closed_at__isnull=False,
            )
            if closed.exists():
                # closed_at - created_at farkının ortalaması
                durations = [
                    (t.closed_at - t.created_at).total_seconds() / 3600
                    for t in closed
                ]
                avg_hours = sum(durations) / len(durations)
            else:
                avg_hours = None

            dept_avg_resolution.append({
                'name': dept.name,
                'avg_hours': round(avg_hours, 1) if avg_hours else None,
                'closed_count': closed.count(),
            })

        context['dept_avg_resolution'] = dept_avg_resolution

        # En çok talep alan kategoriler (ilk 10)
        top_categories = Category.objects.annotate(
            ticket_count=Count('tickets'),
        ).filter(ticket_count__gt=0).order_by('-ticket_count')[:10]

        context['top_categories'] = top_categories

        # ── Personel İş Yükü Raporları ───────────────────────────────────────

        # Personel başına aktif bilet sayısı
        personnel = User.objects.filter(
            role__in=[Role.AGENT, Role.MANAGER],
        ).annotate(
            active_tickets=Count(
                'assigned_tickets',
                filter=Q(assigned_tickets__status=Status.IN_PROGRESS),
            ),
            total_closed=Count(
                'assigned_tickets',
                filter=Q(assigned_tickets__status=Status.CLOSED),
            ),
        ).order_by('-active_tickets')

        context['personnel'] = personnel

        # En çok bilet üstlenen personel sıralaması (ilk 10)
        top_personnel = User.objects.filter(
            role__in=[Role.AGENT, Role.MANAGER],
        ).annotate(
            total_assigned=Count('assigned_tickets'),
        ).filter(total_assigned__gt=0).order_by('-total_assigned')[:10]

        context['top_personnel'] = top_personnel

        # Personel bazlı ortalama çözüm süresi
        personnel_avg = []
        for p in top_personnel:
            closed = Ticket.objects.filter(
                assigned_to=p,
                status=Status.CLOSED,
                closed_at__isnull=False,
            )
            if closed.exists():
                durations = [
                    (t.closed_at - t.created_at).total_seconds() / 3600
                    for t in closed
                ]
                avg_hours = sum(durations) / len(durations)
            else:
                avg_hours = None

            personnel_avg.append({
                'name': p.get_full_name() or p.username,
                'avg_hours': round(avg_hours, 1) if avg_hours else None,
            })

        context['personnel_avg'] = personnel_avg

        # ── Grafiksel Dashboard Verileri ──────────────────────────────────────

        # Genel bilet istatistikleri
        context['total_tickets'] = Ticket.objects.count()
        context['open_count'] = Ticket.objects.filter(status=Status.OPEN).count()
        context['in_progress_count'] = Ticket.objects.filter(status=Status.IN_PROGRESS).count()
        context['closed_count'] = Ticket.objects.filter(status=Status.CLOSED).count()

        # Aylık bilet trend verisi (son 6 ay)
        today = timezone.now()
        monthly_data = []
        for i in range(5, -1, -1):
            month_start = (today - timedelta(days=i * 30)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            if i > 0:
                month_end = (today - timedelta(days=(i - 1) * 30)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0,
                )
            else:
                month_end = today

            count = Ticket.objects.filter(
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).count()

            monthly_data.append({
                'label': month_start.strftime('%b %Y'),
                'count': count,
            })

        context['monthly_labels'] = [m['label'] for m in monthly_data]
        context['monthly_counts'] = [m['count'] for m in monthly_data]

        # Departman karşılaştırma verisi (çubuk grafik için)
        context['dept_names'] = [d.name for d in departments]
        context['dept_open'] = [d.open_tickets for d in departments]
        context['dept_in_progress'] = [d.in_progress_tickets for d in departments]
        context['dept_closed'] = [d.closed_tickets for d in departments]

        return context
