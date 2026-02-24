![A hook helming a bundle of data streams](hook-banner.png)

# Captain Hook

A reusable GitHub Action for posting concise deployment updates to Discord.

CaptainHook turns raw CI/CD context into a streamlined digest with minimal intro, grouped commit bullets, and no success-link previews.

## Features

- Success digests in a Krill-like layout (`Features`, `Fixes / Improvements`, and `Stats`)
- Commit hash + subject bullets for high-signal scanability
- No commit/GitHub URLs in success posts (avoids Discord preview clutter)
- Failure alerts that prioritize incident clarity over feature hype
- Failure-safe behavior: no shipped feature list on failed deploys
- Discord webhook compatibility headers (including Cloudflare-sensitive environments)

## Repository layout

- `.github/actions/deploy-notify/action.yml`
- `.github/actions/deploy-notify/notify.py`
- `SOUL.md`

## Required secrets in consuming repos

Set at organization or repository scope:

- `DISCORD_DEPLOY_WEBHOOK_URL`

## Quick start

```yaml
- name: Notify Discord
  if: always()
  continue-on-error: true
  uses: merchbaseco/captainhook/.github/actions/deploy-notify@v1
  with:
    discord-webhook-url: ${{ secrets.DISCORD_DEPLOY_WEBHOOK_URL }}
```

## Behavior contract

- On success, CaptainHook posts: one short header (`<Repo> — update`), grouped commit bullets (`short_sha + subject`), and one stats line.
- On success, CaptainHook does **not** include commit links/URLs.
- On failure, CaptainHook posts a failure-first alert and does **not** present feature bullets as shipped.
- Uses workflow context automatically (`repository`, `branch`, `actor`, `run`, `sha`).
