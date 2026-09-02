import os
import subprocess
import time
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class GitHubBackup:
    def __init__(self, settings):
        self.settings = settings
        self.data_dir = settings.DATA_DIR
        self.repo_url = os.getenv("GITHUB_BACKUP_REPO", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.backup_enabled = os.getenv("BACKUP_ENABLED", "false").lower() == "true"
        self.message_counter = 0
        self.last_backup_time = time.time()
        self.backup_interval_messages = 10
        self.backup_interval_time = 3600
        self._audit_logger = None

    def attach_audit(self, audit_logger):
        self._audit_logger = audit_logger

    def _get_auth_url(self):
        if self.github_token and self.repo_url:
            if "https://" in self.repo_url:
                return self.repo_url.replace("https://", f"https://{self.github_token}@")
            else:
                return f"https://{self.github_token}@github.com/{self.repo_url.split('github.com/')[-1]}"
        return self.repo_url

    def init_repo(self):
        if not self.backup_enabled:
            return False

        if not self.repo_url:
            logger.warning("GITHUB_BACKUP_REPO not set")
            return False

        git_dir = os.path.join(self.data_dir, ".git")
        if not os.path.exists(git_dir):
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                auth_url = self._get_auth_url()
                subprocess.run(
                    ["git", "remote", "add", "origin", auth_url],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                subprocess.run(
                    ["git", "config", "user.name", "Nova Bot"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                subprocess.run(
                    ["git", "config", "user.email", "nova-bot@discord"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )

                gitignore_path = os.path.join(self.data_dir, ".gitignore")
                if not os.path.exists(gitignore_path):
                    with open(gitignore_path, "w") as f:
                        f.write("*.pyc\n__pycache__/\n.env\n*.log\n")

                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit - Nova Bot Backup"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                subprocess.run(
                    ["git", "branch", "-M", "main"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )
                auth_url = self._get_auth_url()
                subprocess.run(
                    ["git", "push", "-u", "origin", "main"],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True,
                    env={**os.environ, "GIT_ASKPASS": "echo"}
                )

                logger.info("Git repo initialized for backup")
                return True
            except Exception as e:
                logger.error(f"Failed to init git repo: {e}")
                return False
        else:
            try:
                auth_url = self._get_auth_url()
                subprocess.run(
                    ["git", "remote", "set-url", "origin", auth_url],
                    cwd=self.data_dir,
                    capture_output=True,
                    check=True
                )

                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=self.data_dir,
                    capture_output=True,
                    text=True
                )
                current_branch = result.stdout.strip()

                log_result = subprocess.run(
                    ["git", "log", "--oneline", "-1"],
                    cwd=self.data_dir,
                    capture_output=True,
                    text=True
                )
                has_commits = log_result.returncode == 0 and log_result.stdout.strip()

                if not has_commits:
                    logger.info("No commits found, creating initial commit")
                    subprocess.run(
                        ["git", "add", "-A"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True
                    )
                    subprocess.run(
                        ["git", "commit", "-m", "Initial commit - Nova Bot Backup"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True
                    )
                    subprocess.run(
                        ["git", "branch", "-M", "main"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True
                    )
                    auth_url = self._get_auth_url()
                    subprocess.run(
                        ["git", "push", "-u", "origin", "main"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True,
                        env={**os.environ, "GIT_ASKPASS": "echo"}
                    )
                    logger.info("Initial commit created and pushed")
                elif current_branch != "main":
                    logger.info(f"Renaming branch from {current_branch} to main")
                    subprocess.run(
                        ["git", "branch", "-M", "main"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True
                    )
                    auth_url = self._get_auth_url()
                    subprocess.run(
                        ["git", "push", "-u", "origin", "main"],
                        cwd=self.data_dir,
                        capture_output=True,
                        check=True,
                        env={**os.environ, "GIT_ASKPASS": "echo"}
                    )

            except Exception as e:
                logger.error(f"Failed to update remote URL: {e}")
        return True

    def should_backup(self):
        if not self.backup_enabled:
            return False

        if self.message_counter >= self.backup_interval_messages:
            return True

        if time.time() - self.last_backup_time >= self.backup_interval_time:
            return True

        return False

    def backup(self, reason="scheduled"):
        if not self.backup_enabled:
            return False

        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.data_dir,
                capture_output=True,
                check=True
            )

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.data_dir,
                capture_output=True,
                text=True
            )
            if not result.stdout.strip():
                logger.info("No changes to backup")
                self.last_backup_time = time.time()
                self.message_counter = 0
                return True

            commit_msg = f"Nova Bot Backup: {reason} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.data_dir,
                capture_output=True,
                check=True
            )

            auth_url = self._get_auth_url()
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.data_dir,
                capture_output=True,
                check=True,
                env={**os.environ, "GIT_ASKPASS": "echo"}
            )

            logger.info(f"Backup successful: {reason}")
            self.last_backup_time = time.time()
            self.message_counter = 0
            if self._audit_logger:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._audit_logger.log_backup("success", f"Auto backup: {reason}"))
                except RuntimeError:
                    pass
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Backup failed: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return False

    def increment_counter(self):
        self.message_counter += 1
        if self.should_backup():
            return self.backup("message_threshold")
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
