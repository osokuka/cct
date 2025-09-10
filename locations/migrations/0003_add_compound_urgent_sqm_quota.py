# Generated manually for compound urgent SQM quota fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0002_alter_camp_month_cutoff_day_alter_camp_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='compound',
            name='monthly_urgent_sqm_quota',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Monthly SQM quota for urgent cleaning requests (optional)',
                max_digits=10,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='compound',
            name='weekly_urgent_sqm_quota',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Weekly SQM quota for urgent cleaning requests (optional)',
                max_digits=10,
                null=True
            ),
        ),
    ]
