from dcos_migrate.plugins.plugin_manager import PluginManager
from dcos_migrate.plugins.plugin import MigratePlugin


def test_auto_discovery():
    pm = PluginManager()

    assert "cluster" in pm.plugins.keys()
    assert "marathon" in pm.plugins.keys()
    assert "secret" in pm.plugins.keys()


def test_dependencies():
    class Test1Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test1"
        # No depends wanna run first

        def __init__(self):
            super(Test1Plugin, self).__init__()

    class Test2Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test2"
        migrate_depends = ['test1']

        def __init__(self):
            super(Test1Plugin, self).__init__()

    class Test3Plugin(MigratePlugin):
        """docstring for ClusterPlugin."""
        plugin_name = "test3"
        migrate_depends = ['test1', 'test2']

        def __init__(self):
            super(Test1Plugin, self).__init__()

    pm = PluginManager(plugins={
        'test1': Test1Plugin,
        'test2': Test2Plugin,
        'test3': Test3Plugin
    })

    assert len(pm.plugins) == 3
    assert len(pm.migrate) == 3

    assert pm.migrate_batch == [[pm.plugins['test1']],
                                [pm.plugins['test2']],
                                [pm.plugins['test3']]
                                ]

    # assert pm.migrate_batch is None
