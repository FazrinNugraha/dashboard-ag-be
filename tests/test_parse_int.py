"""Unit test parse_int dari sheets_repository."""
import pytest

from app.repositories.sheets_repository import parse_int


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        ("", 0),
        ("   ", 0),
        (0, 0),
        (8_000_000, 8_000_000),
        (8_000_000.4, 8_000_000),
        ("8000000", 8_000_000),
        ("8.000.000", 8_000_000),
        ("Rp 8.000.000", 8_000_000),
        ("6,700,000", 6_700_000),
        ("3,000.000", 3_000_000),
        ("21.700.000", 21_700_000),
        ("-1.500.000", -1_500_000),
        ("2.1E+07", 21_000_000),
        ("2.1e7", 21_000_000),
        ("1.2345E+06", 1_234_500),
        ("Rp -", 0),
        ("abc", 0),
    ],
)
def test_parse_int(raw, expected):
    assert parse_int(raw) == expected