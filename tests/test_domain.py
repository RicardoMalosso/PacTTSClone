import pytest
from pydantic import ValidationError

from pacttsclone.domain import GenerationRequest


def test_normalizes_fields():
    request = GenerationRequest(text="  Olá.  ", ref_text="  Referência. ")
    assert request.text == "Olá."
    assert request.ref_text == "Referência."
    assert request.language == "auto"


@pytest.mark.parametrize(
    "fields",
    [
        {"text": ""},
        {"text": "  "},
        {"text": "a" * 2001},
        {"speed": 0.49},
        {"speed": 1.51},
        {"speed": float("nan")},
        {"speed": float("inf")},
        {"steps": 3},
        {"steps": 65},
        {"steps": 4.5},
        {"language": "invalid"},
        {"ref_text": "a" * 4001},
        {"unknown": 1},
    ],
)
def test_rejects_invalid_input(fields):
    values = {"text": "Olá.", **fields}
    with pytest.raises(ValidationError):
        GenerationRequest(**values)
