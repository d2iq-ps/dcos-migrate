import pytest
from dcos_migrate.utils import dnsify


@pytest.mark.parametrize("path_name, expected_name", [
    ("foo", "foo"),
    ("foo/bar", "foo.bar"),
    ("foo!bar/baz", "foo_bar.baz"),
])
def test_dnsify(path_name, expected_name):
    assert dnsify(path_name) == expected_name
