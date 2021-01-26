import importlib
import pkgutil
import inspect
import logging
from typing import Dict, List

import dcos_migrate.plugins
from dcos_migrate.plugins.plugin import MigratePlugin


def is_plugin(obj):
    return (
        inspect.isclass(obj)
        and issubclass(obj, MigratePlugin)
        and obj.plugin_name is not None
    )


def get_dependency_batches(
    plugins: Dict[str, MigratePlugin], depattr: str
) -> List[List[MigratePlugin]]:
    """
    Return a list of lists of plugins. The plugins in the first list must be run
    before the plugins in the second list, and so on, for each list.
    [
        [ Plugin, PlugIn ],
        [ Plugin ],
    ]
    """
    batches = []
    p_deps = {}
    # build a map of plugin names and assign it the
    # list of dependencies in `depattr`
    for p in plugins.values():
        p_deps[p.plugin_name] = set(getattr(p, depattr))

    # `p_deps` is now a dictionary mapping each plugin names to the set of
    # plugins that are required to run before it.

    while p_deps:
        # Create a list of plugins that have no further dependencies.
        nodeps = [name for name, deps in p_deps.items() if not deps]

        if not nodeps:
            raise ValueError("Circular plugin dependency")

        # Delete collected plugins from `p_deps` (must be done outside iteration).
        for name in nodeps:
            del p_deps[name]

        # Remove collected plugins from remaining plugin dependencies.
        for deps in p_deps.values():
            deps.difference_update(nodeps)

        # Create the next batch of plugins.
        batch = [plugins[name] for name in nodeps]

        batches.append(batch)

    return batches


class PluginManager(object):
    """docstring for PluginManager."""

    plugin_namespace = dcos_migrate.plugins

    def __init__(self, plugins={}):

        self.backup = []
        self.backup_data = []
        self.migrate = []
        self.migrate_data = []
        self.plugins = plugins

        self.build_dependencies()

        # auto load plugins if not statically specified
        if not plugins:
            self.discover_modules()

    def iter_namespace(self):
        return pkgutil.iter_modules(self.plugin_namespace.__path__,
                                    self.plugin_namespace.__name__ + ".")

    @ property
    def backup_batch(self):
        """list: List of list of tuples plugin name and plugin class."""
        return self.backup

    @ property
    def backup_data_batch(self):
        """list: List of tuples plugin name and plugin class."""
        return self.backup_data

    @ property
    def migrate_batch(self):
        """list: List of tuples plugin name and plugin class."""
        return self.migrate

    @ property
    def migrate_data_batch(self):
        """list: List of tuples plugin name and plugin class."""
        return self.migrate_data

    def discover_modules(self):
        # https://packaging.python.org/guides/creating-and-discovering-plugins/#using-namespace-packages
        for finder, name, ispkg in self.iter_namespace():
            plugin_module = importlib.import_module(name)

            for clsName, cls in inspect.getmembers(plugin_module, is_plugin):
                logging.info(
                    "found plugin {} - {}".format(cls.plugin_name, clsName))
                self.plugins[cls.plugin_name] = cls()

        # if we discover we need to build dependencies
        self.build_dependencies()

    def build_dependencies(self):
        self.backup = get_dependency_batches(plugins=self.plugins,
                                             depattr="backup_depends")
        logging.debug("Backup batches {}".format(self.backup))
        self.backup_data = get_dependency_batches(plugins=self.plugins,
                                                  depattr="backup_data_depends")
        logging.debug("Backup Data batches {}".format(self.backup_data))
        self.migrate = get_dependency_batches(plugins=self.plugins,
                                              depattr="migrate_depends")
        logging.debug("Migrate batches {}".format(self.migrate))
        self.migrate_data = get_dependency_batches(plugins=self.plugins,
                                                   depattr="migrate_data_depends")
        logging.debug("Migrate Data batches {}".format(self.migrate_data))
