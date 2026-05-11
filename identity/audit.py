from .models import AuditLog


AuditCategory = AuditLog.Category


def _client_ip(request):
    if not request:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def audit_log(request, category, action, target=None, actor=None,
              department=None, ticket=None):
    if actor is None and request is not None:
        u = getattr(request, 'user', None)
        if u is not None and u.is_authenticated:
            actor = u

    target_repr = ''
    if target is not None:
        try:
            target_repr = str(target)[:200]
        except Exception:
            target_repr = ''

    AuditLog.objects.create(
        actor=actor,
        category=category,
        action=action[:300],
        target_repr=target_repr,
        department=department,
        ticket=ticket,
        ip_address=_client_ip(request),
    )
