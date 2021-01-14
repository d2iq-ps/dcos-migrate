from dcos_migrate.system import Migrator
from kubernetes.client.models import V1Secret, V1ObjectMeta
from base64 import b64encode


class SecretMigrator(Migrator):
    """docstring for SecretsMigrator."""

    def __init__(self, **kw):
        super(SecretsMigrator, self).__init__(**kw)
        self.translate = {
            "key": self.translate_secret,
        }

    @staticmethod
    def parse_id(id):
        id = id.replace('_', '-')
        return '.'.join(reversed(list(filter(None, id.split('/')))))

    def translate_secret(self, key, value):
        fullPath = "/".join(filter(None,
                                   [self.object["path"], self.object["key"]]))
        metadata = V1ObjectMeta(name=SecretsMigrator.parse_id(value))
        metadata.annotations =
        metadata.annotations["migration.dcos.d2iq.com/secrets/secretpath"] = fullPath

        sec = V1Secret(metadata=metadata)
        sec.data[self.object["key"]] = b64encode(
            self.object['value'].encode('ascii'))
        self.manifest.append(sec)
