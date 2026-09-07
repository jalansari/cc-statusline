#!/usr/bin/env python3

import calendar
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

debug_info = ""


# Define color palette
C_DIR_BG = 18  # dark blue
C_DIR_FG = 255  # white
C_BRANCH_BG = 232  # black
C_BRANCH_FG = 117  # light blue
C_BRANCH_MAIN_FG = 124  # dark red
C_BRANCH_STAGING_FG = 226  # yellow
C_MODEL_BG = 53  # teal
C_MODEL_FG = 255  # white
C_TOKENS_BG = 233  # dark gray
C_TOKENS_FG = 250  # light gray
C_TOKENS_WEEK_BG = 236  # very dark gray
C_TOKENS_WEEK_FG = 250  # light gray
C_TOKENS_CURR_BG = 236  # very dark gray
C_TOKENS_CURR_FG = 34  # green
C_TOKENS_CURR_BIG_FG = 204  # light red
C_STATUS_ICONS_BG = 233  # dark gray
C_AUTHD_OK = 34  # green
C_AUTHD_FAIL = 196  # red
C_ENTERPRISE_FG = 33  # blue
C_ENTERPRISE_BG = 18  # dark blue bg


# Nerd Font icons
ICON_BRANCH = "\ue0a0"  #  (powerline branch)
ICON_WORKTREE = "\uf1bb"  #  (tree)
ICON_AI_MODEL = "\u2731"  # ✱ (heavy asterisk)
ICON_WINDOW_QUOTA = "\u25eb"  # ◫ (white square with vertical bisecting line)
ICON_WEEK_QUOTA = "\uef38"  #  (calendar week)
ICON_CURRENT_CONTEXT = "\u25d0"  # ◐ (circle with left half black)
ICON_ENTERPRISE = "\ueebf"  #  (enterprise plan)
ICON_API_KEY = "\U000f109b"  # 󱂛 (API key)

ICON_NOTION = "\ue848"  #  (notion)
ICON_ATLASSIAN_CLI = "\ue75c"  #  (atlassian jira)
ICON_ATLASSIAN = "\uef32"  #  (atlassian)
ICON_FIGMA = "\ue7da"  #  (figma)
ICON_DATADOG = "\ue902"  #  (datadog)
ICON_MIXPANEL = "\U000f0b05"  # 󰬅 (mixpanel)
ICON_OPENTOFU = "\U000f1062"  # 󱁢 (opentofu)
ICON_GITHUB = "\uea84"  #  (github)
ICON_PERL = "\ue67e"  #  (perl)
ICON_PYTHON = "\ue73c"  #  (python)
ICON_NODE = "\ue718"  #  (nodejs)
ICON_RUST = "\ue7a8"  #  (rust)
ICON_GO = "\ue627"  #  (go)
ICON_JAVA = "\ue738"  #  (java)
ICON_RUBY = "\ue791"  #  (ruby)
ICON_SHELL = "\uebca"  #  (terminal/shell)
ICON_TYPESCRIPT = "\ue628"  #  (typescript)
ICON_TERRAFORM = "\ue69a"  #  (terraform)
ICON_DOCKER = "\ue7b0"  #  (docker)

SEP_RIGHT = "\ue0b0"  #  (powerline right arrow)
# SEP_RIGHT_THIN = "\ue0b1"  #  (powerline right thin arrow)

RESET = "\033[0m"
BOLD = "\033[1m"


USER_AGENT_STRING = "cc-statusline/0.0.1"


CACHE_DIR = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), f"claude_status_cache_{os.getuid()}"
)


def _config_dir() -> str:
    """Return the Claude config directory, honouring CLAUDE_CONFIG_DIR.

    Claude Code treats an unset variable differently from one set to an empty
    string.

    Only an unset variable falls back to ~/.claude; a variable that is set but
    empty is kept as-is, which makes Claude Code resolve its config home
    against the current working directory instead.

    Mirroring that distinction allows us to read the profile Claude Code is
    actually writing, hence this deliberately tests for None rather than for
    emptiness.
    """
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir is None:
        return os.path.expanduser("~/.claude")
    return config_dir


def _profile_key() -> str:
    """Cache key for the active config dir, e.g. '.claude-alt' -> 'claude-alt'."""
    path = os.path.realpath(_config_dir())
    slug = os.path.basename(path).lstrip(".") or "claude"
    return f"{slug}_{hashlib.sha256(path.encode()).hexdigest()[:8]}"


