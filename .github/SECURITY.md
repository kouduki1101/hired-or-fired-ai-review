# Security Policy

This policy covers the **AIOS** multi-agent operations platform under [`aios/`](../aios).

## Reporting a Vulnerability

Please report security issues **privately**. Do not open public issues for
suspected vulnerabilities.

- Preferred: [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
  (Security → Report a vulnerability) on this repository.
- Include: affected component, version/commit, reproduction steps, impact, and
  any PoC. Please allow **90 days** for remediation before public disclosure.

We aim to acknowledge reports within **3 business days** and to provide a
remediation timeline within **10 business days**.

## Supported Versions

AIOS is pre-1.0. Security fixes target the `main` branch and the latest
released `aios-sdk`. Older tags are not maintained.

## Scope

| In scope | Out of scope |
|---|---|
| `aios/apps/api` (Control Plane API) | The "Hired or Fired" game under repo root (separate product) |
| `aios/apps/orchestrator`, `aios/packages/*` | Third-party dependencies (report upstream; we track via `security-audit` CI) |
| `aios/apps/dashboard` | Denial-of-service via unthrottled load against test deployments |
| Authn/authz, tenant isolation, audit-chain integrity | Social engineering, physical attacks |

Detailed rules of engagement for commissioned penetration tests:
[`aios/docs/security/pentest_scope.md`](../aios/docs/security/pentest_scope.md).

## Security Controls (summary)

See the threat model in [`aios/docs/09_security.md`](../aios/docs/09_security.md).
Highlights: API-key + OIDC/RBAC authn/z, ContextVar-propagated tenant isolation,
SHA-256 hash-chained audit events (append-only, no delete API by design),
HMAC-signed webhooks, strict security headers, and dependency vulnerability
scanning in CI.
