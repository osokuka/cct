# Generated manually to fix Route model schema
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_fix_route_compounds"),
    ]

    operations = [
        # Drop all indexes that reference compound_id
        migrations.RunSQL(
            "DROP INDEX IF EXISTS accounts_route_compound_id_7be49bf4;",
            reverse_sql="CREATE INDEX accounts_route_compound_id_7be49bf4 ON accounts_route (compound_id);"
        ),
        migrations.RunSQL(
            "DROP INDEX IF EXISTS accounts_route_team_id_shift_id_compound_id_b4d8912e_uniq;",
            reverse_sql="CREATE UNIQUE INDEX accounts_route_team_id_shift_id_compound_id_b4d8912e_uniq ON accounts_route (team_id, shift_id, compound_id);"
        ),
        # Then drop the compound_id column (already removed by the RemoveField in
        # 0003 on fresh databases, so guard with IF EXISTS to stay idempotent).
        migrations.RunSQL(
            "ALTER TABLE accounts_route DROP COLUMN IF EXISTS compound_id;",
            reverse_sql="ALTER TABLE accounts_route ADD COLUMN compound_id char(32);"
        ),
    ]
