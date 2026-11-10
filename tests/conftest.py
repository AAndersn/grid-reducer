from pathlib import Path

import pytest

from grid_reducer import model_io

FIXTURES = Path(__file__).parent / "fixtures"
IEEE13 = FIXTURES / "IEEE13_CDPSM" / "IEEE13_CDPSM.cimtbl"
PROTECTION = FIXTURES / "protection" / "protection.cimtbl"


@pytest.fixture
def ieee13_path():
    return IEEE13


@pytest.fixture
def ieee13():
    return model_io.load_model(IEEE13)


@pytest.fixture
def protection():
    return model_io.load_model(PROTECTION)
