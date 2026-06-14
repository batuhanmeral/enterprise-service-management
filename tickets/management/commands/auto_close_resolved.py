from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from tickets.models import (
    AUTO_CLOSE_DAYS,
    Status,
    Ticket,
    TicketActionType,
    TicketHistory,
)


class Command(BaseCommand):
    help = (
        'RESOLVED durumdaki ve resolved_at + AUTO_CLOSE_DAYS süresini geçen biletleri '
        'otomatik olarak CLOSED durumuna alır. Cron veya systemd timer ile periyodik çalıştırılmalıdır '
        '(örn. her saat başı).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Sadece etkilenecek biletleri raporla, kaydetme.',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=AUTO_CLOSE_DAYS)
        qs = Ticket.objects.filter(
            status=Status.RESOLVED,
            resolved_at__isnull=False,
            resolved_at__lte=cutoff,
        ).select_related('sender', 'department')

        total = qs.count()
        self.stdout.write(f'Auto-close adayı: {total} bilet (cutoff={cutoff.isoformat()})')

        if options['dry_run']:
            for t in qs:
                self.stdout.write(f'  - #{t.pk} "{t.subject}" resolved_at={t.resolved_at}')
            return

        closed_count = 0
        for ticket in qs:
            with transaction.atomic():
                ticket.auto_close()
                TicketHistory.objects.create(
                    ticket=ticket,
                    actor=None,
                    action=f'Bilet {AUTO_CLOSE_DAYS} gün içinde onay verilmediği için otomatik kapatıldı.',
                    action_type=TicketActionType.AUTO_CLOSED,
                )
                if ticket.sender:
                    Notification.objects.create(
                        recipient=ticket.sender,
                        ticket=ticket,
                        message=(
                            f'Talebiniz "{ticket.subject}" (#{ticket.pk}) '
                            f'{AUTO_CLOSE_DAYS} gün içinde onay vermediğiniz için otomatik olarak kapandı. '
                            f'Memnuniyet puanı vermeyi unutmayın.'
                        ),
                    )
            closed_count += 1
            self.stdout.write(self.style.SUCCESS(f'  ✓ #{ticket.pk} kapatıldı'))

        self.stdout.write(self.style.SUCCESS(f'Toplam {closed_count} bilet otomatik kapatıldı.'))
