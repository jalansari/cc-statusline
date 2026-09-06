import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest

import cc_statusline as cc_sl

# ------------------------------------------------------------------------------
# Pure helper tests: fg, bg
# ------------------------------------------------------------------------------


class TestAnsiHelpers:
    def test_fg(self):
        assert cc_sl.fg(34) == "\033[38;5;34m"

    def test_bg(self):
        assert cc_sl.bg(18) == "\033[48;5;18m"

    def test_fg_zero(self):
        assert cc_sl.fg(0) == "\033[38;5;0m"

    def test_bg_zero(self):
        assert cc_sl.bg(0) == "\033[48;5;0m"


# ------------------------------------------------------------------------------
# Test _format_time_remaining
# ------------------------------------------------------------------------------


class TestFormatTimeRemaining:
    def test_minutes_only(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=42)
        iso = future.isoformat()
        result = cc_sl._format_time_remaining(iso)
        assert result.endswith("m")
        assert "h" not in result
        minutes = int(result.rstrip("m"))
        assert minutes == pytest.approx(42, abs=1)

    def test_hours_and_minutes(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2, minutes=13)
        iso = future.isoformat()
        result = cc_sl._format_time_remaining(iso)
        # e.g. "2h13m" or "2h12m"
        hr, mins = result.split("h")
        assert int(hr) == 2
        assert int(mins.rstrip("m")) == pytest.approx(13, abs=1)

    def test_days(self):
        future = datetime.now(timezone.utc) + timedelta(days=3)
        iso = future.isoformat()
        result = cc_sl._format_time_remaining(iso)
        # Source uses hours // 24 (integer division), so 71h59m → "2.0d"
        assert result.endswith("d")
        days = float(result.rstrip("d"))
        assert days == pytest.approx(3, abs=1)

    def test_past_timestamp_returns_zero_minutes(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        iso = past.isoformat()
        result = cc_sl._format_time_remaining(iso)
        assert result == "0m"

    def test_with_z_suffix(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1, minutes=30)
        iso = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = cc_sl._format_time_remaining(iso)
        hr, mins = result.split("h")
        assert int(hr) == 1
        assert int(mins.rstrip("m")) == pytest.approx(30, abs=1)

    @pytest.mark.parametrize(
        "invalid_input",
        [
            None,
            "",
            "not-a-date",
            "abc123",
            "2026-13-99T00:00:00Z",
        ],
    )
    def test_invalid_input_returns_unknown_default_string(self, invalid_input):
        assert cc_sl._format_time_remaining(invalid_input) == "?m"


# ------------------------------------------------------------------------------
# LangDetectRules.matches
# ------------------------------------------------------------------------------


class TestLangDetectRules:
    def test_matches_by_file(self):
        rule = cc_sl.LangDetectRules(
            icon="P", files=["pyproject.toml"], extensions=[], folders=[], prefixes=[]
        )
        assert rule.matches(["pyproject.toml", "README.md"])

    def test_matches_by_extension(self):
        rule = cc_sl.LangDetectRules(
            icon="P", files=[], extensions=[".py"], folders=[], prefixes=[]
        )
        assert rule.matches(["main.py", "README.md"])

    def test_matches_by_prefix(self):
        rule = cc_sl.LangDetectRules(
            icon="T", files=[], extensions=[], folders=[], prefixes=[".terraform"]
        )
        assert rule.matches([".terraform.lock.hcl", "main.tf"])

    @patch("os.path.isdir", return_value=True)
    def test_matches_by_folder(self, mock_isdir):
        rule = cc_sl.LangDetectRules(
            icon="N", files=[], extensions=[], folders=["node_modules"], prefixes=[]
        )
        assert rule.matches(["node_modules", "index.js"])

    @patch("os.path.isdir", return_value=False)
    def test_folder_not_a_dir(self, mock_isdir):
        rule = cc_sl.LangDetectRules(
            icon="N", files=[], extensions=[], folders=["node_modules"], prefixes=[]
        )
        assert rule.matches(["node_modules"]) is False

    def test_no_match(self):
        rule = cc_sl.LangDetectRules(
            icon="P", files=["Cargo.toml"], extensions=[".rs"], folders=[], prefixes=[]
        )
        assert rule.matches(["main.py", "README.md"]) is False

    def test_empty_entries(self):
        rule = cc_sl.LangDetectRules(
            icon="P", files=["pyproject.toml"], extensions=[], folders=[], prefixes=[]
        )
        assert rule.matches([]) is False


# ------------------------------------------------------------------------------
# Segment and render_segments
# ------------------------------------------------------------------------------


class TestSegment:
    def test_segment_creation(self):
        seg = cc_sl.Segment(text=" hi ", fg_color=255, bg_color=18, bold=True)
        assert seg.text == " hi "
        assert seg.bold is True

    def test_segment_default_not_bold(self):
        seg = cc_sl.Segment(text="x", fg_color=0, bg_color=0)
        assert seg.bold is False


class TestRenderSegments:
    def test_empty_list(self):
        assert cc_sl.render_segments([]) == ""

    def test_single_segment_has_reset(self):
        segs = [cc_sl.Segment(" test ", 255, 18)]
        result = cc_sl.render_segments(segs)
        assert cc_sl.RESET in result
        assert cc_sl.SEP_RIGHT in result
        assert result.startswith(
            cc_sl.fg(255) + cc_sl.bg(18) + " test "
        )  # Should start with segment styling
        assert result.endswith(cc_sl.RESET)  # Should end with reset

    def test_two_segments_have_separator(self):
        segs = [
            cc_sl.Segment(" a ", 255, 18),
            cc_sl.Segment(" b ", 250, 233),
        ]
        result = cc_sl.render_segments(segs)
        # The separator between them should use seg1.bg as fg and seg2.bg as bg
        assert cc_sl.SEP_RIGHT in result
        assert result.count(cc_sl.SEP_RIGHT) == 2
        assert " a " in result
        assert " b " in result

    def test_bold_segment(self):
        segs = [cc_sl.Segment(" bold ", 255, 18, bold=True)]
        result = cc_sl.render_segments(segs)
        assert cc_sl.BOLD in result
        assert "\033[22m" in result  # bold off


# ------------------------------------------------------------------------------
# Cache
# ------------------------------------------------------------------------------


class TestCache:
    def test_read_fresh_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        with patch.object(cc_sl, "CACHE_DIR", cache_dir):
            cache = cc_sl.Cache("test.json", ttl=60)
            data = {"key": "value"}
            cache.write(data)
            assert cache.read() == data

    def test_read_stale_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        with patch.object(cc_sl, "CACHE_DIR", cache_dir):
            cache = cc_sl.Cache("test.json", ttl=1)
            cache.write({"key": "value"})
            # Make the file appear old
            old_time = time.time() - 10
            os.utime(cache.path, (old_time, old_time))
            assert cache.read() == {}

    def test_read_missing_cache(self, tmp_path):
        cache_dir = str(tmp_path)
        with patch.object(cc_sl, "CACHE_DIR", cache_dir):
            cache = cc_sl.Cache("nonexistent.json", ttl=60)
            assert cache.read() == {}

    def test_write_creates_dir_and_file(self, tmp_path):
        cache_dir = os.path.join(str(tmp_path), "subdir")
        with patch.object(cc_sl, "CACHE_DIR", cache_dir):
            cache = cc_sl.Cache("test.json", ttl=60)
            cache.write({"a": 1})
            assert os.path.isdir(cache_dir)
            assert os.path.isfile(cache.path)


# ------------------------------------------------------------------------------
# SystemInfo.get_auth_mode
# ------------------------------------------------------------------------------


class TestGetAuthMode:
    CREDS_ATTR = "_SystemInfo__get_creds_data"

    def test_enterprise(self):
        si = cc_sl.SystemInfo("s")
        with patch.object(
            cc_sl.SystemInfo,
            self.CREDS_ATTR,
            return_value={"claudeAiOauth": {"subscriptionType": "enterprise"}},
        ):
            assert si.get_auth_mode() == "enterprise"

    def test_oauth(self):
        si = cc_sl.SystemInfo("s")
        with patch.object(
            cc_sl.SystemInfo,
            self.CREDS_ATTR,
            return_value={"claudeAiOauth": {"accessToken": "abc"}},
        ):
            assert si.get_auth_mode() == "oauth"

    def test_api_key_when_no_oauth_token(self):
        si = cc_sl.SystemInfo("s")
        with patch.object(
            cc_sl.SystemInfo,
            self.CREDS_ATTR,
            return_value={"claudeAiOauth": {}},
        ):
            assert si.get_auth_mode() == "api_key"

    def test_enterprise_wins_over_access_token(self):
        si = cc_sl.SystemInfo("s")
        with patch.object(
            cc_sl.SystemInfo,
            self.CREDS_ATTR,
            return_value={
                "claudeAiOauth": {
                    "subscriptionType": "enterprise",
                    "accessToken": "abc",
                }
            },
        ):
            assert si.get_auth_mode() == "enterprise"


# ------------------------------------------------------------------------------
# _profile_key and per-profile usage cache paths
# ------------------------------------------------------------------------------


class TestProfileKey:
    def test_default_config_dir(self):
        with patch.dict(os.environ, {}, clear=True):
            assert cc_sl._profile_key().startswith("claude_")

    def test_slug_comes_from_config_dir_basename(self, tmp_path):
        alt = tmp_path / ".claude-alt"
        alt.mkdir()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(alt)}):
            assert cc_sl._profile_key().startswith("claude-alt_")

    def test_differs_between_profiles(self, tmp_path):
        keys = set()
        for name in (".claude", ".claude-alt"):
            path = tmp_path / name
            path.mkdir()
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(path)}):
                keys.add(cc_sl._profile_key())
        assert len(keys) == 2

    def test_same_basename_different_parent_does_not_collide(self, tmp_path):
        keys = set()
        for parent in ("work", "personal"):
            path = tmp_path / parent / ".claude"
            path.mkdir(parents=True)
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(path)}):
                keys.add(cc_sl._profile_key())
        assert len(keys) == 2

    def test_stable_across_calls(self, tmp_path):
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(tmp_path)}):
            assert cc_sl._profile_key() == cc_sl._profile_key()

    # The test cases, using unusual config dirs may not be valid usage, but we
    # handle the edge case paths anyway, resulting with a fall-back to "claude".

    def test_root_config_dir_falls_back_to_default_slug(self):
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/"}):
            assert cc_sl._profile_key().startswith("claude_")

    def test_all_dot_basename_falls_back_to_default_slug(self, tmp_path):
        dots = tmp_path / "..."
        dots.mkdir()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(dots)}):
            assert cc_sl._profile_key().startswith("claude_")

    def test_fallback_never_yields_an_empty_slug(self, tmp_path):
        dots = tmp_path / "..."
        dots.mkdir()
        for config_dir in ("/", str(dots)):
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": config_dir}):
                slug, _, digest = cc_sl._profile_key().rpartition("_")
                assert slug
                assert len(digest) == 8

    def test_fallback_slug_still_keys_distinctly_from_real_default(self, tmp_path):
        default = tmp_path / ".claude"
        default.mkdir()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(default)}):
            default_key = cc_sl._profile_key()
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/"}):
            root_key = cc_sl._profile_key()
        # Both slugs read "claude"; only the realpath hash keeps them apart.
        assert default_key.startswith("claude_")
        assert root_key.startswith("claude_")
        assert default_key != root_key


