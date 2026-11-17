# Environments: dev, staging, production

VAI runs from one codebase in three environments. They differ only in configuration, and they never share data.

| | **dev** | **staging** | **production** |
|---|---|---|---|
| Where | Your laptop | On the internet, private | On the internet, public |
| Who | You | You and test colleagues | Real workers and employers |
| Database | Throwaway SQLite (default) | Its own database | Its own PostgreSQL, backed up |
| Node registration | Open, unless `VAI_REGISTRATION_KEY` is set | Requires `VAI_REGISTRATION_KEY` | Requires `VAI_REGISTRATION_KEY` |
| Payments | None | Test mode only | Live |
| Deploys from | Your working copy | Pushes to `main` | Tagged releases (e.g. `v0.3.0`) |

Set `VAI_ENV` to `dev` (the default), `staging` or `production`. Dev and staging pages show a banner so nobody mistakes test data for real work.

## The platform refuses unsafe setups

`web_platform/config.py` runs before anything else. In `staging` and `production` the platform won't start unless:

- `DATABASE_URL` is set explicitly (no falling back to a local SQLite file),
- `SECRET_KEY` is a random value of at least 32 characters (not the example value),
- `VAI_REGISTRATION_KEY` is set (at least 16 characters), so only your nodes can register VAIs.

Production also refuses SQLite. Give each environment its own values for all three settings, so a node token or key from one environment never works on another.

## What the platform can and can't know about a worker

The platform never reads files from a worker's machine. A VAI appears on the marketplace only when the worker's own node registers it, sending a **public card**: display name, headline, short bio, areas of expertise and the kinds of work it never accepts. The registration endpoint rejects any other field.

Everything else stays on the worker's machine: interview answers, deep-interview answers and notes, reference documents, the local vector memory, AI drafts and the worker's corrections. The platform only sees each task, the draft the node submits for review, and the final deliverable the worker approves.

Each node gets a bearer token when it registers. The platform stores only a SHA-256 hash of it, and a node can only see, draft and learn from tasks hired to its own VAI. Tokens are saved per platform URL in the profile's `node_credentials.json`, so a dev or staging token is never sent to production. The node refuses plain `http://` for any platform that isn't on `localhost`.

## Still needed before production

- **Worker logins.** Any worker dashboard (`/worker/<id>`) is open to anyone who can reach the platform. That's acceptable on dev and on a private staging site only.
- **Migrations (Alembic).** New columns are currently added in place at startup. Production needs versioned migrations, rehearsed on staging first.
- **Payments and escrow**, in test mode on staging.
- **Hosting** for staging, then production, each with its own database and keys.
