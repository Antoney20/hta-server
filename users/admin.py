from django.contrib import admin

from django.contrib import admin


from .models import (
    CustomUser,
    InterventionProposal,
    Member,
    ProposalSubmission,
    TemporaryFile,
    ProposalDocument,
    FAQ,
    News,
    Governance,
    MediaResource,
    ContactSubmission,
    NewsletterSubscription,
)

admin.site.register(CustomUser)
admin.site.register(InterventionProposal)
admin.site.register(Member)
admin.site.register(TemporaryFile)
admin.site.register(ProposalDocument)
admin.site.register(FAQ)
admin.site.register(News)
admin.site.register(Governance)
admin.site.register(MediaResource)
admin.site.register(ContactSubmission)
admin.site.register(NewsletterSubscription)


@admin.register(ProposalSubmission)
class ProposalSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "submission_id",
        "proposal",
        "status",
        "attempts",
        "max_attempts",
        "task_id",
        "submitted_at",
        "processing_started_at",
        "completed_at",
        "error_summary",
    )
    list_filter = ("status", "submitted_at")
    search_fields = ("submission_id", "proposal__title", "proposal__email")
    readonly_fields = (
        "submission_id",
        "submitted_at",
        "processing_started_at",
        "completed_at",
        "task_id",
        "attempts",
        "error_message",
    )
    ordering = ("-submitted_at",)

    @admin.display(description="Error Summary")
    def error_summary(self, obj):
        if obj.error_message:
            return (obj.error_message[:70] + "...") if len(obj.error_message) > 70 else obj.error_message
        return "—"

    fieldsets = (
        ("Submission Info", {
            "fields": (
                "submission_id",
                "proposal",
                "status",
                "attempts",
                "max_attempts",
                "task_id",
            ),
        }),
        ("Processing Details", {
            "fields": (
                "submitted_at",
                "processing_started_at",
                "completed_at",
            ),
        }),
        ("Error / Logs", {
            "fields": ("error_message",),
        }),
    )
