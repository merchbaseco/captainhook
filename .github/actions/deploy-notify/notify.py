#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any, Optional


def env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def read_event_before_sha() -> str:
    event_path = env("GITHUB_EVENT_PATH")
    if not event_path:
        return ""
    p = pathlib.Path(event_path)
    if not p.exists():
        return ""
    try:
        payload = json.loads(p.read_text())
    except Exception:
        return ""
    before = payload.get("before")
    return before.strip() if isinstance(before, str) else ""


def build_commits(before_sha: str, after_sha: str, max_commits: int) -> list[dict[str, str]]:
    zero = "0" * 40
    has_before = bool(before_sha) and before_sha != zero
    has_after = bool(after_sha)

    if has_before and has_after:
        rev = f"{before_sha}..{after_sha}"
    elif has_after:
        rev = after_sha
    else:
        rev = "HEAD"

    try:
        raw = git(
            "log",
            "--no-merges",
            f"--max-count={max_commits}",
            "--pretty=format:%h%x1f%s%x1f%an",
            rev,
        )
    except Exception:
        raw = ""

    commits: list[dict[str, str]] = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        short_sha, subject, author = parts
        commits.append(
            {
                "short_sha": short_sha.strip(),
                "subject": subject.strip(),
                "author": author.strip(),
            }
        )
    return commits


def compare_url(repo: str, before_sha: str, after_sha: str) -> str:
    zero = "0" * 40
    if before_sha and before_sha != zero and after_sha:
        return f"https://github.com/{repo}/compare/{before_sha}...{after_sha}"
    if after_sha:
        return f"https://github.com/{repo}/commit/{after_sha}"
    return ""


def normalize_repo_name(repo: str) -> str:
    short = repo.split("/")[-1] if repo else "repo"
    pieces = [p for p in short.replace("_", "-").split("-") if p]
    return " ".join(p.capitalize() for p in pieces) if pieces else short


def read_soul(style_file_input: str, action_path: str) -> str:
    candidates: list[pathlib.Path] = []
    if style_file_input:
        p = pathlib.Path(style_file_input)
        if not p.is_absolute():
            p = pathlib.Path.cwd() / p
        candidates.append(p)
    candidates.append(pathlib.Path(action_path) / "SOUL.md")

    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                continue
    return ""


def fallback_bullets(commits: list[dict[str, str]]) -> list[str]:
    if not commits:
        return ["🔧 Primarily internal maintenance and deployment plumbing updates."]

    def emoji_for(subject: str) -> str:
        s = subject.lower()
        if any(k in s for k in ["security", "harden", "auth", "permission", "secret"]):
            return "🛡️"
        if any(k in s for k in ["fix", "bug", "error", "fail", "regression"]):
            return "🔧"
        if any(k in s for k in ["perf", "speed", "latency", "optimiz", "cache"]):
            return "⚡"
        if any(k in s for k in ["worker", "queue", "cron", "job"]):
            return "🧵"
        if any(k in s for k in ["ui", "dashboard", "frontend", "website"]):
            return "🎛️"
        if any(k in s for k in ["api", "endpoint", "server"]):
            return "🌐"
        if any(k in s for k in ["deploy", "docker", "compose", "workflow", "ci"]):
            return "🚢"
        return "⚓"

    out: list[str] = []
    for c in commits[:5]:
        out.append(f"{emoji_for(c['subject'])} {c['subject']}")
    return out


