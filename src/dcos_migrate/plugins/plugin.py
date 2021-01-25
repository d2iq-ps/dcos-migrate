from typing import List
from dcos_migrate.system import DCOSClient, BackupList, ManifestList


class MigratePlugin(object):
    """docstring for Migrator."""
    plugin_name: str = 'OVERRIDE'
    backup_depends: List[str] = []
    backup_data_depends: List[str] = []
    migrate_depends: List[str] = []
    migrate_data_depends: List[str] = []
    config_options: List = []

    def __init__(self, config={}):
        self.plugin_config = config

    def backup(self, client: DCOSClient, backupList: BackupList, **kwargs) -> BackupList:
        pass

    def backup_data(self, client: DCOSClient, **kwargs):
        pass

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs) -> ManifestList:
        pass

    def migrate_data(self, backupList: BackupList, manifestList: ManifestList, **kwargs):
        pass
