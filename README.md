# Claude Code Status Line

- [Claude Code Status Line](#claude-code-status-line)
  - [Introduction](#introduction)
  - [Installation](#installation)
    - [Configuration](#configuration)
    - [Upgrade](#upgrade)
  - [Features](#features)
    - [Segments](#segments)
      - [Segment breakdown](#segment-breakdown)
      - [Detected languages](#detected-languages)
    - [Caching](#caching)
  - [Development](#development)
    - [Testing](#testing)
    - [Build and publish](#build-and-publish)
      - [Configure Publishing to Pypi](#configure-publishing-to-pypi)
      - [Publishing to Test Pypi](#publishing-to-test-pypi)
      - [Publishing to Pypi](#publishing-to-pypi)

## Introduction

Powerline-style status line for
[Claude Code](https://code.claude.com/docs/en/statusline).

Requires a [Nerd Font](https://www.nerdfonts.com/font-downloads) installed and
setup as your terminals default font.

Recommendation is to install either:

- FiraCode Nerd Font
- JetBrainsMono Nerd Font

## Installation

```bash
pip install cc-statusline
```

On newer Linux systems, install with:

```bash
pip3 install --break-system-packages cc-statusline
```

It is recommended to install this status line with the cost tracking hook:

- `cc-costtrack`

see [cc-costtrack](https://github.com/jalansari/cc-costtrack).

### Configuration

Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "cc-statusline"
  }
}
```

### Upgrade

Upgrade with pip regularly:

```bash
pip install cc-statusline -U
```

On newer Linux systems, install with:

```bash
pip3 install --break-system-packages cc-statusline -U
```

## Features

### Segments

```
project   >   branch_name   >   ai_model   >   ctx% | tokens | cost   >   quota / usages / enterprise   >   cli | mcp
```

Example (Pro/Max plan):

```
 my-app   >   feat/abc123   >   Opus 4.6   >   12% | 58.3k | 1.42$   >   34% (2h05m)   >   61% (4.2d)   >   cli | mcp
```

Example (Enterprise plan):

```
 my-app   >   feat/abc123   >   Opus 4.6   >   12% | 58.3k | 1.42$   >   $78.50 22d   >   cli | mcp
```

#### Segment breakdown

| #   | Segment          | Description                                                                                                                                                                  |
| --- | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Directory**    | Current working directory name.                                                                                                                                              |
| 2   | **Git branch**   | Branch name with color coding: red for `main`/`master`, yellow for `staging`, blue otherwise. Shows worktree icon if in a worktree. And, language icon, based on best guess. |
| 3   | **Model**        | Active Claude model name.                                                                                                                                                    |
| 4   | **Context**      | Context window usage: percentage, input tokens, and session cost (USD). Turns red at 80%+ usage.                                                                             |
| 5a  | **Window quota** | *(Pro/Max only)* 5-hour rolling usage percentage and time until reset.                                                                                                       |
| 5b  | **Weekly quota** | *(Pro/Max only)* 7-day usage percentage and time until reset.                                                                                                                |
| 5c  | **Enterprise**   | *(Enterprise only)* Monthly cumulative cost* (all sessions) and days remaining in billing period.                                                                            |
| 6a  | **CLI Services** | Auth status for CLI services (green = authenticated, red = not): GitHub CLI, Atlassian CLI.                                                                                  |
| 6b  | **Services**     | Auth status for MCP services (green = authenticated, red = not): Notion MCP, Atlassian MCP, Figma MCP.                                                                       |

\* Cost is estimated, and requires the cost tracking hook to function.

#### Detected languages

The branch segment appends an icon for the detected project language:

- Terraform
- Node.js
- TypeScript
- Python
- Rust
- Go
- Java
- Perl
- Shell

### Caching

Data is cached at multiple tiers to keep the status line fast:

| TTL | Data                                              |
| --- | ------------------------------------------------- |
| 1s  | Git branch, stdin JSON (session data).            |
| 10s | CLI/MCP auth status checks.                       |
| 60s | Directory name, language detection, monthly cost. |
| 5m  | API rate limit usage (Pro/Max).                   |

## Development

Set up a virtual environment:

```bash
python3 -m venv .venv
```

Activate the virtual environment before running any of the steps below:

```bash
source .venv/bin/activate
```

### Testing

```bash
pip install -e ".[test]"
pytest
```

### Build and publish

Build the distribution:

```bash
pip install -e ".[package]"
python -m build
```

This creates `dist/` with `.tar.gz` and `.whl` files.

#### Configure Publishing to Pypi

Configure PyPI credentials in `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-<your-api-token>

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-<your-test-api-token>
```

API tokens can be created at:

- PyPI: https://pypi.org/manage/account/token/
- TestPyPI: https://test.pypi.org/manage/account/token/

Alternatively, set credentials via environment variables instead of `~/.pypirc`:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-<your-api-token>
```

To target TestPyPI, override the repository URL:

```bash
export TWINE_REPOSITORY_URL=https://test.pypi.org/legacy/
```

#### Publishing to Test Pypi

To publish to TestPyPI first:

```bash
pip install -e ".[package,publish]"

# Using ini file:
twine upload --repository testpypi dist/*

# Or, with environment variables:
export TWINE_REPOSITORY_URL=https://test.pypi.org/legacy/
twine upload dist/*
```

#### Publishing to Pypi

Publish to PyPI:

```bash
pip install -e ".[publish]"
twine upload dist/*
```