def extract_json_block(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def generate_success_copy(
    *,
    repo: str,
    repo_name: str,
    branch: str,
    actor: str,
    date_tag: str,
    commits: list[dict[str, str]],
    run_url: str,
    diff_url: str,
    openai_api_key: str,
    model: str,
    soul: str,
) -> str:
    default_headline = f"🪝 CaptainHook {date_tag}"
    default_bullets = fallback_bullets(commits)
    default_status = "✅ Status: Deployment confirmed by the CI crew."

    if not openai_api_key:
        lines = [
            default_headline,
            "",
            f"⚓ {repo_name} shipped to `{branch}`",
            *default_bullets,
            default_status,
            run_url,
            diff_url if diff_url else "",
        ]
        return "\n".join(line for line in lines if line).strip()

    prompt_payload = {
        "repo": repo,
        "repo_name": repo_name,
        "branch": branch,
        "actor": actor,
        "date_tag": date_tag,
        "commits": commits,
        "run_url": run_url,
        "diff_url": diff_url,
        "requirements": {
            "format": "OpenClaw/X-style release digest",
            "headline": "CaptainHook + date + hook emoji",
            "bullets": "4-6 emoji-first bullets, one line each",
            "status": "explicit success confirmation",
            "length": "under 1200 chars",
            "failure_rule": "N/A in this success-only branch",
        },
        "soul": soul,
        "output_schema": {
            "headline": "string",
            "bullets": ["string"],
            "status_line": "string",
            "punchline": "string",
        },
    }

    body = {
        "model": model,
        "temperature": 0.35,
        "max_output_tokens": 300,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are Captain Hook deploy narrator. Return JSON only. "
                    "No markdown code fences. Keep bullets factual and concise."
                ),
            },
            {"role": "user", "content": json.dumps(prompt_payload)},
        ],
    }

    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_api_key}",
                "User-Agent": "captainhook-notify/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        output_text = (data.get("output_text") or "").strip()
        parsed = extract_json_block(output_text)

        if not parsed:
            raise ValueError("Model returned non-JSON output.")

        headline = str(parsed.get("headline") or default_headline).strip()
        bullets_raw = parsed.get("bullets") or default_bullets
        bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
        if not bullets:
            bullets = default_bullets
        bullets = bullets[:6]

        status_line = str(parsed.get("status_line") or default_status).strip()
        punchline = str(parsed.get("punchline") or "").strip()

        lines = [
            headline,
            "",
            f"⚓ {repo_name} shipped to `{branch}`",
            *bullets,
            status_line,
            punchline,
            run_url,
            diff_url if diff_url else "",
        ]
        return "\n".join(line for line in lines if line).strip()
    except Exception as exc:
        print(f"OpenAI summary failed, using fallback: {exc}")
        lines = [
            default_headline,
            "",
            f"⚓ {repo_name} shipped to `{branch}`",
            *default_bullets,
            default_status,
            run_url,
            diff_url if diff_url else "",
        ]
        return "\n".join(line for line in lines if line).strip()


def generate_failure_copy(
    *,
    repo_name: str,
    branch: str,
    actor: str,
    run_url: str,
    date_tag: str,
    diff_url: str,
) -> str:
    lines = [
        f"☠️ CaptainHook Alert {date_tag}",
        "",
        f"❌ {repo_name} failed to deploy on `{branch}`.",
        f"🧭 Actor: `{actor}`",
        "🛑 Status: Build/deploy failed. Feature rollup withheld until a successful landing.",
        run_url,
        diff_url if diff_url else "",
    ]
    return "\n".join(line for line in lines if line).strip()


def post_discord(webhook_url: str, content: str) -> None:
    payload = {"content": content[:1900]}
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "curl/8.7.1",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"Discord webhook response: {resp.status}")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"Discord webhook HTTPError: {exc.code} {exc.reason}; body={body}")
        raise


def main() -> None:
    webhook_url = env("CH_DISCORD_WEBHOOK_URL")
    openai_api_key = env("CH_OPENAI_API_KEY")
    openai_model = env("CH_OPENAI_MODEL", "gpt-4.1-mini")
    style_file = env("CH_STYLE_FILE")
    max_commits = to_int(env("CH_MAX_COMMITS", "8"), 8)

    if not webhook_url:
        print("CH_DISCORD_WEBHOOK_URL is not set; skipping Discord notification.")
        return

    repo = env("GITHUB_REPOSITORY")
    repo_name = normalize_repo_name(repo)
    branch = env("GITHUB_REF_NAME")
    actor = env("GITHUB_ACTOR")
    before_sha = read_event_before_sha()
    after_sha = env("GITHUB_SHA")

    run_url = f"{env('GITHUB_SERVER_URL')}/{repo}/actions/runs/{env('GITHUB_RUN_ID')}"
    job_status = env("CH_JOB_STATUS", "unknown").lower()

    action_path = env("GITHUB_ACTION_PATH", str(pathlib.Path(__file__).resolve().parent))
    soul = read_soul(style_file, action_path)

    commits = build_commits(before_sha, after_sha, max_commits)
    diff_url = compare_url(repo, before_sha, after_sha)

    now = dt.datetime.utcnow()
    date_tag = f"{now.year}.{now.month}.{now.day:02d}"

    if job_status != "success":
        content = generate_failure_copy(
            repo_name=repo_name,
            branch=branch,
            actor=actor,
            run_url=run_url,
            date_tag=date_tag,
            diff_url=diff_url,
        )
        post_discord(webhook_url, content)
        return

    content = generate_success_copy(
        repo=repo,
        repo_name=repo_name,
        branch=branch,
        actor=actor,
        date_tag=date_tag,
        commits=commits,
        run_url=run_url,
        diff_url=diff_url,
        openai_api_key=openai_api_key,
        model=openai_model,
        soul=soul,
    )
    post_discord(webhook_url, content)


if __name__ == "__main__":
    main()
