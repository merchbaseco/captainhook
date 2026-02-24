#!/usr/bin/env python3
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any


META_KEYWORDS = [
    "deploy",
    "workflow",
    "actions",
    "ci",
    "discord",
    "webhook",
    "runner",
    "pipeline",
]


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


def commit_url(repo: str, after_sha: str) -> str:
    if repo and after_sha:
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


def select_notable_subjects(commits: list[dict[str, str]], limit: int = 3) -> list[str]:
    subjects = [c["subject"] for c in commits if c.get("subject")]
    if not subjects:
        return []

    non_meta = [
        s
        for s in subjects
        if not any(keyword in s.lower() for keyword in META_KEYWORDS)
    ]
    chosen = non_meta[:limit] if non_meta else subjects[:limit]
    return chosen


def fallback_success_copy(repo_name: str, commits: list[dict[str, str]], commit_link: str) -> str:
    opener = f"Arr matey, {repo_name}'s latest deployment just landed clean."
    subjects = select_notable_subjects(commits, limit=3)

    if not subjects:
        bullets = ["• Primarily internal maintenance this voyage."]
    else:
        bullets = [f"• {s}" for s in subjects]

    lines = [opener, "", *bullets]
    if commit_link:
        lines.extend(["", f"Commit: {commit_link}"])
    return "\n".join(lines).strip()


def extract_response_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for item in response.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []) or []:
            if not isinstance(part, dict):
                continue
            value = part.get("value")
            if isinstance(value, str) and value.strip():
                chunks.append(value.strip())
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                continue
            if isinstance(text, dict):
                value = text.get("value")
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
    return "\n".join(chunks).strip()


def sanitize_success_copy(text: str, fallback_opener: str, fallback_bullets: list[str]) -> str:
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n|\n```$", "", text.strip())
    raw_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    raw_lines = [line for line in raw_lines if "http://" not in line and "https://" not in line]

    if not raw_lines:
        raise ValueError("Model returned empty output.")

    opener = raw_lines[0]
    if re.search(r"captainhook\s+\d|openclaw\s+\d", opener.lower()):
        opener = fallback_opener

    bullets: list[str] = []
    for line in raw_lines[1:]:
        text_line = re.sub(r"^[•\-*\d\.)\s]+", "", line).strip()
        if not text_line:
            continue
        bullets.append(f"• {text_line}")

    for fallback in fallback_bullets:
        if len(bullets) >= 3:
            break
        if fallback not in bullets:
            bullets.append(fallback)

    if not bullets:
        bullets = fallback_bullets[:1] if fallback_bullets else ["• Primarily internal maintenance this voyage."]

    return "\n".join([opener, "", *bullets[:3]]).strip()


def render_success_with_openai(
    *,
    openai_api_key: str,
    model: str,
    soul: str,
    repo: str,
    repo_name: str,
    branch: str,
    actor: str,
    commits: list[dict[str, str]],
) -> str:
    payload = {
        "repo": repo,
        "repo_name": repo_name,
        "branch": branch,
        "actor": actor,
        "commits": commits,
        "instructions": [
            "Success-only deploy message.",
            "No title/header/date line.",
            "Line 1 must be a fun pirate-flavored opener sentence.",
            "Then 2-3 short bullets of notable shipped changes.",
            "Focus on user-visible/product impact first.",
            "If mostly internal work, say that plainly.",
            "No links in generated text.",
            "No markdown code fences.",
            "Keep it concise and punchy.",
        ],
    }

    body: dict[str, Any] = {
        "model": model,
        "max_output_tokens": 220,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are Captain Hook, a production release narrator. "
                    "Write concise, vivid deploy updates with pirate flavor and real signal."
                ),
            },
            {
                "role": "system",
                "content": f"SOUL.md (style contract):\n\n{soul or '(No SOUL provided)'}",
            },
            {"role": "user", "content": json.dumps(payload)},
        ],
    }
    if model.startswith("gpt-5"):
        body["reasoning"] = {"effort": "minimal"}
        body["text"] = {"verbosity": "low"}
        body["max_output_tokens"] = 500

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}",
            "User-Agent": "captainhook-notify/1.1",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"OpenAI HTTPError {exc.code}: {body_text}") from exc

    text = extract_response_text(data)
    if not text:
        print("OpenAI empty response payload:", json.dumps(data)[:1500])
        raise ValueError("Model returned empty output.")
    return text


def generate_success_copy(
    *,
    repo: str,
    repo_name: str,
    branch: str,
    actor: str,
    commits: list[dict[str, str]],
    commit_link: str,
    openai_api_key: str,
    model: str,
    soul: str,
) -> str:
    fallback_bullets = [f"• {s}" for s in select_notable_subjects(commits, limit=3)]
    fallback_opener = f"Arr matey, {repo_name}'s latest deployment just landed clean."

    if not openai_api_key:
        return fallback_success_copy(repo_name, commits, commit_link)

    try:
        rendered = render_success_with_openai(
            openai_api_key=openai_api_key,
            model=model,
            soul=soul,
            repo=repo,
            repo_name=repo_name,
            branch=branch,
            actor=actor,
            commits=commits,
        )
        body = sanitize_success_copy(rendered, fallback_opener, fallback_bullets)
    except Exception as exc:
        print(f"OpenAI summary failed, using fallback: {exc}")
        return fallback_success_copy(repo_name, commits, commit_link)

    lines = [body]
    if commit_link:
        lines.extend(["", f"Commit: {commit_link}"])
    return "\n".join(lines).strip()


def generate_failure_copy(*, repo_name: str, branch: str, actor: str, run_url: str) -> str:
    lines = [
        f"Arr matey, rough seas — {repo_name} failed to deploy on `{branch}`.",
        "",
        "• Build/deploy did not land.",
        "• No feature notes posted for failed voyages.",
        f"• Triggered by: {actor}",
        "",
        f"Run: {run_url}",
    ]
    return "\n".join(lines).strip()


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
    latest_commit_link = commit_url(repo, after_sha)

    if job_status != "success":
        content = generate_failure_copy(
            repo_name=repo_name,
            branch=branch,
            actor=actor,
            run_url=run_url,
        )
        post_discord(webhook_url, content)
        return

    content = generate_success_copy(
        repo=repo,
        repo_name=repo_name,
        branch=branch,
        actor=actor,
        commits=commits,
        commit_link=latest_commit_link,
        openai_api_key=openai_api_key,
        model=openai_model,
        soul=soul,
    )
    post_discord(webhook_url, content)


if __name__ == "__main__":
    main()
