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
