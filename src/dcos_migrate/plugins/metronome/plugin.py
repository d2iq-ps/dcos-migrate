from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.cluster import ClusterPlugin
from dcos_migrate.plugins.secret import SecretPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup


class MetronomePlugin(MigratePlugin):
    """docstring for MarathonPlugin."""

    plugin_name = "metronome"
    depends_migrate = [ClusterPlugin.plugin_name, SecretPlugin.plugin_name]

    def __init__(self):
        super(MetronomePlugin, self).__init__()

    def backup(self, client: DCOSClient, **kwargs) -> BackupList:
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
