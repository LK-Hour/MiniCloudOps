# Security Policy

MiniOps is an academic project that runs on localhost. It still follows basic production security practices (docs/MiniCloudOps.md §16).

## Reporting a vulnerability

Don't open a public issue for a security problem. Contact the maintainers privately through the team channel, or use GitHub's **Report a vulnerability** (private security advisory) on this repository. Include the steps to reproduce and which service is affected.

## Built-in practices

- **Secrets:** credentials live in `.env`, which is never committed. Only `.env.example`, with placeholders, is in git.
- **Database isolation:** each service has its own database user. PostgreSQL is on the internal Docker network only and is never published to the host.
- **Network exposure:** only the gateway, frontend, Grafana and Prometheus are published. The microservices are internal.
- **Input validation:** every request body is validated with Pydantic.
- **Logging:** passwords, tokens and connection strings must never be logged.
- **SSRF protection:** the Target Service must reject monitoring URLs that point at internal or sensitive addresses (loopback, link-local, cloud metadata, private ranges unless explicitly allowed).
- **Containers:** service images run as a non-root user.

## Known limitations (Version 1)

- The dashboard has no authentication yet (planned).
- Traffic is plain HTTP on localhost. There is no TLS.
- Alloy and cAdvisor mount the Docker socket and host paths. Run the stack only on a development machine you trust.
