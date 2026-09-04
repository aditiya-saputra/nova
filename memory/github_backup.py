import os
import re
import subprocess
import threading
import time
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN_HEADER_NAME = "Authorization"
_TOKEN_HEADER_VALUE_PREFIX = "token "


class GitHubBackup:
    def __init__(self, settings):
        self.settings = settings
        self.data_dir = settings.DATA_DIR
        # Sumber kanonis dari Settings (mendukung alias GITHUB_REPO lama).
        self.repo_url = getattr(settings, "GITHUB_BACKUP_REPO", "") or os.getenv("GITHUB_BACKUP_REPO", "") or os.getenv("GITHUB_REPO", "")
        self.github_token = getattr(settings, "GITHUB_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")
        self.backup_enabled = bool(getattr(settings, "BACKUP_ENABLED", False)) or os.getenv("BACKUP_ENABLED", "false").lower() == "true"
        self.message_counter = 0
        self.last_backup_time = time.time()
        self.backup_interval_messages = 10
        self.backup_interval_time = 3600
        self._audit_logger = None
        self._backup_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._token_applied = False
        self._canonical_repo_host = self._parse_host(self.repo_url)

    def attach_audit(self, audit_logger):
        self._audit_logger = audit_logger

    @staticmethod
    def _parse_host(url):
        if not url:
            return ""
        m = re.match(r'https?://([^/]+)/', url + "/")
        return m.group(1).lower() if m else ""

    def _redact(self, text):
        if not text or not self.github_token:
            return text
        return text.replace(self.github_token, "***")

    def _safe_run(self, *args, **kwargs):
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        result = subprocess.run(args, **kwargs)
        if result.stderr and self.github_token:
            result.stderr = self._redact(result.stderr)
        if result.stdout and self.github_token:
            result.stdout = self._redact(result.stdout)
        return result

    def _apply_token_to_remote(self):
        if self._token_applied or not self.github_token or not self._canonical_repo_host:
            return
        try:
            self._safe_run(
                "git", "config",
                f"http.{self._canonical_repo_host}/.extraheader",
                f"AUTHORIZATION: {_TOKEN_HEADER_VALUE_PREFIX}{self.github_token}",
                cwd=self.data_dir, check=True,
            )
            self._safe_run(
                "git", "config",
                f"http.{self._canonical_repo_host}/.token",
                f"x-access-token:{self.github_token}",
                cwd=self.data_dir, check=True,
            )
            self._safe_run(
                "git", "remote", "set-url", "origin", self.repo_url,
                cwd=self.data_dir, check=True,
            )
            self._token_applied = True
        except Exception as e:
            logger.error(f"Failed to apply token to remote: {self._redact(str(e))}")

    def init_repo(self):
        if not self.backup_enabled:
            return False

        if not self.repo_url:
            logger.warning("GITHUB_BACKUP_REPO not set")
            return False

        git_dir = os.path.join(self.data_dir, ".git")
        if not os.path.exists(git_dir):
            try:
                self._safe_run("git", "init", cwd=self.data_dir, check=True)
                self._safe_run(
                    "git", "remote", "add", "origin", self.repo_url,
                    cwd=self.data_dir, check=True,
                )
                self._safe_run(
                    "git", "config", "user.name", "Nova Bot",
                    cwd=self.data_dir, check=True,
                )
                self._safe_run(
                    "git", "config", "user.email", "nova-bot@discord",
                    cwd=self.data_dir, check=True,
                )

                gitignore_path = os.path.join(self.data_dir, ".gitignore")
                if not os.path.exists(gitignore_path):
                    with open(gitignore_path, "w") as f:
                        f.write("*.pyc\n__pycache__/\n.env\n*.log\n")

                self._safe_run("git", "add", "-A", cwd=self.data_dir, check=True)
                self._safe_run(
                    "git", "commit", "-m", "Initial commit - Nova Bot Backup",
                    cwd=self.data_dir, check=True,
                )

                branch_result = self._safe_run(
                    "git", "rev-parse", "--abbrev-ref", "HEAD",
                    cwd=self.data_dir, check=True,
                )
                current_branch = branch_result.stdout.strip()
                if current_branch != "main":
                    self._safe_run(
                        "git", "branch", "-m", "main",
                        cwd=self.data_dir, check=True,
                    )

                self._apply_token_to_remote()
                self._safe_run(
                    "git", "push", "-u", "origin", "main",
                    cwd=self.data_dir, check=True,
                )

                logger.info("Git repo initialized for backup")
                return True
            except Exception as e:
                logger.error(f"Failed to init git repo: {self._redact(str(e))}")
                return False
        else:
            try:
                self._safe_run(
                    "git", "remote", "set-url", "origin", self.repo_url,
                    cwd=self.data_dir, check=True,
                )
                self._apply_token_to_remote()

                branch_result = self._safe_run(
                    "git", "rev-parse", "--abbrev-ref", "HEAD",
                    cwd=self.data_dir, check=True,
                )
                current_branch = branch_result.stdout.strip()

                log_result = self._safe_run(
                    "git", "log", "--oneline", "-1",
                    cwd=self.data_dir,
                )
                has_commits = log_result.returncode == 0 and log_result.stdout.strip()

                if not has_commits:
                    logger.info("No commits found, creating initial commit")
                    self._safe_run(
                        "git", "add", "-A", cwd=self.data_dir, check=True,
                    )
                    self._safe_run(
                        "git", "commit", "-m", "Initial commit - Nova Bot Backup",
                        cwd=self.data_dir, check=True,
                    )
                    if current_branch != "main":
                        self._safe_run(
                            "git", "branch", "-m", "main",
                            cwd=self.data_dir, check=True,
                        )
                    self._safe_run(
                        "git", "push", "-u", "origin", "main",
                        cwd=self.data_dir, check=True,
                    )
                    logger.info("Initial commit created and pushed")
                elif current_branch != "main":
                    logger.info(f"Renaming branch from {current_branch} to main")
                    self._safe_run(
                        "git", "branch", "-m", "main",
                        cwd=self.data_dir, check=True,
                    )
                    self._safe_run(
                        "git", "push", "-u", "origin", "main",
                        cwd=self.data_dir, check=True,
                    )

            except Exception as e:
                logger.error(f"Failed to update remote URL: {self._redact(str(e))}")
        return True

    def should_backup(self):
        if not self.backup_enabled:
            return False
        with self._counter_lock:
            if self.message_counter >= self.backup_interval_messages:
                return True
            if time.time() - self.last_backup_time >= self.backup_interval_time:
                return True
        return False

    async def backup(self, reason="scheduled"):
        import asyncio
        if not self.backup_enabled:
            return False
        if self._backup_lock.locked():
            logger.debug(f"Backup already in progress, skipping: {reason}")
            return False
        return await asyncio.to_thread(self._backup_sync, reason)

    def _backup_sync(self, reason="scheduled"):
        with self._backup_lock:
            try:
                self._safe_run(
                    "git", "add", "-A",
                    cwd=self.data_dir, check=True,
                )

                result = self._safe_run(
                    "git", "status", "--porcelain",
                    cwd=self.data_dir,
                )
                if not result.stdout.strip():
                    logger.info("No changes to backup")
                    self._reset_counters()
                    return True

                commit_msg = f"Nova Bot Backup: {reason} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                self._safe_run(
                    "git", "commit", "-m", commit_msg,
                    cwd=self.data_dir, check=True,
                )

                self._safe_run(
                    "git", "push", "origin", "main",
                    cwd=self.data_dir, check=True,
                )

                logger.info(f"Backup successful: {reason}")
                self._reset_counters()
                self._schedule_audit("success", f"Auto backup: {reason}")
                return True

            except subprocess.CalledProcessError as e:
                logger.error(f"Backup failed: {self._redact(e.stderr or '')}")
                return False
            except Exception as e:
                logger.error(f"Backup error: {self._redact(str(e))}")
                return False

    def _reset_counters(self):
        with self._counter_lock:
            self.last_backup_time = time.time()
            self.message_counter = 0

    def _schedule_audit(self, status, message):
        if not self._audit_logger:
            return
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._audit_logger.log_backup(status, message))
        except RuntimeError:
            pass

    def increment_counter(self):
        with self._counter_lock:
            self.message_counter += 1
            if (self.message_counter >= self.backup_interval_messages
                    or time.time() - self.last_backup_time >= self.backup_interval_time):
                return True
        return False

    def get_status(self):
        return {
            "enabled": self.backup_enabled,
            "repo_url": self.repo_url,
            "has_token": bool(self.github_token),
            "messages_since_backup": self.message_counter,
            "last_backup": datetime.fromtimestamp(self.last_backup_time).isoformat(),
            "next_backup_in": max(0, self.backup_interval_messages - self.message_counter)
        }
