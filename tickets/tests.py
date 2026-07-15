from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from departments.models import Category, Department
from identity.models import Role, User
from tickets.models import (
    MAX_ACTIVE_TICKETS_PER_AGENT, MAX_REOPENS, CannedResponse, Priority, Status,
    Ticket, TicketComment, add_business_hours, business_seconds_between,
    format_duration_short,
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


class FirstResponseTimeTests(TicketFactoryMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)
        cls.agent = cls.create_user('ajan', Role.AGENT, cls.dept)

    def test_new_ticket_has_no_first_response(self):
        ticket = self.create_ticket(self.employee, self.dept)
        self.assertIsNone(ticket.first_response_at)
        self.assertTrue(ticket.awaiting_first_response)
        self.assertEqual(ticket.first_response_label, '—')

    def test_mark_first_response_is_idempotent(self):
        ticket = self.create_ticket(self.employee, self.dept)
        first = ticket.created_at + timedelta(hours=1)
        self.assertTrue(ticket.mark_first_response(at=first))
        # İkinci yanıt metriği bozmamalı — ilk damga korunur.
        self.assertFalse(ticket.mark_first_response(at=first + timedelta(hours=5)))
        ticket.refresh_from_db()
        self.assertEqual(ticket.first_response_at, first)

    def test_duration_measured_in_business_hours(self):
        ticket = self.create_ticket(self.employee, self.dept)
        # Cuma 17:00 -> Pazartesi 10:00 = 1s Cuma + 1s Pazartesi = 2 iş saati,
        # takvim saati olarak 65 saat. Ölçüm iş saatini vermeli.
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=FRI(17), first_response_at=NEXT_MON(10),
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.first_response_seconds, 7200)
        self.assertEqual(ticket.first_response_label, '2 saat')

    def test_breach_flagged_against_priority_target(self):
        ticket = self.create_ticket(self.employee, self.dept, priority=Priority.URGENT)
        # Acil hedefi 1 iş saati; Pazartesi 09:00 -> 11:00 bunu aşar.
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=MON(9), first_response_at=MON(11),
        )
        ticket.refresh_from_db()
        self.assertTrue(ticket.first_response_breached)

        Ticket.objects.filter(pk=ticket.pk).update(first_response_at=MON(9, 30))
        ticket.refresh_from_db()
        self.assertFalse(ticket.first_response_breached)

    def test_resolving_without_comment_stamps_first_response(self):
        ticket = self.create_ticket(self.employee, self.dept)
        ticket.take_into_process(self.agent)
        ticket.mark_resolved('Çözüldü')
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.first_response_at)
        self.assertEqual(ticket.first_response_at, ticket.resolved_at)

    def test_resolving_does_not_overwrite_existing_stamp(self):
        ticket = self.create_ticket(self.employee, self.dept)
        first = ticket.created_at + timedelta(minutes=10)
        ticket.mark_first_response(at=first)
        ticket.take_into_process(self.agent)
        ticket.mark_resolved('Çözüldü')
        ticket.refresh_from_db()
        self.assertEqual(ticket.first_response_at, first)

    def test_closed_unanswered_ticket_is_not_flagged(self):
        ticket = self.create_ticket(self.employee, self.dept)
        Ticket.objects.filter(pk=ticket.pk).update(
            created_at=MON(9), status=Status.CLOSED,
        )
        ticket.refresh_from_db()
        self.assertFalse(ticket.awaiting_first_response)
        self.assertFalse(ticket.first_response_breached)


class FormatDurationTests(SimpleTestCase):

    def test_formats(self):
        self.assertEqual(format_duration_short(0), '—')
        self.assertEqual(format_duration_short(30), '< 1 dk')
        self.assertEqual(format_duration_short(45 * 60), '45 dk')
        self.assertEqual(format_duration_short(2 * 3600), '2 saat')
        self.assertEqual(format_duration_short(2 * 3600 + 15 * 60), '2 saat 15 dk')
        self.assertEqual(format_duration_short(26 * 3600), '1 gün 2 saat')


