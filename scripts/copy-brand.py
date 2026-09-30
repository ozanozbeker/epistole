"""Copy `_brand.yml` into the build directory, which great-docs recreates on each build."""  # noqa: INP001

import os
import shutil
from pathlib import Path

build = Path(os.environ["QUARTO_PROJECT_DIR"])
shutil.copy2(build.parent / "_brand.yml", build / "_brand.yml")
