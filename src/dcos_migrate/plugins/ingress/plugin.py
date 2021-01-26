#

from dcos_migrate.plugins import plugin
from dcos_migrate import system

from . import edgelb
from . import migrator


class EdgeLBPlugin(plugin.MigratePlugin):
    plugin_name = "edgelb"

    def backup(
        self,
        client: system.DCOSClient,
        backupList: system.BackupList,
        **kwargs
    ) -> system.BackupList:
        service_path = "/service/edgelb"

        if "service_name" in kwargs:
            service_path = "/service/{}/api".format(kwargs["service_name"])

        url = "{}{}/v2/pools".format(client.dcos_url, service_path)

        pools = client.get(url).json()

        if "pool_name" in kwargs:
            pools = [p for p in pools if p["name"] == kwargs["pool_name"]]

        bl = system.BackupList()
        for pool in pools:
            parsed_pool = edgelb.parse_pool(pool)

            if parsed_pool:
                backup = system.Backup(
                    self.plugin_name,
                    system.Backup.renderBackupName(pool["name"]),
                    parsed_pool,
                )
                bl.append(backup)

        return bl

    def migrate(
        self,
        backupList: system.BackupList,
        manifestList: system.ManifestList,
        **kwargs
    ) -> system.ManifestList:
        ml = system.ManifestList()

        for b in backupList.backups(pluginName=self.plugin_name):
            mig = migrator.Ingress(
                backup=b,
                backup_list=backupList,
                manifest_list=manifestList,
            )

            manifest = mig.migrate()
            if manifest:
                ml.append(manifest)

        return ml
