from dcos_migrate.plugins.plugin import MigratePlugin
from dcos_migrate.plugins.cluster import ClusterPlugin
from dcos_migrate.system import DCOSClient, BackupList, Backup, Manifest, ManifestList

from kubernetes.client.models import V1Secret, V1ObjectMeta

import urllib
import base64
import logging
from base64 import b64encode


class DCOSSecretsService:

    def __init__(self, client: DCOSClient):
        self.client = client
        self.url = "{}/{}".format(self.client.dcos_url, 'secrets/v1')
        self.store = 'default'

    def list(self, path: str = ''):
        u = '{url}/secret/{store}/{path}?list=true'.format(
            url=self.url,
            store=urllib.parse.quote(self.store),
            path=urllib.parse.quote(path)
        )
        r = self.client.get(u)
        r.raise_for_status()
        return r.json()['array']

    def get(self, path: str, key: str):
        # There are two types of secrets: text and binary.  Using `Accept: */*`
        # the returned `Content-Type` will be `application/octet-stream` for
        # binary secrets and `application/json` for text secrets.
        #
        # Returns the secret as:
        # {
        #   "path": "...",
        #   "key": "...",
        #   "type": "{text|binary}",
        #   "value": "base64(value)"
        # }
        full_path = (path + '/' + key).strip('/')
        url = self.url + '/secret/{store}/{path}'.format(
            store=urllib.parse.quote(self.store), path=urllib.parse.quote(full_path)
        )
        r = self.client.get(url)
        r.raise_for_status()
        content_type = r.headers['Content-Type']
        if content_type == 'application/octet-stream':
            response = {
                'type': 'binary',
                'value': base64.b64encode(r.content).decode('ascii')
            }
        else:
            assert content_type == 'application/json', content_type
            response = r.json()
            response['type'] = 'text'
            # Always encode the secret as base64, even when it is safe UTF-8 text.
            # This obscures the values to prevent unintentional exposure.
            response['value'] = base64.b64encode(
                response['value'].encode('utf-8')).decode('ascii')
        # Always add the `path` and `key` values to the JSON response. Ensure the key always has a
        # value by taking the last component of the path if necessary.
        if not key:
            parts = path.rsplit('/', 1)
            key = parts.pop()
            parts.append('')
            path = parts[0]
        response['path'] = path
        response['key'] = key
        return response


class SecretPlugin(MigratePlugin):
    """docstring for SecretPlugin."""

    plugin_name = "secret"
    depends_migrate = [ClusterPlugin.plugin_name]

    def __init__(self):
        super(SecretPlugin, self).__init__()

    def backup(self, client: DCOSClient, **kwargs) -> BackupList:
        backupList = BackupList()
        sec = DCOSSecretsService(client)
        path = ""
        keys = sec.list(path)
        if keys:
            for key in keys:
                secData = sec.get(path, key)

                backupList.append(
                    Backup(self.plugin_name, Backup.renderBackupName(path+key), data=secData))

        return backupList

    def migrate(self, backupList: BackupList, manifestList: ManifestList, **kwargs) -> ManifestList:
        ml = ManifestList()

        metadata = V1ObjectMeta()

        clusterManifests = manifestList.manifests(pluginName='cluster')
        if clusterManifests:
            # we expect a single manifest
            if clusterManifests[0][0]:
                # set default annotations from cluster
                metadata.annotations = clusterManifests[0][0].metadata.annotations

        for ba in backupList.backups(pluginName='secret'):
            logging.debug("Found backup {}".format(ba))
            b = ba.data
            fullPath = "/".join(filter(None, [b["path"], b["key"]]))
            name = Manifest.renderManifestName(b["key"])

            metadata.annotations["migration.dcos.d2iq.com/secrets/secretpath"] = fullPath
            metadata.name = name
            sec = V1Secret(metadata=metadata)
            sec.api_version = 'v1'
            sec.kind = 'Secret'
            sec.data = {}
            sec.data[name] = b64encode(
                    b['value'].encode('ascii')).decode('ascii')

            manifest = Manifest(pluginName=self.plugin_name,
                                manifestName=Manifest.renderManifestName(fullPath))
            manifest.append(sec)

            ml.append(manifest)

        return ml
