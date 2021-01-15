import json
import logging
import re
from jsonpath_ng.ext import parse
from dcos_migrate.system import ManifestList, BackupList, Backup, Manifest


class Migrator(object):
    """docstring for Migrator."""

    _invalid_secret_key = re.compile("[^-._a-zA-Z0-9]")

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

    def clean_key(self, s: str) -> str:
        # Replace DC/OS folders with dots
        s = s.replace("/", ".")
        # Replace other invalid characters with `_`
        # `folder/sec!ret` becomes `folder.sec_ret`
        return self._invalid_secret_key.sub("_", s).lstrip(".")

    def dnsify(self, name):
        new_name = re.sub("[^a-z0-9-]+", "-", name.lower())
        if not name == new_name:
            logging.info(
                f'"{name}" is not a valid name in kubernetes. converted it to "{new_name}".'
            )
        return new_name

    def migrate(self) -> Manifest:
        if not self.valid():
            return None

        for k, v in self.translate.items():
            expr = parse(k)
            for match in expr.find(self.object):
                v(match.path, match.value, match.full_path)

        return self.manifest

    def noEquivalent(self, key, value, full_path):
        logging.warning("No equivalent availbale for {full_path} with value {value}".format(
            full_path=full_path, value=value))
