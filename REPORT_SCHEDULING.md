# Report Scheduling

This schedules the comprehensive project report to regenerate every hour.

## Cron entry

Replace `rick` with your username if different.

```cron
# m h  dom mon dow   command
0 * * * * /bin/bash -lc '/home/rick/ozzy-simple/scripts/generate_project_report_cron.sh'
```

Notes:

- The script uses the repo's virtualenv at `/home/rick/ozzy-simple/venv`.
- Logs are written to `/home/rick/ozzy-simple/logs/report_cron.log`.
- You can run it on demand:

```bash
/home/rick/ozzy-simple/scripts/generate_project_report_cron.sh
```
