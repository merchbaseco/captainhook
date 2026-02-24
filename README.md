# captainhook

Shared deploy-notification logic for Merchbase services.

## What this repo is

`captainhook` centralizes the Discord deploy post behavior that used to be duplicated in each app repo.

Instead of copying inline Python in every `deploy.yml`, service repos now call a single shared GitHub Action from here:

- `.github/actions/deploy-notify/action.yml`
- `.github/actions/deploy-notify/notify.py`

This keeps deploy messaging consistent and makes style/logic changes one-time.

## Why it exists

- Single place for deploy post formatting + behavior
- AI summary + commit rollup in one implementation
- Clear failure-mode handling (no feature bullets when deploy fails)
- Easier maintenance, fewer drift bugs

## Personality / style

`SOUL.md` defines Captain Hook’s voice and format policy.

High-level behavior:

- **Success**: OpenClaw/X-style digest with emoji bullets + links
- **Failure**: explicit failure report, no feature rollup

## Required secrets in consuming repos

Set at org or repo level:

- `DISCORD_DEPLOY_WEBHOOK_URL`
- `OPENAI_API_KEY` (optional, used for richer summaries)

## Usage from another repo

```yaml
- name: Notify Discord
  if: always()
  continue-on-error: true
  uses: merchbaseco/captainhook/.github/actions/deploy-notify@v1
  with:
    discord-webhook-url: ${{ secrets.DISCORD_DEPLOY_WEBHOOK_URL }}
    openai-api-key: ${{ secrets.OPENAI_API_KEY }}
```

## Notes

- Includes webhook headers that avoid Cloudflare 403 blocks on default `urllib` user agents.
- Uses workflow context (`repo`, `branch`, `actor`, `run`, `sha`) automatically.
