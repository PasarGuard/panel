import os
import sysconfig


def configure_free_threaded_runtime() -> None:
    if sysconfig.get_config_var("Py_GIL_DISABLED") == 1:
        os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")
        os.environ.setdefault("MSGPACK_PUREPYTHON", "1")


configure_free_threaded_runtime()
