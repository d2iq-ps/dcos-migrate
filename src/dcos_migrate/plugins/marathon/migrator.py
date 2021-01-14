from dcos_migrate.system import Migrator, Manifest
from kubernetes.client.models import V1Deployment, V1ObjectMeta, V1Secret
from random import randrange


class MarathonMigrator(Migrator):
    """docstring for MarathonMigrator."""

    def __init__(self, **kw):
        super(MarathonMigrator, self).__init__(**kw)
        self.translate = {
            "id": self.translate_id,
            "container.docker.portMappings[*]": self.container_portmappings,
            # "label.COM_EXAMPLE_FOO": self.my_special_func
        }
        self.appid = ""
        self.appid_annotation = "migrate.dcos.io/marathon/appid"
        self.manifest = Manifest(pluginName="marathon")

    def get_deployment(self):
        return self.manifest.find_by_annotation(annotation=self.appid_annotation,
                                                value=self.appid)

    @staticmethod
    def parse_id(id):
        id = id.replace('_', '-')
        return '.'.join(reversed(list(filter(None, id.split('/')))))

    def container_portmappings(self, key, value={}):
        p = 0
        if "port" in value and int(value["port"]) == 0:
            p = randrange(1024, 65535)

        self.get_deployment()

    def translate_id(self, key, value):
        # create Deployment
        metadata = V1ObjectMeta(name=MarathonMigrator.parse_id(value))
        metadata.annotations = {
            self.appid_annotation: value
        }
        self.appid = value
        m = V1Deployment(metadata=metadata)

        self.manifest.name=value
        self.manifest.append(m)
        self.deployment_name = value

    def det_deployment(self):
        self.manifest.find_resource_by_name(self.deployment_name)
