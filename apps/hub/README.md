# Hub

The Hub will be the management web application for an OpenRoIS gateway: a live view of
connected adapters, their components, status, and reservations, plus profile and package
management through the gateway API.

> **Not started.** This directory currently holds a Vite and React scaffold with no
> OpenRoIS code. The Hub is [Phase 11 of the roadmap](https://openrois.org/docs/project/roadmap),
> after version 1.0, and it is gated on adoption.

## Looking for a Tool to Inspect an Engine Today?

Use [`examples/hri-client`](../../examples/hri-client/README.md). It connects to any RoIS
engine, reads the profile, and renders every component with its queries, commands, and
events. The [quickstart](https://openrois.org/docs/getting-started/quickstart) runs it in
a couple of minutes.

## Development

```bash
npm install
npm run dev
```

## License

Apache-2.0.
