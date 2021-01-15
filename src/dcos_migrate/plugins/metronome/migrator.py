from dcos_migrate.system import Migrator, Manifest
from kubernetes.client.models import V1beta1CronJob, V1beta1CronJobSpec, V1beta1JobTemplateSpec, V1JobSpec, V1ObjectMeta, V1PodSpec, V1Container
import logging


class MetronomeMigrator(Migrator):
    """docstring for SecretsMigrator."""

    def __init__(self,
                 defaultImage="alpine:latest",
                 forceJob=False,
                 secretOverwrites={},
                 **kw):
        super(MetronomeMigrator, self).__init__(**kw)

        self.manifest = None

        self.apiVersion = "batch/v1beta1"
        self.kind = "CronJob"

        self.image = defaultImage
        self.forceJob = forceJob
        self.secretOverwrites = secretOverwrites
        self.translate = {
            "id": self.initJob,
            "dependencies": self.handleDependencies,
            "description": self.handleDescription,
            "labels.*": self.handleLabels,
            "run.artifacts": self.handleArtifacts,
            "secrets": self.handleSecrets,
            "env": self.handleEnv,
            "run.maxLaunchDelay|run.docker.parameters": self.noEquivalent
        }

    @property
    def job(self):
        return self.manifest[0]

    @job.setter
    def job(self, job):
        if len(self.manifest) > 0:
            self.manifest[0] = job

        self.manifest.append(job)

    def initJob(self, key, value, full_path):
        name = self.dnsify(value)
        self.manifest = Manifest(
            data=[None], pluginName='metronome', manifestName=name)
        metadata = V1ObjectMeta(name=name)
        clusterMeta = self.manifest_list.clusterMeta()
        if clusterMeta:
            metadata.annotations = clusterMeta.annotations
        job = V1beta1CronJob(metadata=metadata)
        job.kind = self.kind
        job.apiVersion = self.apiVersion
        job.spec = V1beta1CronJobSpec(
            schedule="* * * * *",
            suspend=True,
            job_template=V1beta1JobTemplateSpec(
                spec=V1JobSpec(
                    template=V1PodSpec(containers=[V1Container(name=name)])
                )
            )
        )
        self.job = job

    def handleDependencies(self, key, value, full_path):
        logging.warning("Not migrating dependencies")

    def handleDescription(self, key, value, full_path):
        j = self.job
        j.metadata.annotations['migration.dcos.d2iq.com/description'] = value
        self.job = j

    def handleLabels(self, key, value, full_path):
        j = self.job
        j.metadata.annotations['migration.dcos.d2iq.com/label/{}'.format(
            key)] = value
        self.job = j

    def handleArtifacts(self, key, value, full_path):
        pass

    def handleSecrets(self, key, value, full_path):
        pass

    def handleEnv(self, key, value, full_path):
        pass
