import re

import evolution_simulator


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", evolution_simulator.__version__)
