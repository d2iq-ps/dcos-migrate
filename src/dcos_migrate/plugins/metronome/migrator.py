from dcos_migrate.system import Migrator
from kubernetes.client.models import V1beta1CronJob, V1ObjectMeta


class MetronomeMigrator(Migrator):
    """docstring for SecretsMigrator."""

    def __init__(self,
                 defaultImage="alpine:latest",
                 forceJob=False,
                 secretOverwrites={},
                 **kw):
        super(MetronomeMigrator, self).__init__(**kw)

        self.image = defaultImage
        self.forceJob = forceJob
        self.secretOverwrites = secretOverwrites
        self.translate = {
            ".id": self.initJob,
            ".run.artifacts": self.handleArtifacts,
            ".labels": self.handleLabels,
            ".secrets": self.handleSecrets,
            ".env": self.handleEnv
        }

    @property
    def thisJob(self):

        pass

    def initJob(self, key, value):
        metadata = V1ObjectMeta()
        job = V1beta1CronJob(metadata=metadata)
        pass

    def handleArtifacts(self, key, value):
        pass

    def handleLabels(self, key, value):
        pass

    def handleSecrets(self, key, value):
        pass

    def handleEnv(self, key, value):
        pass
