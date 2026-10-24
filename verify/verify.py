"""Enforce one policy on a pull request: routine paths ship, protected paths wait for the owner.

Reads the policy and the allowed signers from the BASE commit, never from the
pull request, so a change cannot loosen the rule that judges it.

    verify.py --repo-dir . --base <sha> --head <sha> [--pr N --repo owner/name]

Exit 0: allowed. Exit 1: not (yet) allowed; the reason is printed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Policy:
    approver: str            # GitHub login whose review protected paths need
    protected: tuple[str, ...]  # glob patterns, "**" crosses directories


def git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    ).stdout


def load_policy(repo: str, base: str) -> Policy:
    raw = tomllib.loads(git(repo, "show", f"{base}:policy.toml"))
    return Policy(approver=raw["approver"], protected=tuple(raw["protected"]))


def matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return fnmatch.fnmatchcase(path, pattern)


def protected_paths(policy: Policy, paths: list[str]) -> list[str]:
    return [p for p in paths if any(matches(p, pat) for pat in policy.protected)]


def commit_signers(repo: str, base: str, head: str) -> dict[str, str | None]:
    """Map each new commit to the principal whose key signed it, or None."""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(git(repo, "show", f"{base}:allowed_signers"))
        signers_file = f.name
    try:
        out = git(
            repo,
            "-c", "gpg.format=ssh",
            "-c", "gpg.ssh.program=ssh-keygen",
            "-c", f"gpg.ssh.allowedSignersFile={signers_file}",
            "log", "--format=%H %G? %GS", f"{base}..{head}",
        )
    finally:
        os.unlink(signers_file)
    result: dict[str, str | None] = {}
    for line in out.splitlines():
        sha, status, *who = line.split(" ", 2)
        result[sha] = who[0] if status == "G" and who else None
    return result


def github_approvers(repo_slug: str, pr: int, head: str) -> set[str]:
    """Logins whose latest review on the PR approves exactly `head`."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo_slug}/pulls/{pr}/reviews?per_page=100",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        reviews = json.load(resp)
    latest: dict[str, dict] = {}
    for r in reviews:  # chronological
        if r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[r["user"]["login"]] = r
    return {
        login for login, r in latest.items()
        if r["state"] == "APPROVED" and r["commit_id"] == head
    }


def decide(
    repo: str, base: str, head: str, approvers: Callable[[], set[str]]
) -> tuple[bool, list[str]]:
    policy = load_policy(repo, base)
    notes: list[str] = []

    unsigned = [sha[:12] for sha, who in commit_signers(repo, base, head).items() if who is None]
    if unsigned:
        return False, [f"commits not signed by an allowed key: {', '.join(unsigned)}"]

    changed = git(repo, "diff", "--name-only", f"{base}...{head}").split()
    touched = protected_paths(policy, changed)
    if not touched:
        return True, [f"routine change ({len(changed)} files): ships without review"]

    notes.append(f"protected paths changed: {', '.join(touched)}")
    if policy.approver in approvers():
        return True, notes + [f"approved by {policy.approver} at {head[:12]}"]
    return False, notes + [f"waiting for {policy.approver} to approve {head[:12]}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo")
    ap.add_argument("--pr", type=int)
    a = ap.parse_args()

    def approvers() -> set[str]:
        if a.repo is None or a.pr is None:
            return set()
        return github_approvers(a.repo, a.pr, a.head)

    ok, notes = decide(a.repo_dir, a.base, a.head, approvers)
    print("\n".join(notes))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
