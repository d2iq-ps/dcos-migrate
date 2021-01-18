from dcos_migrate.plugins.marathon import MarathonMigrator
from dcos_migrate.system import ManifestList
import json
import pytest


def test_simple():
    with open('tests/examples/simple.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data)

        mres = m.migrate()

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0]['metadata']['name'] == 'group1.predictionio-server'


@pytest.mark.xfail
def test_simple_portmapping():
    with open('tests/examples/simplePortmapping.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data)

        mres = m.migrate()

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0]['metadata']['name'] == 'group1.predictionio-server'


def test_simple_with_secret():
    ml = ManifestList(path='tests/examples/simpleWithSecret')
    ml.load()

    assert len(ml) == 2
    with open('tests/examples/simpleWithSecret.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data, manifest_list=ml)

        mres = m.migrate()

        assert len(m.manifest) > 1

        assert mres is not None
        # assert m.manifest[0]['metadata']['name'] == 'predictionio-server.group1'
        assert m.manifest[0]['metadata']['name'] == 'group1.predictionio-server'
