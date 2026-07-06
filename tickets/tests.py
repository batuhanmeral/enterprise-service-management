from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase

from departments.models import Department
from identity.models import Role, User
from tickets.models import (
    MAX_ACTIVE_TICKETS_PER_AGENT, MAX_REOPENS, Priority, Status, Ticket,
    add_business_hours, business_seconds_between,
)

TZ = ZoneInfo('Europe/Istanbul')


def dt(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


# 2026-01-05 Pazartesi
MON = lambda h, m=0: dt(2026, 1, 5, h, m)
TUE = lambda h, m=0: dt(2026, 1, 6, h, m)
WED = lambda h, m=0: dt(2026, 1, 7, h, m)
FRI = lambda h, m=0: dt(2026, 1, 9, h, m)
SAT = lambda h, m=0: dt(2026, 1, 10, h, m)
SUN = lambda h, m=0: dt(2026, 1, 11, h, m)
NEXT_MON = lambda h, m=0: dt(2026, 1, 12, h, m)


class AddBusinessHoursTests(SimpleTestCase):

    def test_within_single_work_day(self):
        self.assertEqual(add_business_hours(MON(10), 4), MON(14))

    def test_spills_over_to_next_work_day(self):
        # Pazartesi 16:00 + 4s -> 2s aynı gün (18:00'e kadar), 2s Salı 09:00'dan
        self.assertEqual(add_business_hours(MON(16), 4), TUE(11))

    def test_spans_weekend(self):
        # Cuma 17:00 + 4s -> 1s Cuma, kalan 3s Pazartesi
        self.assertEqual(add_business_hours(FRI(17), 4), NEXT_MON(12))

    def test_start_on_weekend_moves_to_monday(self):
        self.assertEqual(add_business_hours(SAT(12), 4), NEXT_MON(13))
        self.assertEqual(add_business_hours(SUN(9), 4), NEXT_MON(13))

    def test_start_before_work_hours_clamps_to_day_start(self):
        self.assertEqual(add_business_hours(MON(7, 30), 4), MON(13))

    def test_start_after_work_hours_moves_to_next_day(self):
        self.assertEqual(add_business_hours(MON(19), 2), TUE(11))

    def test_multi_day_sla(self):
        # 24 iş saati, günde 9 saat: Pzt 9 + Sal 9 + Çar 6 -> Çarşamba 15:00
        self.assertEqual(add_business_hours(MON(9), 24), WED(15))


class BusinessSecondsBetweenTests(SimpleTestCase):

    def test_same_day(self):
        self.assertEqual(business_seconds_between(MON(10), MON(12)), 7200)

    def test_end_before_start_is_zero(self):
        self.assertEqual(business_seconds_between(MON(12), MON(10)), 0)

    def test_ignores_weekend(self):
        self.assertEqual(business_seconds_between(SAT(10), SUN(15)), 0)

    def test_spans_weekend(self):
        # Cuma 17:00-18:00 (1s) + Pazartesi 09:00-10:00 (1s)
        self.assertEqual(business_seconds_between(FRI(17), NEXT_MON(10)), 7200)

    def test_clamps_to_work_hours(self):
        self.assertEqual(business_seconds_between(MON(8), MON(10)), 3600)
        self.assertEqual(business_seconds_between(MON(17), MON(20)), 3600)


class TicketFactoryMixin:

    @classmethod
    def create_department(cls, name='BT', **kwargs):
        return Department.objects.create(name=name, **kwargs)

    @classmethod
    def create_user(cls, username, role, department=None):
        return User.objects.create_user(
            username=username, password='x', role=role, department=department,
        )

    @classmethod
    def create_ticket(cls, sender, department=None, **kwargs):
        return Ticket.objects.create(
            subject='Test bileti', message='Açıklama',
            sender=sender, department=department, **kwargs
        )


class TicketSlaTests(TicketFactoryMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)

    def test_save_sets_sla_due_date(self):
        ticket = self.create_ticket(self.employee, self.dept, priority=Priority.URGENT)
        self.assertIsNotNone(ticket.sla_due_at)
        self.assertGreater(ticket.sla_due_at, ticket.created_at)

    def test_priority_orders_sla_due_dates(self):
        urgent = self.create_ticket(self.employee, self.dept, priority=Priority.URGENT)
        low = self.create_ticket(self.employee, self.dept, priority=Priority.LOW)
        self.assertLess(urgent.sla_due_at, low.sla_due_at)

    def test_priority_change_recomputes_sla_even_with_update_fields(self):
        ticket = self.create_ticket(self.employee, self.dept, priority=Priority.LOW)
        old_due = ticket.sla_due_at
        ticket.priority = Priority.URGENT
        ticket.save(update_fields=['priority'])
        ticket.refresh_from_db()
        self.assertLess(ticket.sla_due_at, old_due)

    def test_resolved_ticket_is_never_overdue(self):
        ticket = self.create_ticket(self.employee, self.dept)
        ticket.status = Status.RESOLVED
        ticket.sla_due_at = ticket.created_at - timedelta(hours=1)
        self.assertFalse(ticket.is_overdue)


class AutoAssignTests(TicketFactoryMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)
        cls.a1 = cls.create_user('ajan1', Role.AGENT, cls.dept)
        cls.a2 = cls.create_user('ajan2', Role.AGENT, cls.dept)
        cls.a3 = cls.create_user('ajan3', Role.AGENT, cls.dept)

    def give_active_tickets(self, agent, count):
        for _ in range(count):
            self.create_ticket(
                self.employee, self.dept,
                assigned_to=agent, status=Status.IN_PROGRESS,
            )

    def test_picks_least_loaded_agent(self):
        self.give_active_tickets(self.a1, 2)
        self.give_active_tickets(self.a3, 1)
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertEqual(ticket.auto_assign(), self.a2)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_to, self.a2)
        self.assertEqual(ticket.status, Status.IN_PROGRESS)

    def test_round_robin_breaks_ties(self):
        self.dept.last_auto_assigned = self.a1
        self.dept.save(update_fields=['last_auto_assigned'])
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertEqual(ticket.auto_assign(), self.a2)
        self.dept.refresh_from_db()
        self.assertEqual(self.dept.last_auto_assigned, self.a2)

    def test_round_robin_wraps_to_first_agent(self):
        self.dept.last_auto_assigned = self.a3
        self.dept.save(update_fields=['last_auto_assigned'])
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertEqual(ticket.auto_assign(), self.a1)

    def test_respects_active_ticket_cap(self):
        for agent in (self.a1, self.a2, self.a3):
            self.give_active_tickets(agent, MAX_ACTIVE_TICKETS_PER_AGENT)
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertIsNone(ticket.auto_assign())
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assigned_to)
        self.assertEqual(ticket.status, Status.OPEN)

    def test_disabled_department_assigns_nobody(self):
        self.dept.auto_assign_enabled = False
        self.dept.save(update_fields=['auto_assign_enabled'])
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertIsNone(ticket.auto_assign())

    def test_never_assigns_ticket_to_its_sender(self):
        dept = self.create_department('İK')
        agent = self.create_user('tek_ajan', Role.AGENT, dept)
        ticket = self.create_ticket(agent, dept)
        self.assertIsNone(ticket.auto_assign())


