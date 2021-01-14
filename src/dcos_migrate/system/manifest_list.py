from .storable_list import StorableList
from .manifest import Manifest
from kubernetes.client.models import V1ObjectMeta


class ManifestList(StorableList):
    """docstring for ManifestList."""

    def __init__(self, dry=False, path='./dcos-migrate/migrate'):
        super(ManifestList, self).__init__(path)
        self._dry = dry

    def find_manifest_by_name(self, name):
        pass

    def clusterMeta(self) -> V1ObjectMeta:
        clustermanifests = self.manifests('cluster')
        # cluster creates a single manifest with a single Configmap
        if clustermanifests and clustermanifests[0] and clustermanifests[0][0]:
            clustercfg = clustermanifests[0][0]
            return clustercfg.metadata

        return None

    def manifests(self, pluginName: str):
        ml = ManifestList()
        for m in self:
            if m.plugin_name == pluginName:
                ml.append(m)

        return ml

    def append_data(self, pluginName: str, backupName: str,
                    extenstion: str, data: str):
        b = Manifest(pluginName=pluginName, backupName=backupName,
                     extenstion=extenstion).deserialize(data)

        self.append(b)
