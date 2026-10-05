import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="clothroll",
            name="version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="WeightAuditLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("changed_by_name", models.CharField(blank=True, default="", max_length=150)),
                ("old_value", models.PositiveIntegerField()),
                ("new_value", models.PositiveIntegerField()),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="weight_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "roll",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="weight_audits",
                        to="core.clothroll",
                    ),
                ),
            ],
            options={
                "ordering": ["-changed_at", "-id"],
            },
        ),
    ]
