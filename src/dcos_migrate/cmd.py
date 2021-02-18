import logging
import sys

from typing import Iterable, List, Optional

from dcos_migrate.system import DCOSClient, BackupList, ManifestList, ArgParse, Arg
from dcos_migrate.plugins.plugin_manager import PluginManager


class DCOSMigrate(object):
    """docstring for DCOSMigrate."""

    config_defaults = [
        Arg(
            name="phase",
            nargs="?",
            choices=["backup", "backup_data",
                     "migrate", "migrate_data", "all"],
            default="all",
            positional=True,
            help="phase to start with."
        ),
        Arg(
            name="verbose",
            alternatives=["-v"],
            action="count",
            default=0,
            help="log verbosity. Default to critical"
        )
    ]

    def __init__(self) -> None:
        super(DCOSMigrate, self).__init__()
        self.client = DCOSClient()
        self.pm = PluginManager()
        self.manifest_list = ManifestList()
        self.backup_list = BackupList()

        config = self.pm.config_options
        config.extend(self.config_defaults)
        self.argparse = ArgParse(
            config,
            prog='dcos-migrate',
            usage='Does a backup of your DC/OS cluster and migrates everything into K8s Manifests'
        )

        self._run = ""

    def _is_not_phase(self, phase: str) -> bool:
        return (not self._is_phase("all") and not self._is_phase(phase))

    def _is_phase(self, phase: str) -> bool:
        return bool(self.pm.config['global']['phase'] == phase)

    def _end_process(self, message: str, exit_code: int = 0) -> None:
        print("Ending process - {}".format(message))
        sys.exit(exit_code)

    def run(self, args: Optional[List[str]] = None) -> None:
        self.handleArgparse(args)
        self.handleGlobal()

        self.backup()
        self.backup_data()
        self.migrate()
        self.migrate_data()

    def handleGlobal(self) -> None:
        # logging
        levels = [logging.CRITICAL, logging.WARNING,
                  logging.INFO, logging.DEBUG]

        v = self.pm.config['global'].get('verbose', 0)
        level = levels[min(len(levels)-1, v)]
        logging.basicConfig(level=level, force=True)

    def handleArgparse(self, args: Optional[List[str]] = None) -> None:
        if args is None:
            args = []
        self.pm.config = self.argparse.parse_args(args)

    def backup(self, pluginName: Optional[str] = None) -> None:
        if self._is_not_phase("backup"):
            logging.info("skipping backup - trying to load from disk.")
            self.backup_list.load()
            return

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

        if self._is_phase("backup"):
            self._end_process("Backup finished")

    def backup_data(self, pluginName: Optional[str] = None) -> None:
        if self._is_not_phase("backup_data"):
            logging.info("skipping backup data")
            return
        # for batch in self.pm.backup_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         blist = plugin.backup_data(DCOSClient=self.client)
        #         self.backup_data_list.extend(blist)

        if self._is_phase("backup_data"):
            self._end_process("Backup data finished")

    def migrate(self, pluginName: Optional[str] = None) -> None:
        if self._is_not_phase("migrate"):
            logging.info("skipping migrate - trying to load from disk.")
            self.manifest_list.load()
            return

        for batch in self.pm.migrate_batch:
            # each batch could also be executed in parallel.
            # But for not just start sequencial
            for plugin in batch:
                mlist = plugin.migrate(
                    backupList=self.backup_list, manifestList=self.manifest_list)
                if mlist:
                    self.manifest_list.extend(mlist)

        self.manifest_list.store()

        if self._is_phase("migrate"):
            self._end_process("Migrate finished")

    def migrate_data(self, pluginName: Optional[str] = None) -> None:
        if self._is_not_phase("migrate_data"):
            logging.info("skipping migrate data")
            return
        # for batch in self.pm.migrate_batch:
        #     # each batch could also be executed in parallel.
        #     # But for not just start sequencial
        #     for plugin in batch:
        #         mlist = plugin.migrate(
        #             backupList=self.backup_list, manifestList=self.manifest_list)
        #         self.manifest_list.extend(mlist)
        if self._is_phase("migrate_data"):
            self._end_process("Migrate data finished")

    def get_plugin_names(self) -> Iterable[str]:
        return self.pm.plugins.keys()


def run() -> None:
    DCOSMigrate().run()
