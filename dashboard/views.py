from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Count, Q

from tickets.models import Ticket, Status
from notifications.models import Notification
from identity.models import Role


# Rol bazlı ana sayfa dashboard'u
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # ── Çalışan (EMPLOYEE): Kendi biletleri ─────────────────────────────
        if user.role == Role.EMPLOYEE:
            my_tickets = Ticket.objects.filter(sender=user)
            context['my_open'] = my_tickets.filter(status=Status.OPEN).count()
            context['my_in_progress'] = my_tickets.filter(status=Status.IN_PROGRESS).count()
            context['my_closed'] = my_tickets.filter(status=Status.CLOSED).count()
            context['recent_tickets'] = my_tickets.select_related('department')[:5]

        # ── Personel (AGENT): Departman bilet havuzu ─────────────────────────
        elif user.role == Role.AGENT:
            dept_tickets = Ticket.objects.filter(department=user.department)
            context['dept_open'] = dept_tickets.filter(status=Status.OPEN).count()
            context['dept_in_progress'] = dept_tickets.filter(status=Status.IN_PROGRESS).count()
            context['my_assigned'] = Ticket.objects.filter(
                assigned_to=user, status=Status.IN_PROGRESS
            ).select_related('sender', 'department')[:5]
            context['waiting_tickets'] = dept_tickets.filter(
                status=Status.OPEN
            ).select_related('sender')[:5]

        # ── Yönetici (MANAGER): Departman istatistikleri ─────────────────────
        elif user.role == Role.MANAGER:
            dept_tickets = Ticket.objects.filter(department=user.department)
            context['dept_total'] = dept_tickets.count()
            context['dept_open'] = dept_tickets.filter(status=Status.OPEN).count()
            context['dept_in_progress'] = dept_tickets.filter(status=Status.IN_PROGRESS).count()
            context['dept_closed'] = dept_tickets.filter(status=Status.CLOSED).count()

            # Personel iş yükü
            from identity.models import User
            context['personnel_load'] = User.objects.filter(
                department=user.department,
                role__in=[Role.AGENT, Role.MANAGER],
            ).annotate(
                active=Count('assigned_tickets', filter=Q(assigned_tickets__status=Status.IN_PROGRESS)),
            ).order_by('-active')[:10]

            context['recent_tickets'] = dept_tickets.select_related(
                'sender', 'assigned_to'
            )[:5]

        # ── Admin: Sistem geneli ─────────────────────────────────────────────
        elif user.role == Role.ADMIN:
            context['total_tickets'] = Ticket.objects.count()
            context['total_open'] = Ticket.objects.filter(status=Status.OPEN).count()
            context['total_in_progress'] = Ticket.objects.filter(status=Status.IN_PROGRESS).count()
            context['total_closed'] = Ticket.objects.filter(status=Status.CLOSED).count()

            # Departman özeti
            from departments.models import Department
            context['dept_summary'] = Department.objects.annotate(
                open_count=Count('tickets', filter=Q(tickets__status=Status.OPEN)),
                total_count=Count('tickets'),
            ).order_by('-open_count')

            context['recent_tickets'] = Ticket.objects.select_related(
                'sender', 'department', 'assigned_to'
            )[:5]

        # Son bildirimler (tüm roller için)
        context['recent_notifications'] = Notification.objects.filter(
            recipient=user, is_read=False,
        ).select_related('ticket')[:5]

        return context
