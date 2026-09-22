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

Authentication, authorization, and TLS exist but are **off by default** in the alpha. A
gateway started without `--auth-key` trusts every connection: any client that can reach
it can list components, reserve them, and command them, and any process can register as
an adapter.

As a result:

- Start the gateway with `--auth-key` (JWT verification, role-based authorization) and
  `--tls-cert`/`--tls-key` before exposing it beyond a trusted network.
- Without those options, run it **only on trusted networks** and do not expose its port
  to the internet.
- Token issuance is outside OpenRoIS: use an identity provider that signs JWTs with the
  `roles` and `scope` claims documented at
  [openrois.org](https://openrois.org/docs/concepts/security).

Making authentication the default, DDS Security for ROS 2 adapters, and media encryption
remain on the [roadmap](docs/roadmap.md).

## Reporting a Vulnerability

Please **do not open a public issue** for a security problem.

Email **info@coarobo.com** with the subject "OpenRoIS security report".

GitHub private vulnerability reporting is intentionally not enabled yet. The alpha
releases implement the message-passing framework only, and access control sits outside
the middleware, so advisory reports would not describe an OpenRoIS defect. It will be
enabled when authentication and session management land (roadmap Phase 9).

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
third-party dependencies (please report those upstream), and deployments that run the
gateway with authentication off.
