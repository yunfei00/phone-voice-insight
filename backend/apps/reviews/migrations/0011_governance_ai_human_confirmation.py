from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('reviews', '0010_governance_ai_batch'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='governanceaireview', name='human_decision', field=models.BooleanField(null=True, blank=True)),
        migrations.AddField(model_name='governanceaireview', name='human_reason', field=models.TextField(blank=True)),
        migrations.AddField(model_name='governanceaireview', name='human_reviewer', field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
        migrations.AddField(model_name='governanceaireview', name='human_reviewed_at', field=models.DateTimeField(null=True, blank=True)),
    ]
