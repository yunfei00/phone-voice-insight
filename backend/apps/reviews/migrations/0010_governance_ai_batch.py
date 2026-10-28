from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('reviews', '0009_governance_ai_review'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='GovernanceAIBatch', fields=[
        ('id', models.BigAutoField(primary_key=True, serialize=False)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('quality_ids', models.JSONField(default=list)),
        ('status', models.CharField(max_length=16, default='PENDING', db_index=True, choices=[('PENDING','等待执行'),('RUNNING','执行中'),('SUCCESS','完成'),('PARTIAL','部分失败'),('FAILED','失败')])),
        ('celery_task_id', models.CharField(max_length=100, blank=True)),
        ('total', models.PositiveIntegerField(default=0)),
        ('processed', models.PositiveIntegerField(default=0)),
        ('succeeded', models.PositiveIntegerField(default=0)),
        ('review_required', models.PositiveIntegerField(default=0)),
        ('failed', models.PositiveIntegerField(default=0)),
        ('failure_ids', models.JSONField(default=list)),
        ('error_code', models.CharField(max_length=80, blank=True)),
        ('started_at', models.DateTimeField(null=True, blank=True)),
        ('finished_at', models.DateTimeField(null=True, blank=True)),
        ('product', models.ForeignKey(to='products.product', on_delete=django.db.models.deletion.PROTECT, related_name='governance_ai_batches')),
        ('requested_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
    ], options={'ordering': ('-created_at', '-id')})]
