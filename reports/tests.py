from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.urls import reverse

from departments.models import Department
from identity.models import Role, User
from tickets.models import Priority, Ticket

TZ = ZoneInfo('Europe/Istanbul')


def dt(day, hour, minute=0):
    # 2026-01-05 Pazartesi
    return datetime(2026, 1, day, hour, minute, tzinfo=TZ)


class ReportDashboardFrtTests(TestCase):
    """Rapor panelindeki ilk yanıt (FRT) metrikleri."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='BT')
        cls.employee = User.objects.create_user(
            'calisan', password='x', role=Role.EMPLOYEE, department=cls.dept,
        )
        cls.agent = User.objects.create_user(
            'ajan', password='x', role=Role.AGENT, department=cls.dept,
        )
        cls.manager = User.objects.create_user(
            'yonetici', password='x', role=Role.MANAGER, department=cls.dept,
        )

    def make_ticket(self, priority, created, responded=None):
        ticket = Ticket.objects.create(
            subject='Test', message='x', sender=self.employee,
            department=self.dept, assigned_to=self.agent, priority=priority,
        )
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=created, first_response_at=responded,
        )
        return ticket

    def dashboard(self, user=None):
        self.client.force_login(user or self.manager)
        response = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_average_is_business_hours_not_wall_clock(self):
        # Cuma 17:00 -> Pazartesi 10:00: takvimde 65 saat, iş saatinde 2 saat.
        self.make_ticket(Priority.NORMAL, dt(9, 17), dt(12, 10))
        context = self.dashboard()
        self.assertEqual(context['frt_count'], 1)
        self.assertEqual(context['frt_avg_label'], '2 saat')

    def test_compliance_counts_breaches_per_priority_target(self):
        # Acil hedefi 1 iş saati: 2 saat ihlal, 30 dk uyumlu.
        self.make_ticket(Priority.URGENT, dt(5, 9), dt(5, 11))
        self.make_ticket(Priority.URGENT, dt(6, 9), dt(6, 9, 30))
        context = self.dashboard()
        self.assertEqual(context['frt_count'], 2)
        self.assertEqual(context['frt_breach'], 1)
        self.assertEqual(context['frt_compliance_pct'], 50.0)

    def test_unanswered_overdue_tickets_are_counted(self):
        self.make_ticket(Priority.URGENT, dt(5, 9))  # yanıtsız, tarih geçmiş
        context = self.dashboard()
        self.assertEqual(context['frt_count'], 0)
        self.assertIsNone(context['frt_avg_label'])
        self.assertEqual(context['frt_awaiting_breached'], 1)

    def test_personnel_table_reports_agent_average(self):
        self.make_ticket(Priority.NORMAL, dt(5, 9), dt(5, 12))
        context = self.dashboard()
        row = next(p for p in context['personnel'] if p['pk'] == self.agent.pk)
        self.assertEqual(row['avg_frt_label'], '3 saat')

    def test_dashboard_without_any_data_renders(self):
        context = self.dashboard()
        self.assertEqual(context['frt_count'], 0)
        self.assertIsNone(context['frt_compliance_pct'])
