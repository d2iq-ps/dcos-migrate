import pytest
from dcos_migrate.utils import dnsify, namespace_path


@pytest.mark.parametrize("path_name, expected_name", [
    ("foo", "foo"),
    ("foo/bar", "foo.bar"),
    ("foo!bar/baz", "foo_bar.baz"),
])
def test_dnsify(path_name, expected_name):
    assert dnsify(path_name) == expected_name


@pytest.mark.parametrize("name, namespaced_name", [
    (["foo"], "migration.dcos.d2iq.com/foo"),
    (["foo", "bar"], "migration.dcos.d2iq.com/foo/bar"),
])
def test_namespace_path(name, namespaced_name):
    assert namespace_path(*name) == namespaced_name
