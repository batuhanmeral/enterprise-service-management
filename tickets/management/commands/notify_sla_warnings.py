from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from identity.models import Role, User
from notifications.models import Notification
from tickets.models import SLA_HOURS, Status, Ticket


WARN_THRESHOLD_PCT = 75


class Command(BaseCommand):
    help = (
        f'Aktif biletler için SLA hedefinin %{WARN_THRESHOLD_PCT} eşiğine ulaştığında '
        'bir kez proaktif uyarı gönderir. sla_warning_sent_at alanı set edilerek '
        'aynı bilete tekrar uyarı gönderilmesi engellenir. Saatlik çalıştırılmalıdır.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Sadece etkilenecek biletleri raporla, kaydetme.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        threshold_q = Q()
        for prio, hours in SLA_HOURS.items():
            cutoff = now - timedelta(hours=hours * WARN_THRESHOLD_PCT / 100)
            threshold_q |= Q(priority=prio, created_at__lt=cutoff)

        qs = Ticket.objects.filter(
            threshold_q,
            sla_warning_sent_at__isnull=True,
        ).exclude(
            status__in=[Status.RESOLVED, Status.CLOSED, Status.ESCALATED],
        ).select_related('assigned_to', 'department', 'sender')

        candidates = [t for t in qs if t.sla_progress_pct >= WARN_THRESHOLD_PCT]
        self.stdout.write(f'SLA uyarı adayı: {len(candidates)} bilet (eşik=%{WARN_THRESHOLD_PCT})')

        if dry_run:
            for t in candidates:
                self.stdout.write(f'  - {t.code} ({t.priority}) — {t.subject[:40]}')
            return

        notifications = []
        warned_ids = []

        for t in candidates:
            msg = (
                f'⚠️ "{t.subject}" (#{t.pk}) bileti SLA hedefinin %{t.sla_progress_pct}\'ine ulaştı. '
                f'Hedef: {t.sla_due_at.strftime("%d.%m.%Y %H:%M") if t.sla_due_at else "—"}'
            )
            recipients = self._recipients_for(t)
            for r in recipients:
                notifications.append(Notification(recipient=r, ticket=t, message=msg))
            warned_ids.append(t.pk)

        Notification.objects.bulk_create(notifications)
        Ticket.objects.filter(pk__in=warned_ids).update(sla_warning_sent_at=now)
        self.stdout.write(self.style.SUCCESS(
            f'{len(warned_ids)} bilete uyarı gönderildi ({len(notifications)} bildirim).'
        ))

    def _recipients_for(self, ticket):
        if ticket.assigned_to_id:
            return [ticket.assigned_to]
        if not ticket.department_id:
            return []
        return list(User.objects.filter(
            department_id=ticket.department_id,
            role__in=[Role.AGENT, Role.MANAGER],
            is_active=True,
        ))
