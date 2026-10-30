from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("assistant", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="AssistantModelSelection",
            fields=[
                ("slot", models.CharField(default="assistant", max_length=32, primary_key=True, serialize=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="assistant.assistantmodelprofile")),
            ],
        ),
    ]