class InternalNoteTests(TicketFactoryMixin, TestCase):
    """Dahili notun asıl sözleşmesi: talep sahibi onu hiçbir koşulda görmez."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.other_dept = cls.create_department('İK')
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)
        cls.agent = cls.create_user('ajan', Role.AGENT, cls.dept)
        cls.manager = cls.create_user('yonetici', Role.MANAGER, cls.dept)
        cls.other_agent = cls.create_user('ik_ajan', Role.AGENT, cls.other_dept)
        cls.admin = cls.create_user('admin', Role.ADMIN)

    def setUp(self):
        self.ticket = self.create_ticket(self.employee, self.dept)
        self.ticket.take_into_process(self.agent)

    def post_comment(self, user, **data):
        self.client.force_login(user)
        return self.client.post(
            reverse('tickets:ticket_add_comment', args=[self.ticket.pk]),
            data,
        )

    def detail_comments(self, user):
        self.client.force_login(user)
        response = self.client.get(
            reverse('tickets:ticket_detail', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 200)
        return list(response.context['comments'])

    def test_agent_can_post_internal_note(self):
        self.post_comment(self.agent, content='Gizli', is_internal='1')
        note = TicketComment.objects.get(ticket=self.ticket)
        self.assertTrue(note.is_internal)

    def test_employee_cannot_post_internal_note(self):
        response = self.post_comment(self.employee, content='Gizli', is_internal='1')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TicketComment.objects.exists())

    def test_requester_never_sees_internal_notes(self):
        self.post_comment(self.agent, content='Gizli', is_internal='1')
        self.post_comment(self.agent, content='Açık yanıt')
        visible = self.detail_comments(self.employee)
        self.assertEqual([c.content for c in visible], ['Açık yanıt'])

    def test_department_staff_and_admin_see_internal_notes(self):
        self.post_comment(self.agent, content='Gizli', is_internal='1')
        for user in (self.agent, self.manager, self.admin):
            with self.subTest(user=user.username):
                contents = [c.content for c in self.detail_comments(user)]
                self.assertIn('Gizli', contents)

    def test_staff_requester_does_not_see_notes_on_own_ticket(self):
        """Kendi departmanına bilet açan personel o bilette talep sahibidir."""
        ticket = self.create_ticket(self.agent, self.dept)
        TicketComment.objects.create(
            ticket=ticket, author=self.manager, content='Gizli', is_internal=True,
        )
        self.client.force_login(self.agent)
        response = self.client.get(reverse('tickets:ticket_detail', args=[ticket.pk]))
        self.assertEqual([c.content for c in response.context['comments']], [])
        self.assertFalse(response.context['can_post_internal'])

    def test_internal_note_does_not_notify_requester(self):
        from notifications.models import Notification
        self.post_comment(self.agent, content='Gizli', is_internal='1')
        self.assertFalse(
            Notification.objects.filter(recipient=self.employee).exists()
        )
        self.assertTrue(Notification.objects.filter(recipient=self.manager).exists())

    def test_internal_note_does_not_count_as_first_response(self):
        self.post_comment(self.agent, content='Gizli', is_internal='1')
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.first_response_at)

        self.post_comment(self.agent, content='Merhaba, bakıyorum.')
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.first_response_at)

    def test_requester_comment_does_not_count_as_first_response(self):
        self.post_comment(self.employee, content='Ek bilgi')
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.first_response_at)


class CannedResponseTests(TicketFactoryMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.dept = cls.create_department()
        cls.other_dept = cls.create_department('İK')
        cls.employee = cls.create_user('calisan', Role.EMPLOYEE)
        cls.agent = cls.create_user('ajan', Role.AGENT, cls.dept)
        cls.manager = cls.create_user('yonetici', Role.MANAGER, cls.dept)
        cls.other_agent = cls.create_user('ik_ajan', Role.AGENT, cls.other_dept)
        cls.admin = cls.create_user('admin', Role.ADMIN)

        cls.global_cr = CannedResponse.objects.create(
            title='Genel karşılama', body='Merhaba {{talep_sahibi}}.',
        )
        cls.dept_cr = CannedResponse.objects.create(
            title='BT şifre', body='Şifreniz sıfırlandı.', department=cls.dept,
        )
        cls.other_cr = CannedResponse.objects.create(
            title='İK izin', body='İzin talebiniz alındı.', department=cls.other_dept,
        )
        cls.passive_cr = CannedResponse.objects.create(
            title='Eski metin', body='Kullanılmıyor.', department=cls.dept,
            is_active=False,
        )

    def test_visible_to_scopes_by_department(self):
        visible = set(CannedResponse.objects.visible_to(self.agent))
        self.assertEqual(visible, {self.global_cr, self.dept_cr})

    def test_visible_to_excludes_passive(self):
        self.assertNotIn(
            self.passive_cr, CannedResponse.objects.visible_to(self.manager)
        )

    def test_admin_sees_all_active(self):
        visible = set(CannedResponse.objects.visible_to(self.admin))
        self.assertEqual(visible, {self.global_cr, self.dept_cr, self.other_cr})

    def test_employee_sees_none(self):
        self.assertFalse(CannedResponse.objects.visible_to(self.employee).exists())

    def test_editable_by_manager_limited_to_own_department(self):
        editable = set(CannedResponse.objects.editable_by(self.manager))
        self.assertEqual(editable, {self.dept_cr, self.passive_cr})

    def test_render_fills_placeholders(self):
        ticket = self.create_ticket(self.employee, self.dept)
        cr = CannedResponse.objects.create(
            title='Tam şablon',
            body='{{talep_sahibi}} / {{personel}} / {{bilet_kodu}} / '
                 '{{konu}} / {{departman}}',
        )
        rendered = cr.render_for(ticket, agent=self.agent)
        self.assertEqual(
            rendered,
            f'calisan / ajan / {ticket.code} / Test bileti / BT',
        )

    def test_detail_view_offers_only_visible_responses(self):
        ticket = self.create_ticket(self.employee, self.dept)
        self.client.force_login(self.agent)
        response = self.client.get(reverse('tickets:ticket_detail', args=[ticket.pk]))
        titles = {c['title'] for c in response.context['canned_responses']}
        self.assertEqual(titles, {'Genel karşılama', 'BT şifre'})

    def test_employee_gets_no_canned_responses(self):
        ticket = self.create_ticket(self.employee, self.dept)
        self.client.force_login(self.employee)
        response = self.client.get(reverse('tickets:ticket_detail', args=[ticket.pk]))
        self.assertIsNone(response.context.get('canned_responses'))

    def test_usage_counter_increments_on_comment(self):
        ticket = self.create_ticket(self.employee, self.dept)
        ticket.take_into_process(self.agent)
        self.client.force_login(self.agent)
        self.client.post(
            reverse('tickets:ticket_add_comment', args=[ticket.pk]),
            {'content': 'Şifreniz sıfırlandı.', 'canned_response': self.dept_cr.pk},
        )
        self.dept_cr.refresh_from_db()
        self.assertEqual(self.dept_cr.usage_count, 1)

    def test_usage_counter_ignores_inaccessible_response(self):
        ticket = self.create_ticket(self.employee, self.dept)
        ticket.take_into_process(self.agent)
        self.client.force_login(self.agent)
        self.client.post(
            reverse('tickets:ticket_add_comment', args=[ticket.pk]),
            {'content': 'Metin', 'canned_response': self.other_cr.pk},
        )
        self.other_cr.refresh_from_db()
        self.assertEqual(self.other_cr.usage_count, 0)

    def test_employee_cannot_reach_management_screen(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('tickets:canned_response_list'))
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_edit_other_department_response(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('tickets:canned_response_update', args=[self.other_cr.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_manager_cannot_create_for_other_department(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('tickets:canned_response_create'),
            {
                'title': 'Sızan metin', 'body': 'Metin',
                'department': self.other_dept.pk, 'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)  # form hatayla geri döner
        self.assertFalse(CannedResponse.objects.filter(title='Sızan metin').exists())

    def test_category_must_belong_to_selected_department(self):
        category = Category.objects.create(department=self.other_dept, name='İzin')
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('tickets:canned_response_create'),
            {
                'title': 'Uyumsuz', 'body': 'Metin',
                'department': self.dept.pk, 'category': category.pk,
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CannedResponse.objects.filter(title='Uyumsuz').exists())
