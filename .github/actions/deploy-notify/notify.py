#!/usr/bin/env python3
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request


COMMIT_TYPE_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?!?:\s*(?P<rest>.+)$")
FEATURE_TYPES = {"feat", "feature"}
IMPROVEMENT_PREFIXES = ("fix", "bug", "perf", "refactor", "chore", "build", "ci", "docs", "test", "style")
FEATURE_PREFIXES = ("add ", "adds ", "introduce ", "introduces ", "support ", "supports ", "enable ", "enables ", "new ")


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


def normalize_repo_name(repo: str) -> str:
    short = repo.split("/")[-1] if repo else "repo"
    pieces = [p for p in short.replace("_", "-").split("-") if p]
    return " ".join(p.capitalize() for p in pieces) if pieces else short


def parse_shortstat(raw: str) -> dict[str, int]:
    files_match = re.search(r"(\d+)\s+files?\s+changed", raw)
    insertions_match = re.search(r"(\d+)\s+insertions?\(\+\)", raw)
    deletions_match = re.search(r"(\d+)\s+deletions?\(-\)", raw)
    return {
        "files_changed": int(files_match.group(1)) if files_match else 0,
        "insertions": int(insertions_match.group(1)) if insertions_match else 0,
        "deletions": int(deletions_match.group(1)) if deletions_match else 0,
    }


def build_change_stats(before_sha: str, after_sha: str) -> dict[str, int]:
    zero = "0" * 40
    try:
        if before_sha and before_sha != zero and after_sha:
            raw = git("diff", "--shortstat", before_sha, after_sha)
        elif after_sha:
            raw = git("diff-tree", "--shortstat", "--no-commit-id", "--root", "-r", after_sha)
        else:
            raw = git("diff-tree", "--shortstat", "--no-commit-id", "--root", "-r", "HEAD")
    except Exception:
        raw = ""
    return parse_shortstat(raw)


def classify_subject(subject: str) -> str:
    if not subject:
        return "Fixes / Improvements"

    lowered = subject.lower().strip()
    match = COMMIT_TYPE_RE.match(subject.strip())
    if match:
        commit_type = match.group("type").lower()
        if commit_type in FEATURE_TYPES:
            return "Features"
        return "Fixes / Improvements"

    if lowered.startswith(FEATURE_PREFIXES):
        return "Features"
    if lowered.startswith(IMPROVEMENT_PREFIXES):
        return "Fixes / Improvements"
    return "Fixes / Improvements"


def summarize_subject(subject: str, max_len: int = 110) -> str:
    cleaned = re.sub(r"\s+", " ", subject).strip() or "No subject"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def render_success_copy(
    *,
    repo_name: str,
    commits: list[dict[str, str]],
    stats: dict[str, int],
) -> str:
    features: list[str] = []
    fixes: list[str] = []

    for commit in commits:
        short_sha = commit.get("short_sha", "").strip() or "unknown"
        subject = summarize_subject(commit.get("subject", ""))
        line = f"• `{short_sha}` {subject}"
        if classify_subject(subject) == "Features":
            features.append(line)
        else:
            fixes.append(line)

    lines = [f"{repo_name} — update"]
    if features:
        lines.extend(["", "Features", *features])
    if fixes:
        lines.extend(["", "Fixes / Improvements", *fixes])
    if not commits:
        lines.extend(["", "Fixes / Improvements", "• No commit subjects found"])

    lines.extend(
        [
            "",
            (
                f"Stats: +{stats['insertions']} / -{stats['deletions']} "
                f"(files changed: {stats['files_changed']})"
            ),
        ]
    )
    return "\n".join(lines).strip()


def generate_failure_copy(*, repo_name: str, branch: str, actor: str, run_url: str) -> str:
    lines = [
        f"{repo_name} — deploy failed",
        f"• Build/deploy did not land on `{branch}`.",
        "• No shipped changes listed for failed deploys.",
        f"• Triggered by: {actor}",
        "",
        f"Run: <{run_url}>",
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

    commits = build_commits(before_sha, after_sha, max_commits)
    stats = build_change_stats(before_sha, after_sha)

    if job_status != "success":
        content = generate_failure_copy(
            repo_name=repo_name,
            branch=branch,
            actor=actor,
            run_url=run_url,
        )
        post_discord(webhook_url, content)
        return

    content = render_success_copy(
        repo_name=repo_name,
        commits=commits,
        stats=stats,
    )
    post_discord(webhook_url, content)


if __name__ == "__main__":
    main()
