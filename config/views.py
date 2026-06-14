from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Count, Q

from tickets.models import Ticket, Status
from identity.models import Role


# Rol bazlı ana sayfa dashboard'u
class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.role == Role.EMPLOYEE:
            my_tickets = Ticket.objects.filter(sender=user)
            context.update(my_tickets.aggregate(
                my_open=Count('pk', filter=Q(status=Status.OPEN)),
                my_in_progress=Count('pk', filter=Q(status=Status.IN_PROGRESS)),
                my_resolved=Count('pk', filter=Q(status=Status.RESOLVED)),
                my_closed=Count('pk', filter=Q(status=Status.CLOSED)),
            ))
            context['recent_tickets'] = my_tickets.select_related('department')[:5]
            context['awaiting_action'] = my_tickets.filter(
                Q(status=Status.RESOLVED) |
                Q(status=Status.CLOSED, csat_rating__isnull=True),
            ).select_related('department', 'assigned_to')[:5]

        elif user.role == Role.AGENT:
            dept_tickets = Ticket.objects.filter(department=user.department)
            context.update(dept_tickets.aggregate(
                dept_open=Count('pk', filter=Q(status=Status.OPEN)),
                dept_in_progress=Count('pk', filter=Q(status=Status.IN_PROGRESS)),
            ))
            context['my_assigned'] = Ticket.objects.filter(
                assigned_to=user, status=Status.IN_PROGRESS
            ).select_related('sender', 'department')[:5]
            context['waiting_tickets'] = dept_tickets.filter(
                status=Status.OPEN
            ).select_related('sender')[:5]
            context['my_history'] = Ticket.objects.filter(
                Q(sender=user) | Q(assigned_to=user)
            ).exclude(status__in=[Status.OPEN, Status.IN_PROGRESS]).order_by('-created_at')[:5]

        elif user.role == Role.MANAGER:
            dept_tickets = Ticket.objects.filter(department=user.department)
            context.update(dept_tickets.aggregate(
                dept_total=Count('pk'),
                dept_open=Count('pk', filter=Q(status=Status.OPEN)),
                dept_in_progress=Count('pk', filter=Q(status=Status.IN_PROGRESS)),
                dept_resolved=Count('pk', filter=Q(status=Status.RESOLVED)),
                dept_closed=Count('pk', filter=Q(status=Status.CLOSED)),
                dept_escalated=Count('pk', filter=Q(status=Status.ESCALATED)),
            ))

            from identity.models import User
            context['personnel_load'] = User.objects.filter(
                department=user.department,
                role=Role.AGENT,
            ).annotate(
                active=Count('assigned_tickets', filter=Q(assigned_tickets__status=Status.IN_PROGRESS)),
            ).order_by('-active')[:10]

            context['recent_tickets'] = dept_tickets.select_related(
                'sender', 'assigned_to'
            )[:5]

        elif user.role == Role.ADMIN:
            context.update(Ticket.objects.aggregate(
                total_tickets=Count('pk'),
                total_open=Count('pk', filter=Q(status=Status.OPEN)),
                total_in_progress=Count('pk', filter=Q(status=Status.IN_PROGRESS)),
                total_resolved=Count('pk', filter=Q(status=Status.RESOLVED)),
                total_closed=Count('pk', filter=Q(status=Status.CLOSED)),
                total_escalated=Count('pk', filter=Q(status=Status.ESCALATED)),
            ))

            from identity.models import User
            context['pending_users_count'] = User.objects.filter(is_active=False).count()

            from departments.models import Department
            context['dept_summary'] = Department.objects.annotate(
                open_count=Count('tickets', filter=Q(tickets__status=Status.OPEN)),
                total_count=Count('tickets'),
            ).order_by('-open_count')

            context['recent_tickets'] = Ticket.objects.select_related(
                'sender', 'department', 'assigned_to'
            )[:5]

        return context
