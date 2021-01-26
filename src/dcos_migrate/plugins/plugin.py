from typing import List, Dict, Any
from dcos_migrate.system import DCOSClient, BackupList, ManifestList, Arg


class MigratePlugin(object):
    """docstring for Migrator."""
    plugin_name: str = 'OVERRIDE'
    backup_depends: List[str] = []
    backup_data_depends: List[str] = []
    migrate_depends: List[str] = []
    migrate_data_depends: List[str] = []

    def __init__(self, config={}):
        self._config_options = []
        self._config = config
        self._plugin_config = {}
        if self.plugin_name in config:
            self._plugin_config = config[self.plugin_name]

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @config.setter
    def config(self, config: Dict[str, Any]):
        self._config = config
        self._plugin_config = None

        if self.plugin_name in config:
            self._plugin_config = config[self.plugin_name]

    @property
    def plugin_config(self) -> Dict[str, Any]:
        return self._plugin_config

    @property
    def config_options(self) -> List[Arg]:
        return self._config_options

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs) -> BackupList:
        pass

    def backup_data(self, client: DCOSClient, **kwargs):
        pass

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs) -> ManifestList:
        pass

    def migrate_data(self, backupList: BackupList, manifestList: ManifestList, **kwargs):
        pass
