# captainhook - shared deploy narrator

This repo owns reusable deploy notification behavior for Merchbase services.

## Source of truth

- Action entrypoint: `.github/actions/deploy-notify/action.yml`
- Runtime logic: `.github/actions/deploy-notify/notify.py`
- Voice + tone contract: `SOUL.md`

## Editing rules

- Keep notification logic centralized here (do not copy scripts back into app repos).
- Preserve failure behavior: **failed deploys must not list shipped features**.
- Keep outputs concise and Discord-friendly.
- If you change tone/format, update `SOUL.md` and `README.md` together.
