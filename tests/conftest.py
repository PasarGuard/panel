import os
import sys
import tempfile
import warnings
from collections import Counter
from pathlib import Path

import pytest
from pydantic import PydanticDeprecatedSince20
from sqlalchemy.engine import make_url

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Override settings for tests
from config import auth_settings, runtime_settings, server_settings

runtime_settings.testing = True
runtime_settings.debug = True
server_settings.proxy_headers = True
server_settings.forwarded_allow_ips = "*"
auth_settings.sudoers["testadmin"] = "testadmin"


def pytest_addoption(parser):
    group = parser.getgroup("sharding")
    group.addoption("--shard-index", type=int, help="Zero based CI shard index")
    group.addoption("--shard-count", type=int, help="Number of independent CI shards")


def pytest_collection_modifyitems(config, items):
    index = config.getoption("--shard-index")
    count = config.getoption("--shard-count")
    if index is None and count is None:
        return
    if count is None or index is None or count < 1 or not 0 <= index < count:
        raise pytest.UsageError("Set --shard-index between 0 and --shard-count minus 1")

    # Keep tests from each file together and spread the largest files first.
    file_counts = Counter(item.path for item in items)
    assigned = {}
    loads = [0] * count
    for path, size in sorted(file_counts.items(), key=lambda entry: (-entry[1], str(entry[0]))):
        shard = min(range(count), key=lambda candidate: loads[candidate])
        assigned[path] = shard
        loads[shard] += size

    selected = [item for item in items if assigned[item.path] == index]
    deselected = [item for item in items if assigned[item.path] != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_configure(config):
    """Give each xdist worker its own SQLite database before API test imports."""
    worker = getattr(config, "workerinput", None)
    if worker is None:
        return

    if os.environ.get("TEST_FROM", "local") != "local":
        raise pytest.UsageError("Parallel tests require TEST_FROM=local and SQLite; use serial tests for CI databases")

    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise pytest.UsageError("Parallel tests require a file backed SQLite DATABASE_URL")

    database_dir = Path(tempfile.mkdtemp(prefix=f"pasarguard-pytest-{worker['workerid']}-"))
    config._pasarguard_database_dir = database_dir
    os.environ["DATABASE_URL"] = str(url.set(database=str(database_dir / "test.db")))


def pytest_unconfigure(config):
    database_dir = getattr(config, "_pasarguard_database_dir", None)
    if database_dir is not None:
        for file in database_dir.iterdir():
            file.unlink()
        database_dir.rmdir()


# Filter out all warnings
@pytest.fixture(autouse=True)
def ignore_all_warnings():
    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
