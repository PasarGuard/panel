import glob
import importlib.util
import sys
from os.path import basename, dirname, join

modules = glob.glob(join(dirname(__file__), "*.py"))

for file in modules:
    name = basename(file).replace(".py", "")
    if name.startswith("_"):
        continue

    # Load job modules under the proper package path so multiprocessing pickling works
    module_name = f"{__name__}.{name}"
    spec = importlib.util.spec_from_file_location(module_name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
