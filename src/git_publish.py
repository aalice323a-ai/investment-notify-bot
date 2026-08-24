"""state/(処理済みYouTube動画ID・保有銘柄リスト等)の変更をリポジトリへ
コミット・pushするヘルパー。

GitHub Actions上での実行を前提とする。
push権限は workflow の `permissions: contents: write` + 既定の GITHUB_TOKEN による。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.log import log

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> None:
    log(f"[GitPublish] $ {' '.join(args)}")
    subprocess.run(args, cwd=REPO_ROOT, check=True)


def commit_and_push(paths: list[Path], message: str) -> None:
    """指定パスに変更があればコミットしてpushする。変更が無ければ何もしない。"""
    if not paths:
        log("[GitPublish] no paths given, nothing to do")
        return
    rel_paths = [
        str(p.relative_to(REPO_ROOT)) if p.is_absolute() else str(p) for p in paths
    ]
    _run("git", "config", "user.name", "github-actions[bot]")
    _run("git", "config", "user.email", "github-actions[bot]@users.noreply.github.com")
    _run("git", "add", *rel_paths)
    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
    if diff_check.returncode == 0:
        log("[GitPublish] no staged changes, skipping commit/push")
        return  # 差分なし
    _run("git", "commit", "-m", message)
    _run("git", "push")
    log("[GitPublish] commit + push complete")
