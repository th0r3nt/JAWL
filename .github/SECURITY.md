# Security Policy

## Supported Versions

Currently, only the latest version of JAWL is actively supported with security updates.

| Version | Supported          |
| ------- | ------------------ |
| >= 0.9.5| :white_check_mark: |
| < 0.9.3.1 | :x:                |

## Reporting a Vulnerability

JAWL is an autonomous AI agent framework with direct access to the Host OS. Security is our top priority, especially regarding the `validate_sandbox_path` (Gatekeeper) mechanism and `Deploy Sessions`.

If you discover a security vulnerability (e.g., a way for the agent to bypass the `sandbox/` directory when `access_level` is 0 or 1, or unauthorized arbitrary code execution via prompts), please **DO NOT** open a public issue.

Instead, please report it privately:
1. Go to the **Security** tab of this repository.
2. Click on **Advisories** in the left sidebar.
3. Click the **Report a vulnerability** button to open a private draft security advisory.

Alternatively, you can reach out directly via email to: `ivancernomasencev77@gmail.com`

We will investigate all legitimate reports and do our best to quickly issue a patch.