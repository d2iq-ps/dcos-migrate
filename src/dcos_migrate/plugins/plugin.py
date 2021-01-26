from typing import Any, Dict, List
from dcos_migrate.system import DCOSClient, BackupList, ManifestList


class MigratePlugin(object):
    """docstring for Migrator."""
    plugin_name: str = 'OVERRIDE'
    backup_depends: List[str] = []
    backup_data_depends: List[str] = []
    migrate_depends: List[str] = []
    migrate_data_depends: List[str] = []
    config_options: List[str] = []

    def __init__(self, config: Dict[str, str] = {}):
        self.plugin_config = config

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs: Any) -> BackupList:
        pass

    def backup_data(self, client: DCOSClient, **kwargs: Any) -> Any:
        pass

    def migrate(
        self, backupList: BackupList, manifestList: ManifestList, **kwargs: Any
    ) -> ManifestList:
        pass

    def migrate_data(
        self, backupList: BackupList, manifestList: ManifestList, **kwargs: Any
    ) -> Any:
        pass
