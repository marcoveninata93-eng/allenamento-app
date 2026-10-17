import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import plan as P  # noqa: E402


@pytest.fixture
def plan():
    return P.load_default_plan()


@pytest.fixture
def videos():
    return P.load_videos()
