import os
import sys
import warnings

import pytest
from pydantic import PydanticDeprecatedSince20

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

# Override settings for tests
from config import auth_settings, runtime_settings, server_settings  # noqa: E402

runtime_settings.testing = True
runtime_settings.debug = True
server_settings.proxy_headers = True
server_settings.forwarded_allow_ips = "*"
auth_settings.sudoers["testadmin"] = "testadmin"


# Filter out all warnings
@pytest.fixture(autouse=True)
def ignore_all_warnings():
    warnings.filterwarnings("ignore")
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
    warnings.filterwarnings("ignore", category=UserWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)