class TicketLifecycleTests(TicketFactoryMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)
        cls.agent = cls.create_user('ajan', Role.AGENT, cls.dept)

    def resolved_ticket(self):
        ticket = self.create_ticket(self.employee, self.dept)
        ticket.take_into_process(self.agent)
        ticket.mark_resolved('Çözüldü')
        return ticket

    def test_confirm_resolution_closes_ticket(self):
        ticket = self.resolved_ticket()
        ticket.confirm_resolution()
        self.assertEqual(ticket.status, Status.CLOSED)
        self.assertTrue(ticket.resolution_confirmed)
        self.assertIsNotNone(ticket.closed_at)

    def test_reject_resolution_requires_reason(self):
        ticket = self.resolved_ticket()
        with self.assertRaises(ValueError):
            ticket.reject_resolution('  ')

    def test_reject_resolution_reopens_until_limit(self):
        ticket = self.resolved_ticket()
        for expected_count in range(1, MAX_REOPENS + 1):
            self.assertTrue(ticket.reject_resolution('Olmadı'))
            self.assertEqual(ticket.reopen_count, expected_count)
            self.assertEqual(ticket.status, Status.IN_PROGRESS)
            ticket.mark_resolved('Tekrar çözüldü')

    def test_rejection_past_limit_escalates(self):
        ticket = self.resolved_ticket()
        for _ in range(MAX_REOPENS):
            ticket.reject_resolution('Olmadı')
            ticket.mark_resolved('Tekrar çözüldü')
        self.assertFalse(ticket.reject_resolution('Hâlâ olmadı'))
        self.assertEqual(ticket.status, Status.ESCALATED)
        self.assertIsNotNone(ticket.escalated_at)
        self.assertTrue(ticket.is_locked)

    def test_reopen_resets_resolution_state(self):
        ticket = self.resolved_ticket()
        ticket.confirm_resolution()
        ticket.reopen()
        self.assertEqual(ticket.status, Status.OPEN)
        self.assertIsNone(ticket.assigned_to)
        self.assertIsNone(ticket.closed_at)
        self.assertIsNone(ticket.resolved_at)
        self.assertEqual(ticket.reopen_count, 0)

    def test_csat_only_on_closed_tickets(self):
        ticket = self.resolved_ticket()
        with self.assertRaises(ValueError):
            ticket.set_csat(5)
        ticket.confirm_resolution()
        with self.assertRaises(ValueError):
            ticket.set_csat(6)
        ticket.set_csat(4)
        self.assertEqual(ticket.csat_rating, 4)
