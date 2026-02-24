![A hook helming a bundle of data streams](hook-banner.png)

# Captain Hook

A reusable GitHub Action for posting polished deployment updates to Discord.

CaptainHook turns raw CI/CD context into clear, high-signal release messages with a distinct voice.

## Features

- ✅ Success digests with structured, emoji-led release notes
- ❌ Failure alerts that prioritize incident clarity over feature hype
- 🤖 Optional AI-assisted copy generation via OpenAI
- 🧠 Persona/style contract via `SOUL.md`
- 🔗 Automatic inclusion of run and compare/commit links
- 🛡️ Discord webhook compatibility headers (including Cloudflare-sensitive environments)

## Repository layout

- `.github/actions/deploy-notify/action.yml`
- `.github/actions/deploy-notify/notify.py`
- `SOUL.md`

## Required secrets in consuming repos

Set at organization or repository scope:

- `DISCORD_DEPLOY_WEBHOOK_URL`
- `OPENAI_API_KEY` *(optional)*

## Quick start

```yaml
- name: Notify Discord
  if: always()
  continue-on-error: true
  uses: merchbaseco/captainhook/.github/actions/deploy-notify@v1
  with:
    discord-webhook-url: ${{ secrets.DISCORD_DEPLOY_WEBHOOK_URL }}
    openai-api-key: ${{ secrets.OPENAI_API_KEY }}
```

## Behavior contract

- On success, CaptainHook posts a concise release digest.
- On failure, CaptainHook posts a failure-first alert and does **not** present feature bullets as shipped.
- Uses workflow context automatically (`repository`, `branch`, `actor`, `run`, `sha`).
