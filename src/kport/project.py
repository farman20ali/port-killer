"""
project.py — Project detection module for kport.

Resolves a filesystem path (typically a process cwd) to Git project metadata.

OBSERVATIONS produced:
  - git_root: the repository root directory (if found)
  - project_name: directory name of the git root
  - branch: current branch name

INFERENCES produced by callers:
  - "PID <N> appears to belong to project <X>" — caller's responsibility

Design constraints:
  - never raises: all failures return None or empty fields
  - never performs network calls (no git fetch/pull)
  - never exposes credentials in remote URLs
  - independently unit-testable: resolve_project(cwd) -> ProjectInfo | None
  - handles .git directories, .git files (worktrees), detached HEAD
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProjectInfo:
    """Observed Git project metadata resolved from a filesystem path.

    All fields except git_root are optional — set to None if unavailable.
    Fields are OS facts (observations), not inferences.
    """
    git_root: str
    project_name: str | None = None
    branch: str | None = None
    remote_origin: str | None = None   # always credential-sanitized
    is_worktree: bool = False


# ---------------------------------------------------------------------------
# Credential sanitization
# ---------------------------------------------------------------------------

_CRED_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+\-.]*://)(?:[^@/\s]+@)(?P<host>.+)"
)


def _sanitize_remote_url(url: str) -> str:
    """Strip user:password@ from a remote URL.

    Examples:
        https://user:token@github.com/org/repo  → https://github.com/org/repo
        git@github.com:org/repo.git             → unchanged (SCP syntax, no creds)
        https://user@github.com/org/repo        → https://github.com/org/repo
    """
    url = url.strip()
    m = _CRED_PATTERN.match(url)
    if m:
        return m.group("scheme") + m.group("host")
    return url


# ---------------------------------------------------------------------------
# Filesystem Git root walker
# ---------------------------------------------------------------------------

def _find_git_dir(start: str) -> tuple[str, str, bool] | None:
    """Walk ancestor directories looking for .git.

    Returns (git_root, git_dir_or_file_path, is_worktree) or None.

    .git can be:
      - a directory  → normal repository
      - a file       → worktree or submodule (contains "gitdir: ...")
    """
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, ".git")
        if os.path.exists(candidate):
            if os.path.isfile(candidate):
                return current, candidate, True
            elif os.path.isdir(candidate):
                return current, candidate, False
        parent = os.path.dirname(current)
        if parent == current:
            # Reached filesystem root without finding .git
            return None
        current = parent


# ---------------------------------------------------------------------------
# Branch resolution
# ---------------------------------------------------------------------------

def _read_branch(git_dir: str, is_worktree: bool, git_file_path: str) -> str | None:
    """Read the current branch name from HEAD.

    Handles:
      - normal branch: "ref: refs/heads/main\n"
      - detached HEAD: a raw commit SHA
      - worktree .git file pointing elsewhere
      - missing / unreadable HEAD
    """
    # For worktree .git file, resolve the actual gitdir
    actual_git_dir = git_dir
    if is_worktree:
        try:
            with open(git_file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if content.startswith("gitdir:"):
                resolved = content[len("gitdir:"):].strip()
                if not os.path.isabs(resolved):
                    resolved = os.path.join(os.path.dirname(git_file_path), resolved)
                resolved = os.path.normpath(resolved)
                if os.path.isdir(resolved):
                    actual_git_dir = resolved
        except OSError:
            pass

    head_path = os.path.join(actual_git_dir, "HEAD")
    try:
        with open(head_path, "r", encoding="utf-8", errors="ignore") as f:
            head_content = f.read().strip()
    except OSError:
        return None

    if head_content.startswith("ref: refs/heads/"):
        return head_content[len("ref: refs/heads/"):]
    if head_content.startswith("ref: "):
        # Unusual ref (e.g. refs/remotes/...) — return as-is
        return head_content[len("ref: "):]
    # Detached HEAD — raw SHA or other
    if re.match(r"^[0-9a-f]{4,}", head_content):
        return f"(detached HEAD {head_content[:8]})"
    return None


# ---------------------------------------------------------------------------
# Remote origin resolution
# ---------------------------------------------------------------------------

def _read_remote_origin(git_path: str, is_worktree: bool, git_file_path: str) -> str | None:
    """Read the remote 'origin' URL from the git config file.

    git_path: the .git directory (non-worktree) or .git file (worktree).
    Never exposes credentials.
    """
    if is_worktree:
        # git_path is a .git file; resolve the actual git directory from it
        actual_git_dir = None
        try:
            with open(git_file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if content.startswith("gitdir:"):
                resolved = content[len("gitdir:"):].strip()
                if not os.path.isabs(resolved):
                    resolved = os.path.join(os.path.dirname(git_file_path), resolved)
                resolved = os.path.normpath(resolved)
                # worktree gitdirs are like .git/worktrees/<name>/; config lives in .git/
                candidate = resolved
                for _ in range(5):  # safety bound
                    config_path_candidate = os.path.join(candidate, "config")
                    if os.path.isfile(config_path_candidate):
                        actual_git_dir = candidate
                        break
                    candidate = os.path.dirname(candidate)
        except OSError:
            pass
        if actual_git_dir is None:
            return None
        config_path = os.path.join(actual_git_dir, "config")
    else:
        # git_path is the .git directory
        config_path = os.path.join(git_path, "config")
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            config_text = f.read()
    except OSError:
        return None

    # Parse [remote "origin"] section manually — avoid dependency on configparser
    in_origin = False
    for line in config_text.splitlines():
        stripped = line.strip()
        if stripped == '[remote "origin"]':
            in_origin = True
            continue
        if in_origin:
            if stripped.startswith("["):
                break  # Next section — origin block ended without url
            if stripped.startswith("url"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    raw_url = parts[1].strip()
                    return _sanitize_remote_url(raw_url)
    return None


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def resolve_project(cwd: str | None) -> ProjectInfo | None:
    """Resolve Git project metadata from a working directory path.

    Args:
        cwd: Filesystem path to start the search from (process cwd, or any path).
             May be None, a deleted path, or an inaccessible path.

    Returns:
        ProjectInfo if a Git repository root was found, None otherwise.
        Never raises.
    """
    if not cwd:
        return None

    # Guard: path must exist and be accessible
    try:
        if not os.path.exists(cwd):
            return None
    except (OSError, ValueError):
        return None

    try:
        result = _find_git_dir(cwd)
    except Exception:
        return None

    if result is None:
        return None

    git_root, git_path, is_worktree = result
    project_name = os.path.basename(git_root) or None

    branch = None
    try:
        branch = _read_branch(git_path, is_worktree, git_path)
    except Exception:
        pass

    remote_origin = None
    try:
        # git_path is always the .git directory (or .git file for worktrees)
        remote_origin = _read_remote_origin(git_path, is_worktree, git_path)
    except Exception:
        pass

    return ProjectInfo(
        git_root=git_root,
        project_name=project_name,
        branch=branch,
        remote_origin=remote_origin,
        is_worktree=is_worktree,
    )
