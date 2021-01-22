import re

DCOS_MIGRATE_NAMESPACE = "migration.dcos.d2iq.com"


def dnsify(name: str) -> str:
    """
    Replace DC/OS folders with dots and
    replace other invalid characters with `_`

    >>> dnsify("folder/sec!ret")
    "folder.sec_ret"
    """
    _invalid_secret_key = re.compile('[^-._a-zA-Z0-9]')
    # Replace DC/OS folders with dots
    name = ".".join(list(filter(None, name.split("/"))))
    # Replace other invalid characters with `_`
    # `folder/sec!ret` becomes `folder.sec_ret`
    return _invalid_secret_key.sub('_', name)


def namespace_path(*args):
    """
    Uses namespace constant. Adds every argument as path part

    >>> namespace_path("cluster-id")
    "migration.dcos.d2iq.com/cluster-id"

    >>> namespace_path("foo", "bar")
    "migration.dcos.d2iq.com/foo/bar"
    """
    return "/".join([DCOS_MIGRATE_NAMESPACE, *args])
