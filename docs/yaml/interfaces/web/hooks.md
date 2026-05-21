# Webhooks Configuration (Incoming HTTP Requests)

The Web Hooks interface spins up a local asynchronous HTTP server (using `aiohttp`) to receive incoming POST/GET requests from external automation services (such as GitHub Actions, Stripe, Smart Home, or IFTTT) without needing custom API integrations.

## Security and Authorization
Each incoming request must contain an authorization token matching the `WEBHOOK_SECRET` key specified in the `.env` file.
The token can be passed in two ways:
1. In the query parameters: `?token=SECRET`
2. In the HTTP headers: `Authorization: Bearer SECRET`

Requests without a valid token are rejected with a `401 Unauthorized` HTTP status, and unauthorized access attempts are logged.

## Network Accessibility (Reverse Proxy)
By default, the server listens to the local loopback interface (`host: "127.0.0.1"`). This means it only accepts requests initiated from the same host machine.

To accept webhooks from the public Internet, **it is highly discouraged** to modify `host` to `0.0.0.0`. Instead, a secure Reverse Proxy should be used.

### Method 1: Using ngrok (For testing and local PCs)
The `ngrok` utility generates a public HTTPS URL and tunnels traffic directly to your local port:
```bash
ngrok http 8080
```
External services can then call the generated URL:
`https://<random_id>.ngrok-free.app/webhook/github_action?token=SECRET`

### Method 2: Using Nginx (For VPS servers)
The recommended production setup. Nginx terminates SSL encryption and forwards traffic to the local JAWL port.

Example `nginx.conf` block:
```nginx
server {
    listen 443 ssl;
    server_name my-agent.com;

    ssl_certificate /etc/letsencrypt/live/my-agent.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/my-agent.com/privkey.pem;

    location /webhook/ {
        proxy_pass http://127.0.0.1:8080/webhook/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```