from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0006_portalconfiguration"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidateanalysisartifact",
            name="content",
            field=models.BinaryField(blank=True, null=True),
        ),
    ]
