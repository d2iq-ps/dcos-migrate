from .storable_list import StorableList
from .backup import Backup
from jsonpath_ng import parse


class BackupList(StorableList):
    """docstring for BackupList."""

    def __init__(self, dry=False, path='./dcos-migrate/backup'):
        super(BackupList, self).__init__(path)
        self._dry = dry

    def backups(self, pluginName: str):
        newList = BackupList()

        for b in self:
            if b.plugin_name == pluginName:
                newList.append(b)
        return newList

    def backup(self, pluginName: str, backupName: str):
        for b in self.backups(pluginName=pluginName):
            if b.name == backupName:
                return b
        return None

    def match_jsonpath(self, jsonPath):
        bl = BackupList()
        jsonpath_expr = parse(jsonPath)

        for b in self:
            # this is quite stupid but related to the Backup object structure
            # maybe there is a better way to make .data directly part of the list
            res = jsonpath_expr.find([b.data])
            if res and len(res) > 0:
                bl.append(b)

        return bl

    def append_data(self, pluginName: str, backupName: str,
                    extenstion: str, data: str):
        b = Backup(pluginName=pluginName, backupName=backupName,
                   extenstion=extenstion).deserialize(data)

        self.append(b)
