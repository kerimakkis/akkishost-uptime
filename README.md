# AkkisHost Uptime Monitor

External uptime monitoring for AkkisHost websites using GitHub Actions.

## Features

-  Automated daily checks at 07:15 Berlin time
-  Email notifications to `akkisgreen@gmail.com`
- JSON report artifacts
-  Async HTTP checks with retries
-  Supports custom timeouts and status codes

## Monitored Sites

- https://senayakkis.com/
- https://kerimakkis.com/
- https://akkisbau.com/
- https://sevoelektro.com/
- https://www.akkistech.com/

## Setup

### GitHub Secrets

To enable email notifications, add these secrets to your GitHub repository:

1. Go to: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

2. Add the following secrets:

   - **EMAIL_USERNAME**: Your Gmail address (e.g., `akkisgreen@gmail.com`)
   - **EMAIL_PASSWORD**: Gmail App Password (see below)

### Gmail App Password

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Step Verification (if not already enabled)
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Create a new app password for "Mail"
5. Copy the generated password and use it as `EMAIL_PASSWORD` secret

### Optional: Slack Notifications

Add `SLACK_WEBHOOK_URL` secret for Slack notifications.

## Manual Testing

Run locally:

```bash
cd monitor
pip install aiohttp pyyaml
python check_sites.py --config sites.yml --json report.json
```

## Adding New Sites

Edit `monitor/sites.yml` and add new entries:

```yaml
sites:
  - url: https://example.com/
    expected_status: 200
```

Then commit and push to trigger the workflow.

## License

MIT
