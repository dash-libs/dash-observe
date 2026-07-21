"""discover_tables() needs a live SparkSession for the actual query — only
its input validation is unit-testable here."""
import pytest

from dashobserve.runner import discover_tables


def test_discover_tables_rejects_bare_catalog():
    with pytest.raises(ValueError, match="catalog.schema"):
        discover_tables("just_a_catalog")
