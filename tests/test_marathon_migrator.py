from dcos_migrate.plugins.marathon import MarathonMigrator
import json


def test_id_parse():
    assert MarathonMigrator.parse_id("/foo/bar") == "bar.foo"
    assert MarathonMigrator.parse_id("/foo/bar_baz") == "bar-baz.foo"


def test_simple():
    with open('tests/examples/simple.json') as json_file:
        data = json.load(json_file)

        m = MarathonMigrator(object=data)

        mres = m.migrate()

        assert mres is not None
        assert m.manifest[0].metadata.name == 'predictionio-server.group1'
