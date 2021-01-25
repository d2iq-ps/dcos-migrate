from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.cluster import ClusterPlugin
from dcos_migrate.plugins.secret import SecretPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup, ManifestList
from .migrator import MarathonMigrator
import logging


class MarathonPlugin(MigratePlugin):
    """docstring for MarathonPlugin."""

    plugin_name = "marathon"
    migrate_depends = [ClusterPlugin.plugin_name, SecretPlugin.plugin_name]

    def __init__(self):
        super(MarathonPlugin, self).__init__()

    def backup(self, client: DCOSClient, **kwargs) -> BackupList:  # type: ignore
        bl = BackupList()
        apps = client.get("{}/marathon/v2/apps".format(client.dcos_url)).json()
        for app in apps['apps']:
            bl.append(self.createBackup(app))

        return bl

    def createBackup(self, app) -> Backup:
        return Backup(pluginName=self.plugin_name,
                      backupName=Backup.renderBackupName(app['id']),
                      data=app)

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs) -> ManifestList:
        ml = ManifestList()

        for b in backupList.backups(pluginName=self.plugin_name):
            mig = MarathonMigrator(backup=b,
                                   backup_list=backupList,
                                   manifest_list=manifestList)

            try:
                manifest = mig.migrate()

                if manifest:
                    ml.append(manifest)
            except Exception as e:
                logging.warning("Cannot migrate: {}".format(e))
        return ml
