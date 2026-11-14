"""Host-independent paths for the Fortune Oracle tests.

Paths are derived from this checkout and the isolated test environment.
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")


def repo_path(rest=""):
    return os.path.join(REPO_ROOT, rest) if rest else REPO_ROOT


def repo_plugin_path(rest=""):
    """Use the entrypoint from the same checkout as the tested library."""
    root = repo_path("plugins/fortune_oracle_plugin")
    return os.path.join(root, rest) if rest else root


def hermes_path(rest=""):
    return os.path.join(HERMES_HOME, rest) if rest else HERMES_HOME
