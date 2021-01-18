from dcos_migrate.system import Migrator, Manifest
from kubernetes.client.models import V1Deployment, V1ObjectMeta, V1Secret
from random import randrange
from .app_translator import ContainerDefaults, translate_app, Settings


class MarathonMigrator(Migrator):
    """docstring for MarathonMigrator."""

    def __init__(self, **kw):
        super(MarathonMigrator, self).__init__(**kw)
        self.translate = {
            "id": self.translate_marathon,
        }
        self.appid = ""
        self.appid_annotation = "migrate.dcos.io/marathon/appid"
        self.manifest = None

    def translate_marathon(self, key, value, full_path):
        settings = Settings(
            container_defaults=ContainerDefaults("alpine:latest", "/"),
            imported_k8s_secret_name=""
        )

        self.manifest = Manifest(
            pluginName="marathon", manifestName=self.dnsify(value))
        app, warning = translate_app(self.object, settings)

        self.manifest.append(app)
