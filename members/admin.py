from django.contrib import admin
from .models import (
    Announcement,
    Channel,
    Message,
    ChannelMembership,
    ProposalTracker,
    Record,
    Resource,
    Task,
    TaskAssignment,
    ThematicArea,
    ReviewerAssignment,
    ReviewComment,
    Event,
    ImplementationTracking,
)

# Register models in Django admin
admin.site.register(Announcement)
admin.site.register(Channel)
admin.site.register(Message)
admin.site.register(ChannelMembership)
admin.site.register(ProposalTracker)
admin.site.register(Record)
admin.site.register(Resource)
admin.site.register(Task)
admin.site.register(TaskAssignment)
admin.site.register(ThematicArea)
admin.site.register(ReviewerAssignment)
admin.site.register(ReviewComment)
admin.site.register(Event)
admin.site.register(ImplementationTracking)

