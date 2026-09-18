# Security Policy

## Supported Versions

OpenRoIS is **alpha, pre-1.0 software**. Only the latest commit on the `dev` branch
receives fixes. There are no long-term support branches before `v1.0`.

| Version | Supported |
|---------|-----------|
| `dev` (latest) | Yes |
| Tagged `0.x` pre-releases | No, upgrade to the latest `dev` |

## Current Security Posture

Please read this before deploying OpenRoIS.

The alpha releases **do not authenticate or authorize connections**. Any client that can
reach the gateway can list components, reserve them, and command them, and any process
that can reach the gateway can register itself as an adapter. Transport encryption is
not enabled by default either.

As a result:

- Run the gateway **only on trusted networks**, and do not expose its port to the
  internet.
- Put your own authenticated reverse proxy or VPN in front of it if remote access is
  required.
- Treat every connected robot as reachable by every client on that network.

Authentication with JSON Web Tokens, role-based authorization per RoIS operation, and
TLS by default are Phase 9 of the [roadmap](docs/roadmap.md). The intended design is
documented at [openrois.org](https://openrois.org/docs/concepts/security).

## Reporting a Vulnerability

Please **do not open a public issue** for a security problem.

1. Preferred: report privately through GitHub, using
   [private vulnerability reporting](https://github.com/openrois/openrois/security/advisories/new)
   on this repository.
2. Alternative: email **info@coarobo.com** with the subject "OpenRoIS security report".

Please include the affected component and version or commit, a description of the issue,
the steps to reproduce it, and the impact you expect.

## What to Expect

- We aim to acknowledge a report within five working days.
- We will confirm the issue, determine the affected versions, and tell you what we plan
  to do.
- We will credit you in the release notes unless you prefer otherwise.
- Because the project is pre-1.0, fixes normally ship on `dev` rather than as a
  backported patch release.

## Scope

In scope: the OpenRoIS engine, gateway, component framework, SDKs, interface types, and
the examples in this repository.

Out of scope: vulnerabilities in the robots, avatars, or services behind an adapter, in
third-party dependencies (please report those upstream), and the known absence of
authentication described above, which is tracked on the roadmap.
