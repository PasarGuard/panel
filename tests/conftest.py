import os
import sys
import warnings

import pytest
from pydantic import PydanticDeprecatedSince20

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from runtime_compat import configure_free_threaded_runtime  # noqa

configure_free_threaded_runtime()
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DEBUG", "0")
# Override the config module for tests
import config  # noqa

config.TESTING = True
config.DEBUG = True
config.SUDOERS["testadmin"] = "testadmin"


# Filter out all warnings
@pytest.fixture(autouse=True)
def ignore_all_warnings():
    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
