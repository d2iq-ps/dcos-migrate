#!/usr/bin/env python
import logging
import sys

from typing import List

from dcos_migrate.system import DCOSClient, BackupList, ManifestList, ArgParse
from dcos_migrate.plugins.plugin_manager import PluginManager


class DCOSMigrate(object):
    """docstring for DCOSMigrate."""

    def __init__(self):
        super(DCOSMigrate, self).__init__()
        self.client = DCOSClient()
        self.pm = PluginManager()
        self.manifest_list = ManifestList()
        self.backup_list = BackupList()
        self.arpparse = ArgParse(
            self.pm.config_options,
            prog='dcos_migrate',
            usage='Does a backup of your DC/OS cluster and migrates everything into K8s Manifests'
        )

    def run(self, args: List[str]):
        self.handleArgparse(args)
        self.backup()
        self.migrate()

    def handleArgparse(self, args: List[str]):
        self.pm.config = self.arpparse.parse_args(args)

    def backup(self, pluginName=None):
        logging.info("Calling {} Backup Batches".format(
            len(self.pm.backup_batch)))
        for batch in self.pm.backup_batch:
            # each batch could also be executed in parallel.
            # But for now just start sequential
            for plugin in batch:
                logging.info(
                    "Calling backup for plugin {}".format(plugin.plugin_name))
                blist = plugin.backup(
                    client=self.client, backupList=self.backup_list)
                if blist:
                    self.backup_list.extend(blist)

        self.backup_list.store()

    def backup_data(self, pluginName=None):
        # for batch in self.pm.backup_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         blist = plugin.backup_data(DCOSClient=self.client)
        #         self.backup_data_list.extend(blist)
        pass

    def migrate(self, pluginName=None):
        for batch in self.pm.migrate_batch:
            # each batch could also be executed in parallel.
            # But for not just start sequencial
            for plugin in batch:
                mlist = plugin.migrate(
                    backupList=self.backup_list, manifestList=self.manifest_list)
                if mlist:
                    self.manifest_list.extend(mlist)

        self.manifest_list.store()

    def migrate_data(self, pluginName=None):
        # for batch in self.pm.migrate_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         mlist = plugin.migrate(
        #             backupList=self.backup_list, manifestList=self.manifest_list)
        #         self.manifest_list.extend(mlist)
        pass

    def get_plugin_names(self):
        return self.pm.plugins.keys()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    DCOSMigrate().run(sys.argv)
