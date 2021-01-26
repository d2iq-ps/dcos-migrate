import logging
from jsonpath_ng.ext import parse  # type: ignore
from typing import Optional
from dcos_migrate.system import Manifest
import dcos_migrate.utils as utils


class Migrator(object):
    """docstring for Migrator."""

    def __init__(self, backup=None, backup_list=None, manifest_list=None, object=None):
        super(Migrator, self).__init__()
        self.backup = backup
        self.object = object
        if backup is not None:
            self.object = backup.data
        self.backup_list = backup_list
        self.manifest_list = manifest_list
        self.manifest = None

        self.translate = {}

    def valid(self):
        """Returns True if self.object is what we expect"""
        return True

    def dnsify(self, name: str):
        new_name = utils.dnsify(name)
        if not name == new_name:
            logging.info(
                f'"{name}" is not a valid name in kubernetes. converted it to "{new_name}".'
            )
        return new_name

    def migrate(self) -> Optional[Manifest]:
        if not self.valid():
            return None

        for k, v in self.translate.items():
            expr = parse(k)
            for match in expr.find(self.object):
                v(str(match.path), match.value, str(match.full_path))

        return self.manifest

    def noEquivalent(self, key, value, full_path):
        logging.warning("No equivalent availbale for {full_path} with value {value}".format(
            full_path=full_path, value=value))
