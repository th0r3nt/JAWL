# Email Configuration (Mail)

The `email` interface transforms the agent into a personal assistant capable of reading, analyzing, and sending emails. The system automatically parses MIME structures and extracts clean text, stripping HTML clutter to save context tokens.

## Authorization (Important)
In your `.env` file, specify login and password:
* `EMAIL_ACCOUNT="agent.jawl@gmail.com"`
* `EMAIL_PASSWORD="app_password_here"`

**Critically Important:** If you use Gmail, Yandex, or Mail.ru, your regular account password **will not work**. Providers block access via scripts using regular passwords. You must enable two-factor authentication (2FA) in your email settings and generate a dedicated **"App Password"**.

The system will automatically resolve IMAP and SMTP servers based on the email domain (supports gmail, yandex, mail.ru, outlook).

## Parameters (`email`)

* **`enabled`**: `true` / `false`.
* **`polling_interval_sec`**: How often (in seconds) to poll the server for new emails. Default is 60.
* **`recent_limit`**: How many of the latest emails to display on the dashboard. Headers (Subject) and senders are populated automatically.