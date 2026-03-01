from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def examples_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def load_module(filename: str, module_name: str):
    path = examples_dir() / filename
    if not path.exists():
        raise AssertionError(f"Expected file missing: {path}")

    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load module spec: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
