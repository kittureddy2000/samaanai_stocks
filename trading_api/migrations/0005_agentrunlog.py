from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trading_api', '0003_positionsnapshot_trade_filled_avg_price_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentRunLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('run_type', models.CharField(choices=[('analyze', 'Analyze'), ('option_chain', 'Option Chain'), ('daily_summary', 'Daily Summary')], db_index=True, max_length=32)),
                ('status', models.CharField(choices=[('success', 'Success'), ('no_trades', 'No Trades'), ('no_response', 'No Response'), ('skipped', 'Skipped'), ('fallback', 'Fallback'), ('error', 'Error')], db_index=True, max_length=32)),
                ('message', models.TextField(blank=True)),
                ('duration_ms', models.IntegerField(blank=True, null=True)),
                ('market_open', models.BooleanField(blank=True, null=True)),
                ('llm_ok', models.BooleanField(blank=True, db_index=True, null=True)),
                ('llm_error', models.TextField(blank=True)),
                ('trades_recommended', models.IntegerField(blank=True, null=True)),
                ('trades_executed', models.IntegerField(blank=True, null=True)),
                ('symbol', models.CharField(blank=True, max_length=20, null=True)),
                ('option_type', models.CharField(blank=True, max_length=10, null=True)),
                ('strike', models.DecimalField(blank=True, decimal_places=4, max_digits=15, null=True)),
                ('recommendation_source', models.CharField(blank=True, max_length=32, null=True)),
                ('recommendation_candidates', models.IntegerField(blank=True, null=True)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'db_table': 'agent_run_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agentrunlog',
            index=models.Index(fields=['run_type', 'created_at'], name='agent_run_l_run_typ_50509b_idx'),
        ),
        migrations.AddIndex(
            model_name='agentrunlog',
            index=models.Index(fields=['status', 'created_at'], name='agent_run_l_status_804c45_idx'),
        ),
    ]