class TestUsageCacheIsPerProfile:
    @staticmethod
    def __paths_for(config_dir, cache_dir):
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(config_dir)}):
            with patch.object(cc_sl, "CACHE_DIR", str(cache_dir)):
                usage = cc_sl.ClaudeUsageInfo("session")
                return usage.cache.path, usage.backoff_file

    def test_two_profiles_get_distinct_cache_and_backoff_paths(self, tmp_path):
        first = tmp_path / ".claude"
        second = tmp_path / ".claude-alt"
        first.mkdir()
        second.mkdir()
        cache_dir = tmp_path / "cache"

        first_cache, first_backoff = self.__paths_for(first, cache_dir)
        second_cache, second_backoff = self.__paths_for(second, cache_dir)

        assert first_cache != second_cache
        assert first_backoff != second_backoff

    def test_backoff_marker_only_affects_its_own_profile(self, tmp_path):
        first = tmp_path / ".claude"
        second = tmp_path / ".claude-alt"
        first.mkdir()
        second.mkdir()
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        _, first_backoff = self.__paths_for(first, cache_dir)
        with open(first_backoff, "w"):
            pass

        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(second)}):
            with patch.object(cc_sl, "CACHE_DIR", str(cache_dir)):
                usage = cc_sl.ClaudeUsageInfo("session")
                assert not os.path.exists(usage.backoff_file)
