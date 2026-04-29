from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires live API keys and network access")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--integration", default=False):
        return
    skip = pytest.mark.skip(reason="integration test — run with --integration flag")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--integration", action="store_true", default=False, help="run integration tests")
