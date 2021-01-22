from dcos_migrate.system import Migrator, Manifest
from kubernetes.client.models import V1Deployment, V1ObjectMeta, V1Secret
from kubernetes.client import ApiClient
from random import randrange
from .app_translator import ContainerDefaults, translate_app, Settings, clean_secret_key
import logging


class MarathonMigrator(Migrator):
    """docstring for MarathonMigrator."""

    def __init__(self, **kw):
        super(MarathonMigrator, self).__init__(**kw)
        self.translate = {
            "secrets.*": self.create_secret,
            "id": self.translate_marathon,
        }

        self.secret = None
        self.manifest = None

    def translate_marathon(self, key, value, full_path):
        secretName = ""
        if self.secret is not None:
            secretName = self.secret.metadata.name

        settings = Settings(
            container_defaults=ContainerDefaults("alpine:latest", "/"),
            imported_k8s_secret_name=secretName
        )

        self.manifest = Manifest(
            pluginName="marathon", manifestName=self.dnsify(value))
        app, warning = translate_app(self.object, settings)

        kc = ApiClient()
        dapp = kc._ApiClient__deserialize(app, V1Deployment)
        self.manifest.append(dapp)
        if self.secret is not None:
            self.manifest.append(self.secret)

    def create_secret(self, key, value, full_path):
        if self.secret is None:
            metadata = V1ObjectMeta(annotations={})

            clusterMeta = self.manifest_list.clusterMeta()
            if clusterMeta:
                metadata.annotations = clusterMeta.annotations
            appid = self.dnsify(self.object['id'])
            metadata.annotations["migration.dcos.d2iq.com/marathon-appid"] = self.object['id']
            metadata.name = "marathonsecret-{}".format(appid)
            self.secret = V1Secret(metadata=metadata, data={})
            self.secret.api_version = 'v1'
            self.secret.kind = 'Secret'

        sec = clean_secret_key(value['source'])

        sourceSecret = self.manifest_list.manifest(
            pluginName='secret', manifestName=sec)

        if sourceSecret:
            for v in sourceSecret[0].data.values():
                self.secret.data[sec] = v
        else:
            logging.warning("Source secret '{}' not found".format(
                sec))