@dataclass(slots=True)
class LangDetectRules:
    icon: str
    files: list[str]
    extensions: list[str]
    folders: list[str]
    prefixes: list[str]

    def matches(self, entries: list[str]) -> bool:
        entry_set = set(entries)
        for a_file in self.files:
            if a_file in entry_set:
                return True
        for ext in self.extensions:
            if any(entry.endswith(ext) for entry in entries):
                return True
        for a_dir in self.folders:
            if a_dir in entry_set and os.path.isdir(a_dir):
                return True
        for prefix in self.prefixes:
            if any(entry.startswith(prefix) for entry in entries):
                return True
        return False


LANG_DETECT_RULES: list[LangDetectRules] = [
    LangDetectRules(
        ICON_TERRAFORM,
        [],
        [".tf"],
        [],
        [".terraform"],
    ),
    LangDetectRules(
        ICON_PERL,
        [],
        [".pl", ".pm"],
        ["Perl"],
        [],
    ),
    LangDetectRules(
        ICON_NODE,
        ["package.json", ".nvmrc", ".node-version"],
        [".js", ".mjs", ".cjs"],
        ["node_modules"],
        [],
    ),
    LangDetectRules(
        ICON_TYPESCRIPT,
        ["tsconfig.json"],
        [".ts", ".tsx"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_PYTHON,
        [
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Pipfile",
            ".python-version",
        ],
        [".py"],
        [".venv"],
        [],
    ),
    LangDetectRules(
        ICON_RUST,
        ["Cargo.toml"],
        [".rs"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_GO,
        ["go.mod"],
        [".go"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_JAVA,
        ["pom.xml", "build.gradle", "build.gradle.kts"],
        [".java"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_RUBY,
        ["Gemfile", "Rakefile", ".ruby-version"],
        [".rb"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_SHELL,
        [],
        [".sh", ".bash", ".zsh"],
        [],
        [],
    ),
    LangDetectRules(
        ICON_DOCKER,
        ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
        [],
        [],
        [],
    ),
]


@dataclass(slots=True)
class McpServer:
    """An MCP server whose auth state is shown in the status line."""

    icon: str
    name: str
    needs_auth: bool = True

    @property
    def creds_prefix(self) -> str:
        """Credentials are keyed "<server name>|<hash>" in mcpOAuth."""
        return f"{self.name}|"


# Order here is the order the icons appear in the status line. A server is only
# drawn when it is registered in .claude.json, so this list can name servers
# that only some machines have.
#
# needs_auth=False marks a server that never authenticates.  Registering the MCP
# is all we need to check, and skip any auth credentials checks.
MCP_SERVERS: list[McpServer] = [
    McpServer(ICON_NOTION, "notion"),
    McpServer(ICON_ATLASSIAN, "atlassian"),
    McpServer(ICON_FIGMA, "figma"),
    McpServer(ICON_DATADOG, "datadog-mcp"),
    McpServer(ICON_MIXPANEL, "mixpanel"),
    McpServer(ICON_OPENTOFU, "opentofu", needs_auth=False),
]


class Cache:
    def __init__(self, filename: str, ttl: int = 5):
        self.path = os.path.join(CACHE_DIR, filename)
        self.ttl = ttl

    def read(self) -> dict:
        """Return cached data if fresh, or empty dict if stale/missing."""
        ret = {}
        try:
            age = time.time() - os.path.getmtime(self.path)
            if age < self.ttl:
                with open(self.path) as a_file:
                    ret = json.load(a_file)
        except Exception:
            pass
        return ret

    def write(self, data: dict) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self.path, "w") as a_file:
            json.dump(data, a_file)


class SystemInfo:
    """Retrieves and caches system information for the status line."""

    def __init__(self, session_id: str) -> None:
        self._session_id: str = session_id
        self.cache_1s: Cache = Cache(f"{session_id}_cache_1s.json", 1)
        self.cache_10s: Cache = Cache(f"{session_id}_cache_10s.json", 10)
        self.cache_1m: Cache = Cache(f"{session_id}_cache_1m.json", 60)
        self._data_fast: dict = {}
        self._data_medium: dict = {}
        self._data_long: dict = {}
        self._creds_data: dict = {}

    def initialise(self) -> None:
        """Gather all system information, using caches when fresh."""
        self._data_fast = self.cache_1s.read()
        if not self._data_fast:
            self._data_fast = {
                "git_branch": self.__fetch_git_branch(),
            }
            self.cache_1s.write(self._data_fast)

        self._data_medium = self.cache_10s.read()
        if not self._data_medium:
            self._data_medium = {
                "acli_authd": self.__check_command_success(["acli", "auth", "status"]),
                "gh_authd": self.__check_command_success(["gh", "auth", "status"]),
                "mcp_status": self.__fetch_mcp_status(),
            }
            self.cache_10s.write(self._data_medium)

        self._data_long = self.cache_1m.read()
        if not self._data_long:
            self._data_long = {
                "current_dir": self.__fetch_current_dir(),
                "language": self.__fetch_language(),
                "monthly_cost": self.__fetch_monthly_cost(self._session_id),
            }
            self.cache_1m.write(self._data_long)

    # -- Getters (read from pre-fetched dictionaries) --

    def get_current_dir(self) -> str:
        return self._data_long.get("current_dir", "")

    def get_git_branch(self) -> str:
        return self._data_fast.get("git_branch", "")

    def detect_language(self) -> str:
        return self._data_long.get("language", "")

    def get_monthly_cost(self) -> float:
        return self._data_long.get("monthly_cost", 0.0)

    def get_acli_authd(self) -> bool:
        return self._data_medium.get("acli_authd", False)

    def get_gh_authd(self) -> bool:
        return self._data_medium.get("gh_authd", False)

    def get_mcp_status(self) -> dict:
        """Registered MCP servers only, mapped to whether auth is live.

        A server missing from this dict is not registered in .claude.json and is
        left out of the status line entirely.
        """
        return self._data_medium.get("mcp_status", {})

    # -- Private fetchers --

    @staticmethod
    def __fetch_current_dir() -> str:
        return os.path.basename(os.getcwd())

    @staticmethod
    def __fetch_git_branch() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return ""

    @staticmethod
    def __fetch_language() -> str:
        try:
            entries = os.listdir(".")
        except OSError:
            return ""
        for rule in LANG_DETECT_RULES:
            if rule.matches(entries):
                return rule.icon
        return ""

    @staticmethod
    def __fetch_monthly_cost(session_id: str) -> float:
        csv_path = os.path.join(_config_dir(), "cc-costtrack", "claude-token-usage.csv")
        month_prefix = datetime.now().strftime("%Y-%m")
        total = 0.0
        try:
            with open(csv_path) as f:
                lines = f.readlines()
            for row in csv.reader(reversed(lines)):
                if not row or row[0] == "timestamp":
                    continue
                if not row[0].startswith(month_prefix):
                    break
                if row[1] == session_id:
                    continue
                total += float(row[-1])
        except (FileNotFoundError, ValueError, IndexError):
            pass
        return total

    def __get_creds_data(self) -> dict:
        if not self._creds_data:
            creds_path = os.path.join(_config_dir(), ".credentials.json")
            try:
                with open(creds_path) as creds_file:
                    self._creds_data = json.load(creds_file)
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                self._creds_data = {}
        return self._creds_data

    def get_subscription_type(self) -> str:
        return (
            self.__get_creds_data().get("claudeAiOauth", {}).get("subscriptionType", "")
        )

    def get_auth_mode(self) -> str:
        """Returns 'enterprise', 'oauth', or 'api_key'."""
        creds = self.__get_creds_data()
        oauth = creds.get("claudeAiOauth", {})
        if oauth.get("subscriptionType") == "enterprise":
            return "enterprise"
        if oauth.get("accessToken"):
            return "oauth"
        return "api_key"

    @staticmethod
    def get_days_remaining_in_month() -> int:
        today = datetime.now()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        return days_in_month - today.day

    def __get_mcp_oauth_creds(self) -> dict:
        return self.__get_creds_data().get("mcpOAuth", {})

    @staticmethod
    def __get_registered_mcp_servers() -> set[str]:
        """Collect all MCP server names registered across any project in .claude.json."""
        servers: set[str] = set()
        config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
        config_path = (
            os.path.join(config_dir, ".claude.json")
            if config_dir
            else os.path.expanduser("~/.claude.json")
        )
        try:
            with open(config_path) as f:
                data = json.load(f)
            # Walk all values recursively looking for mcpServers dicts
            to_visit = [data]
            while to_visit:
                node = to_visit.pop()
                if isinstance(node, dict):
                    if "mcpServers" in node and isinstance(node["mcpServers"], dict):
                        servers.update(node["mcpServers"].keys())
                    to_visit.extend(node.values())
                elif isinstance(node, list):
                    to_visit.extend(node)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return servers

    def __fetch_mcp_status(self) -> dict:
        """Map each *registered* MCP server to whether it is healthy.

        Servers absent from .claude.json are omitted rather than reported as
        failed, so the status line only shows what this machine uses.

        The registry is read once here, not once per server.
        """
        registered = self.__get_registered_mcp_servers()
        return {
            server.name: self.__mcp_server_ok(server)
            for server in MCP_SERVERS
            if server.name in registered
        }

    def __mcp_server_ok(self, server: McpServer) -> bool:
        if not server.needs_auth:
            # A server needing no auth is just healthy.
            return True
        return self.__mcp_has_token(server.creds_prefix)

    def __mcp_has_token(self, prefix: str) -> bool:
        """True when a non-expired access token exists for this server."""
        now_ms = int(time.time() * 1000)
        for k, v in self.__get_mcp_oauth_creds().items():
            if k.startswith(prefix) and isinstance(v, dict):
                if not v.get("accessToken", ""):
                    continue
                expires_at = v.get("expiresAt")
                if isinstance(expires_at, (int, float)) and expires_at <= now_ms:
                    continue
                return True
        return False

    @staticmethod
    def __check_command_success(command: list[str], timeout: int = 5) -> bool:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


class ClaudeUsageInfo:
    """Fetches and caches Anthropic API rate limit usage (window + weekly)."""

    USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
    REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
    CLAUDE_CODE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

    def __init__(self, session_id: str) -> None:
        profile = _profile_key()
        self.cache = Cache(f"shared_usage_cache_{profile}.json", 300)
        self.backoff_file = os.path.join(CACHE_DIR, f"usage_backoff_{profile}")
        self._data: dict = {}

    def initialise(self) -> None:
        self._data = self.cache.read()
        if not self._data:
            if self.__is_backing_off():
                return
            self._data = self.__fetch_usage()
            if self._data:
                self.cache.write(self._data)
            else:
                self.__set_backoff()

    def __is_backing_off(self) -> bool:
        try:
            age = time.time() - os.path.getmtime(self.backoff_file)
            return age < 300  # 5 minute backoff after failure
        except OSError:
            return False

    def __set_backoff(self) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self.backoff_file, "w") as f:
            f.write("")

    def get_window_pct(self) -> float:
        return self._data.get("five_hour", {}).get("utilization", 0) or 0

    def get_window_resets_at(self) -> str:
        return self._data.get("five_hour", {}).get("resets_at", "")

    def get_weekly_pct(self) -> float:
        return self._data.get("seven_day", {}).get("utilization", 0) or 0

    def get_weekly_resets_at(self) -> str:
        return self._data.get("seven_day", {}).get("resets_at", "")

    @staticmethod
    def __get_bearer_token() -> tuple[str, str] | None:
        ret = None
        creds_path = os.path.join(_config_dir(), ".credentials.json")
        try:
            with open(creds_path) as creds_file:
                creds = json.load(creds_file)
                oauth_info = creds.get("claudeAiOauth", {})
                access_token = oauth_info.get("accessToken", "")
                refresh_token = oauth_info.get("refreshToken", "")
                ret = (
                    (access_token, refresh_token)
                    if access_token and refresh_token
                    else None
                )
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        return ret

    def __auth_refresh_on_rate_limit(self, refresh_token: str) -> dict:
        refresh_data = {}
        req = urllib.request.Request(
            self.REFRESH_URL,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT_STRING,
            },
            data=json.dumps(
                {
                    "clientId": self.CLAUDE_CODE_CLIENT_ID,
                    "grantType": "refresh_token",
                    "refreshToken": refresh_token,
                }
            ).encode("utf-8"),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            refresh_data = json.loads(resp.read())
        self.__save_refreshed_tokens(refresh_data)
        return refresh_data

    @staticmethod
    def __save_refreshed_tokens(refresh_data: dict) -> None:
        new_access = refresh_data.get("accessToken", "")
        new_refresh = refresh_data.get("refreshToken", "")
        if not new_access:
            return
        creds_path = os.path.join(_config_dir(), ".credentials.json")
        try:
            with open(creds_path) as f:
                creds = json.load(f)
            oauth_info = creds.setdefault("claudeAiOauth", {})
            oauth_info["accessToken"] = new_access
            if new_refresh:
                oauth_info["refreshToken"] = new_refresh
            with open(creds_path, "w") as f:
                json.dump(creds, f, indent=2)
        except Exception:
            pass

    def __make_usage_request(self, token: str) -> dict:
        req = urllib.request.Request(
            self.USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT_STRING,
                "anthropic-beta": "oauth-2025-04-20",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def __fetch_usage(self) -> dict:
        usage_data = {}
        tokens = self.__get_bearer_token()
        if tokens:
            token, refresh = tokens
            try:
                usage_data = self.__make_usage_request(token)
            except urllib.error.HTTPError as http_exc:
                global debug_info
                if http_exc.code in (401, 429):
                    try:
                        refresh_data = self.__auth_refresh_on_rate_limit(refresh)
                        new_token = refresh_data.get("accessToken", "")
                        if new_token:
                            usage_data = self.__make_usage_request(new_token)
                    except urllib.error.HTTPError as rf_exc:
                        debug_info += f"ue:{http_exc.code}+rf:{rf_exc.code}"
                    except Exception as rf_exc:
                        debug_info += f"ue:{http_exc.code}+rf:{type(rf_exc).__name__}"
                else:
                    debug_info += f"ue:{http_exc.code}"
            except Exception:
                pass
        return usage_data


class ClaudeInfo:
    """Retrieves and caches Claude Code session information from stdin JSON."""

    def __init__(self) -> None:
        self._data: dict = {}

    def initialise(self) -> None:
        """Read Claude Code JSON from stdin."""
        stdin_data = self.__read_stdin()
        self._data = stdin_data or {}
        # For debugging...
        session_id = stdin_data.get("session_id", "")
        cache = Cache(f"{session_id}_cache_stdin.json", 1)
        cache.write(self._data)

    def get_model_name(self) -> str:
        return self._data.get("model", {}).get("display_name", "")

    # -- Getters: cost and context window --

    def get_cost_usd(self) -> float:
        return self._data.get("cost", {}).get("total_cost_usd", 0.0)

    def get_context_used_pct(self) -> float:
        return self._data.get("context_window", {}).get("used_percentage", 0) or 0

    def get_current_usage(self) -> int:
        all_token_usage = self._data.get("context_window", {})
        usage_dict = all_token_usage.get("current_usage", {}) or {}
        input_tokens = usage_dict.get("input_tokens", 0)
        cache_creation_input_tokens = usage_dict.get("cache_creation_input_tokens", 0)
        cache_read_input_tokens = usage_dict.get("cache_read_input_tokens", 0)
        all_input_tokens = (
            input_tokens + cache_creation_input_tokens + cache_read_input_tokens
        )
        return all_input_tokens

    # -- Getters: session --

    def get_session_id(self) -> str:
        return self._data.get("session_id", "")

    def get_worktree(self) -> dict:
        return self._data.get("worktree", {})

    # -- Private --

    @staticmethod
    def __read_stdin() -> dict:
        data = {}
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
                if raw.strip():
                    data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass
        return data


# ANSI 256-color helpers
def fg(color: int) -> str:
    return f"\033[38;5;{color}m"


def bg(color: int) -> str:
    return f"\033[48;5;{color}m"


def _format_time_remaining(resets_at: str) -> str:
    """
    ISO timestamp into human-readable time remaining (e.g. '2h13m' or '5.1d').
    """
    ret = "?m"
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        remaining = reset_dt - datetime.now(timezone.utc)
        total_seconds = max(0, int(remaining.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        if hours < 1:
            ret = f"{minutes}m"
        elif hours > 0 and hours < 24:
            ret = f"{hours}h{minutes:02d}m"
        else:
            days = hours // 24
            ret = f"{days:.1f}d"
    except (ValueError, TypeError, AttributeError):
        pass
    return ret


@dataclass(slots=True)
class Segment:
    text: str
    fg_color: int
    bg_color: int
    bold: bool = False


def render_segments(segments: list[Segment]) -> str:
    out = ""
    for i, seg in enumerate(segments):
        bold_on = BOLD if seg.bold else ""
        bold_off = "\033[22m" if seg.bold else ""
        out += f"{bold_on}{fg(seg.fg_color)}{bg(seg.bg_color)}{seg.text}{bold_off}"
        if i < len(segments) - 1:
            next_bg = segments[i + 1].bg_color
            out += f"{fg(seg.bg_color)}{bg(next_bg)}{SEP_RIGHT}"
        else:
            out += f"{RESET}{fg(seg.bg_color)}{SEP_RIGHT}{RESET}"
    return out


def render_statusline() -> str:
    claude_info = ClaudeInfo()
    claude_info.initialise()
    session_id = claude_info.get_session_id()
    sysinfo = SystemInfo(session_id)
    sysinfo.initialise()
    auth_mode = sysinfo.get_auth_mode()
    usage: ClaudeUsageInfo | None = None
    if auth_mode == "oauth":
        usage = ClaudeUsageInfo(session_id)
        usage.initialise()

    segments: list[Segment] = []

    # Directory segment
    directory = sysinfo.get_current_dir()
    segments.append(Segment(f" {directory} ", C_DIR_FG, C_DIR_BG, bold=True))

    # Git branch segment (color by branch name)
    branch = sysinfo.get_git_branch()
    if branch:
        branch_color = C_BRANCH_FG
        if branch in ("master", "main"):
            branch_color = C_BRANCH_MAIN_FG
        elif branch == "staging":
            branch_color = C_BRANCH_STAGING_FG
        worktree_icon = f" {ICON_WORKTREE}" if claude_info.get_worktree() else ""
        lang_icon = sysinfo.detect_language()
        lang_suffix = f" {lang_icon}" if lang_icon else ""
        segments.append(
            Segment(
                f" {ICON_BRANCH}{worktree_icon} {branch}{lang_suffix} ",
                branch_color,
                C_BRANCH_BG,
                bold=True,
            )
        )

    # Model segment
    model = claude_info.get_model_name()
    segments.append(Segment(f" {ICON_AI_MODEL} {model} ", C_MODEL_FG, C_MODEL_BG))

    # Token usage segments (combined into one background)
    current_context_pct = claude_info.get_context_used_pct()
    current_used_raw = claude_info.get_current_usage()
    current_used = f"{current_used_raw / 1000:.3g}k"
    ctx_fg = C_TOKENS_CURR_BIG_FG if current_context_pct >= 80 else C_TOKENS_CURR_FG
    cost_usd = claude_info.get_cost_usd()
    segments.append(
        Segment(
            f" {ICON_CURRENT_CONTEXT} {current_context_pct}% | {current_used} | ${cost_usd:.2f} ",
            ctx_fg,
            C_TOKENS_CURR_BG,
            bold=True,
        )
    )

    if usage:
        window_pct = usage.get_window_pct()
        window_time = _format_time_remaining(usage.get_window_resets_at())
        weekly_pct = usage.get_weekly_pct()
        weekly_time = _format_time_remaining(usage.get_weekly_resets_at())
        segments.append(
            Segment(
                f" {ICON_WINDOW_QUOTA} {window_pct:.0f}% ({window_time}) ",
                C_TOKENS_FG,
                C_TOKENS_BG,
            )
        )
        segments.append(
            Segment(
                f" {ICON_WEEK_QUOTA} {weekly_pct:.0f}% ({weekly_time}) ",
                C_TOKENS_WEEK_FG,
                C_TOKENS_WEEK_BG,
            )
        )
    else:
        monthly_cost = sysinfo.get_monthly_cost() + cost_usd
        days_left = sysinfo.get_days_remaining_in_month()
        icon = ICON_ENTERPRISE if auth_mode == "enterprise" else ICON_API_KEY
        segments.append(
            Segment(
                f" {icon}  ${monthly_cost:.2f} {days_left}d ",
                C_ENTERPRISE_FG,
                C_ENTERPRISE_BG,
            )
        )

    # Auth status icons: CLI tools, then MCP servers, each colored independently
    gh_color = C_AUTHD_OK if sysinfo.get_gh_authd() else C_AUTHD_FAIL
    acli_color = C_AUTHD_OK if sysinfo.get_acli_authd() else C_AUTHD_FAIL
    mcp_status = sysinfo.get_mcp_status()
    mcp_icons = "".join(
        f" {fg(C_AUTHD_OK if authd else C_AUTHD_FAIL)}{server.icon}"
        for server in MCP_SERVERS
        if (authd := mcp_status.get(server.name)) is not None
    )
    status_text = (
        f" {fg(gh_color)}{ICON_GITHUB}"
        f" {fg(acli_color)}{ICON_ATLASSIAN_CLI}"
        f"{' |' if mcp_icons else ''}{mcp_icons}  "
    )
    # fg_color unused here since we embed colors inline; set to 0
    segments.append(Segment(status_text, 0, C_STATUS_ICONS_BG))

    if debug_info:
        segments.append(Segment(f" {debug_info} ", C_AUTHD_FAIL, C_STATUS_ICONS_BG))

    return render_segments(segments)


def main():
    print(render_statusline())


if __name__ == "__main__":
    main()
