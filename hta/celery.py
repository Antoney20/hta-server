# from __future__ import absolute_import, unicode_literals

# import os
# import logging
# from celery import Celery
# from django.conf import settings

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hta.settings')

# # Create Celery app instance
# app = Celery('hta')

# app.config_from_object('django.conf:settings', namespace='CELERY')

# # Load tasks from all registered Django app configs
# app.autodiscover_tasks()

# # Optional: Configure logging
# logger = logging.getLogger(__name__)

# @app.task(bind=True)
# def debug_task(self):
#     """Debug task to test Celery setup"""
#     print(f'Request: {self.request!r}')

# # Celery beat schedule (if you need periodic tasks)
# app.conf.beat_schedule = {
#     'cleanup-temp-files': {
#         'task': 'users.tasks.cleanup_temp_files',
#         'schedule': 60.0 * 60,  # Run every hour
#     },
#     'cleanup-old-submissions': {
#         'task': 'users.tasks.cleanup_old_submissions', 
#         'schedule': 60.0 * 60 * 24,  # Run daily
#     },
# }

# # # Additional Celery configuration
# # app.conf.update(
# #     # Task execution settings
# #     task_always_eager=False,  # Set to True for synchronous testing
# #     task_eager_propagates=True,
    
# #     # Error handling
# #     task_reject_on_worker_lost=True,
# #     task_acks_late=True,
    
# #     # Result backend settings
# #     result_expires=60 * 60 * 24,  # Results expire after 24 hours
    
# #     # Worker settings
# #     worker_prefetch_multiplier=1,
# #     worker_max_tasks_per_child=1000,
# #     worker_disable_rate_limits=False,
    
# #     # Queue routing
# #     task_default_queue='default',
# #     task_default_exchange='default',
# #     task_default_routing_key='default',
    
# #     # Monitoring
# #     worker_send_task_events=True,
# #     task_send_sent_event=True,
    
# #     # Security
# #     task_serializer='json',
# #     accept_content=['json'],
# #     result_serializer='json',
    
# #     # Timezone
# #     timezone='UTC',
# #     enable_utc=True,
# # )

# # Error handler
# @app.task(bind=True)
# def error_handler(self, uuid):
#     """Handle task errors"""
#     result = self.app.AsyncResult(uuid)
#     logger.error(f'Task {uuid} raised exception: {result.result!r}\n{result.traceback!r}')

# if __name__ == '__main__':
#     app.start()


import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hta.settings')

app = Celery('hta')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()