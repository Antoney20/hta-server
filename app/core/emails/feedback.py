import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe

from app.models import FeedbackEmailLog

logger = logging.getLogger(__name__)


def _build_context(intervention, category, status_update=None) -> dict:
    """
    Assemble template context from an InterventionProposal.
    Optionally enriched with a specific InterventionStatusUpdate.
    """
    submitter_name = getattr(intervention, "name", None) or (
        intervention.email.split("@")[0]
        if getattr(intervention, "email", None)
        else "Applicant"
    )

    decision      = getattr(status_update, "decision", None)
    decision_date = getattr(status_update, "decision_date", None)
    feedback      = getattr(status_update, "feedback", "") or ""

    return {
        "submitter_name":  submitter_name,
        "submitter_email": getattr(intervention, "email", ""),
        "decision_type":   str(decision) if decision else "",
        "decision_date":   decision_date.strftime("%d %B %Y") if decision_date else "",
        "feedback":        feedback,
        "category_name":   category.name,
        "subject":         category.subject,
        "bptap":        getattr(settings, "ORG_NAME", "BPTAP"),
        "bptap_email":       getattr(settings, "DEFAULT_FROM_EMAIL", "hbtap@uonbi.ac.ke" ),
        "current_year":    timezone.now().year,
    }


def send_feedback_email(intervention, category, status_update=None, sent_by=None) -> bool:
    """
    Render the category's stored body template, wrap it in the base
    layout, send to the proposal submitter, and log the attempt.

    Args:
        intervention:  InterventionProposal instance
        category:      FeedbackCategory instance
        status_update: InterventionStatusUpdate instance (optional)
        sent_by:       User who triggered the send (optional)

    Returns:
        True on success, False on failure.
    """

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "hbtap@uonbi.ac.ke")
    recipient  = getattr(intervention, "email", None)

    if not recipient:
        logger.error(
            "send_feedback_email: intervention %s has no email — skipping.",
            intervention.pk,
        )
        return False

    ctx = _build_context(intervention, category, status_update)

    try:
        # ── Step 1: render the subject line (may contain template vars) ──
        rendered_subject = Template(category.subject).render(Context(ctx))

        # ── Step 2: render the DB body template ──────────────────────────
        rendered_body = Template(category.template).render(Context(ctx))

        # ── Step 3: inject body into the on-disk base layout ─────────────
        #   mark_safe so the base template renders it as HTML, not escaped text
        layout_ctx = {**ctx, "body_content": mark_safe(rendered_body)}
        rendered_html = render_to_string("emails/feedback_base.html", layout_ctx)

    except Exception as render_exc:
        logger.error(
            "send_feedback_email: render failed for category '%s': %s",
            category.name, render_exc,
        )
        return False

    log = FeedbackEmailLog.objects.create(
        intervention=intervention,
        category=category,
        subject_sent=rendered_subject,
        message_sent=rendered_html,
        recipient=recipient,
        sender=from_email,
        sent_by=sent_by,
        status="initial",
    )

    try:
        logger.info(
            "Sending feedback email [%s] to %s (intervention=%s)",
            category.name, recipient, intervention.pk,
        )
        log.mark_sending()

        email = EmailMultiAlternatives(
            subject=rendered_subject,
            body="",
            from_email=from_email,
            to=[recipient],
        )
        email.attach_alternative(rendered_html, "text/html")
        email.send(fail_silently=False)

        log.mark_sent()
        logger.info(
            "Feedback email [%s] sent successfully to %s",
            category.name, recipient,
        )
        return True

    except (SMTPException, Exception) as exc:
        log.mark_failed(exc)
        logger.error(
            "Failed to send feedback email [%s] to %s — %s",
            category.name, recipient, exc,
        )
        return False