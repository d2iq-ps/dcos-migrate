from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.cluster import ClusterPlugin
from dcos_migrate.plugins.secret import SecretPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup, ManifestList

from .migrator import MetronomeMigrator


class MetronomePlugin(MigratePlugin):
    """docstring for MetronomePlugin."""

    plugin_name = "metronome"
    migrate_depends = [ClusterPlugin.plugin_name, SecretPlugin.plugin_name]

    def __init__(self):
        super(MetronomePlugin, self).__init__()

    def backup(self, client: DCOSClient, **kwargs) -> BackupList:  # type: ignore
        bl = BackupList()
        jobs = client.get(
            "{}/service/metronome/v1/jobs".format(client.dcos_url)).json()
        for job in jobs:
            bl.append(self.createBackup(job))

        return bl

    def createBackup(self, job) -> Backup:
        return Backup(pluginName=self.plugin_name,
                      backupName=Backup.renderBackupName(job['id']),
                      data=job)

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs) -> ManifestList:
        ml = ManifestList()

        for b in backupList.backups(pluginName=self.plugin_name):
            mig = MetronomeMigrator(backup=b,
                                    backup_list=backupList,
                                    manifest_list=manifestList)

            manifest = mig.migrate()
            if manifest:
                ml.append(manifest)

        return ml
