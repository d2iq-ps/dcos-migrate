from dcos_migrate.system import ManifestList, Manifest
from kubernetes.client.models import V1ObjectMeta, V1Secret
import pytest


def create_example_list_manifest(dir: str) -> ManifestList:
    list = ManifestList(path=str(dir))

    p = "testPlugin"
    b = "foobar"
    metadata = V1ObjectMeta(name="secret1")
    sec = V1Secret(metadata=metadata, kind="Secret", api_version="v1")
    sec.data = {
        "secret1": "Zm9vYmFy"
    }
    d = [sec]
    list.append(Manifest(pluginName=p,
                         manifestName=b, data=d))

    list.store()
    return list, p, b, d


def test_load():
    ml = ManifestList(path='tests/examples/simpleWithSecret')
    ml.load()

    assert ml is not None
    assert len(ml) == 2
    assert ml[0] is not None
    assert len(ml[0]) > 0
    assert ml[0][0].kind == "Secret"
    assert ml[0][0].api_version == "v1"
    assert ml[0][0].data is not None
    assert ml[0][0].data == {'secret1': 'Zm9vYmFy'}


def test_load_manifest(tmpdir):
    dir = tmpdir.mkdir("test")
    list, p, b, d = create_example_list_manifest(str(dir))

    list2 = ManifestList(path=str(dir))
    list2.load()

    # we expect different objects
    assert list == list2
    # but the same amount

    assert len(list) == len(list2)
    # and data
    assert list[0][0].data == list2[0][0].data
