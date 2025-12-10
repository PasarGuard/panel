import glob
from importlib import import_module
from os.path import basename, dirname, join

modules = glob.glob(join(dirname(__file__), "*.py"))

for file in modules:
    name = basename(file).replace(".py", "")
    if name.startswith("_"):
        continue

    import_module(f"{__name__}.{name}")
