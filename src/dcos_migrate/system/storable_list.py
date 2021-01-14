import os
import glob
from .backup import Backup
from .manifest import Manifest
import logging
# pre python 3.9


def removeprefix(s: str, pre: str):
    if s.startswith(pre):
        return s[len(pre):]
    return s


class StorableList(list):
    """docstring for StorableList."""

    def __init__(self, path, dry=False):
        super(StorableList, self).__init__()
        self._dry = dry
        self._path = path

    def store(self, pluginName=None, backupName=None) -> object:
        # ./data/backup/<pluginName>/<backupName>.<class>.<extension>
        out = {}
        for b in self:
            pname = b.plugin_name
            bname = b.name
            fextension = ".{cls}.{ext}".format(
                cls=b.__class__.__name__, ext=b.extension)

            path = os.path.join(self._path, pname)
            filepath = os.path.join(path, bname+fextension)

            data = b.serialize()

            logging.debug("writing file {}".format(filepath))
            if not self._dry:
                os.makedirs(path, exist_ok=True)

                with open(filepath, 'wt', encoding='utf-8') as f:
                    f.write(data)
                    f.close()

            out[filepath] = data

        return out

    def append_data(self, pluginName: str, backupName: str, extension: str,
                    className: str, data: str, **kwargs):
        # list classes should implement this. Now we do a static guess
        cls = None
        if className == "Backup":
            cls = Backup
        if className == "Manifest":
            cls = Manifest

        if not cls:
            raise ValueError("Unknown class: {}".format(className))

        d = cls(pluginName=pluginName, backupName=backupName,
                extension=extension, **kwargs)
        d.deserialize(data)
        self.append(d)

    def load(self):
        # ./data/backup/<pluginName>/<backupName>.<class>.<extension>
        globstr = "{path}/*/*".format(path=self._path)
        for f in glob.glob(globstr):
            fname = removeprefix(removeprefix(f, self._path), '')
            # <pluginName>/<backupName>
            pluginFile = list(filter(None, fname.split('/')))
            if not len(pluginFile) == 2:
                raise ValueError(
                    "Unexpected file/path: {} in {}".format(f, pluginFile))

            pluginName = pluginFile[0]
            fileName = pluginFile[1].split('.')
            if not len(fileName) == 3:
                raise ValueError(
                    "Unexpected file name: {} in {}".format(f, fileName))

            name = fileName[0]
            className = fileName[1]
            extension = fileName[2]

            data = ""
            with open(f, 'rt') as file:
                data = file.read()
                file.close()

            if not data:
                continue

            # let classes implement the load method
            self.append_data(pluginName=pluginName,
                             backupName=name, extension=extension, data=data, className=className)

        return self
