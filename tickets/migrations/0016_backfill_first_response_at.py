from django.db import migrations

# Rol değerleri migration içinde bilinçli olarak literal: migration'lar uygulama
# kodundaki enum'a bağlanmamalı, aksi halde enum ileride değişirse geçmiş
# migration'ın davranışı da değişir.
STAFF_ROLES = ('AGENT', 'MANAGER', 'ADMIN')


def backfill(apps, schema_editor):
    """Geçmiş biletlere ilk yanıt damgası atar.

    İlk yanıt = talep sahibi dışındaki bir personelin yazdığı ilk *genel*
    (dahili olmayan) yorum. Hiç yorum yoksa çözüm tarihi ilk yanıt sayılır;
    mark_resolved() da canlıda aynı kuralı uyguluyor.
    """
    Ticket = apps.get_model('tickets', 'Ticket')
    TicketComment = apps.get_model('tickets', 'TicketComment')

    first_by_ticket = {}
    comments = (
        TicketComment.objects
        .filter(is_internal=False, author__isnull=False)
        .filter(author__role__in=STAFF_ROLES)
        .order_by('ticket_id', 'created_at')
        .values_list('ticket_id', 'author_id', 'created_at')
    )
    for ticket_id, author_id, created_at in comments.iterator():
        if ticket_id not in first_by_ticket:
            first_by_ticket[ticket_id] = (author_id, created_at)

    to_update = []
    qs = Ticket.objects.filter(first_response_at__isnull=True).only(
        'pk', 'sender_id', 'resolved_at', 'closed_at',
    )
    for ticket in qs.iterator():
        stamp = None
        hit = first_by_ticket.get(ticket.pk)
        # Talep sahibinin kendi kendine yazdığı yorum yanıt sayılmaz.
        if hit and hit[0] != ticket.sender_id:
            stamp = hit[1]
        elif ticket.resolved_at:
            stamp = ticket.resolved_at
        elif ticket.closed_at:
            stamp = ticket.closed_at
        if stamp is not None:
            ticket.first_response_at = stamp
            to_update.append(ticket)

    if to_update:
        Ticket.objects.bulk_update(to_update, ['first_response_at'], batch_size=500)


def noop(apps, schema_editor):
    """Geri alma: damgaları temizlemek veri kaybı olur, alan zaten silinecek."""


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0015_frt_internal_notes_canned_responses'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
