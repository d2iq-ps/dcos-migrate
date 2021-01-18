from dcos_migrate.system import Migrator, Manifest
from kubernetes.client.models import V1beta1CronJob, V1beta1CronJobSpec, V1beta1JobTemplateSpec, V1JobSpec, V1ObjectMeta, V1PodSpec, V1Container, V1ResourceRequirements
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
            "description": self.handleDescription,
            "labels.*": self.handleLabels,
            "run.args":  self.handleRunArgs,
            "run.cpus|gpus|mem|disk": self.handleLimits,
            "run.artifacts": self.handleArtifacts,
            "secrets": self.handleSecrets,
            "env": self.handleEnv,
            "dependencies|run.maxLaunchDelay|run.docker.parameters": self.noEquivalent
        }

    @property
    def job(self):
        return self.manifest[0]

    @job.setter
    def job(self, job):
        if len(self.manifest) > 0:
            self.manifest[0] = job
            return

        self.manifest.append(job)

    # if ".id" == key:
    #     return update(
    #         {
    #             "metadata": {"name": dnsify(val)},
    #             "spec": {"template": {"spec": {"containers": [{"name": dnsify(val)}]}}},
    #         }
    #     )

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
                    template=V1PodSpec(containers=[V1Container(name=name, resources=V1ResourceRequirements(limits={}, requests=None
                                                                                                           ))])
                )
            )
        )
        self.job = job

    def handleDependencies(self, key, value, full_path):
        logging.warning("Not migrating dependencies")

    # if ".description" == key:
    #     if not val:
    #         return result
    #     return update({"metadata": {"annotations": {"description": val}}})

    def handleDescription(self, key, value, full_path):
        j = self.job
        j.metadata.annotations['migration.dcos.d2iq.com/description'] = value
        self.job = j

    # if ".labels" == key:
    #     return update({"metadata": {"labels": val}})

    def handleLabels(self, key, value, full_path):
        j = self.job
        j.metadata.annotations['migration.dcos.d2iq.com/label/{}'.format(
            key)] = value
        self.job = j

    # if re.match(".run.args", key):
    #     return update_container(
    #         {"args": result.get("run", {}).get("args", []).append(val)}
    #     )

    def handleRunArgs(self, key, value, full_path):
        j = self.job

        j.spec.job_template.spec.template.spec.containers[0].args = value

        self.job = j

    # if ".run.cpus" == key:
    #     if val == 0:
    #         return result
    #     return update_container({"resources": {"limits": {"cpu": val}}})
    #
    # if ".run.disk" == key:
    #     if val == 0:
    #         return result
    #     return update_container({"resources": {"limits": {"ephemeral-storage": val}}})
    #
    # if ".run.gpus" == key:
    #     if val == 0:
    #         return result
    #     return update_container(
    #         {
    #             "resources": {
    #                 "requests": {"nvidia.com/gpu": val},
    #                 "limits": {"nvidia.com/gpu": val},
    #             },
    #         }
    #     )
    #
    # if ".run.mem" == key:
    #     if val == 0:
    #         return result
    #     return update_container({"resources": {"limits": {"memory": str(val) + "Mi"}}})

    def handleLimits(self, key, value, full_path):
        j = self.job
        container = j.spec.job_template.spec.template.containers[0]

        if "cpus" == key:
            container.resources.limits.update({"cpu": value})

        if "mem" == key:
            container.resources.limits["memory"] = str(
                value) + "Mi"

        if "disk" == key:
            if value == 0:
                return
            container.resources.limits["ephemeral-storage"] = value

        if "gpus" == key and value != 0:
            if not container.resources:
                container.resources.requests = {}
            container.resources.requests["nvidia.com/gpu"] = value
            container.resources.limits["nvidia.com/gpu"] = value

        j.spec.job_template.spec.template.containers[0] = container

        self.job = j

    def handleArtifacts(self, key, value, full_path):
        pass

    def handleSecrets(self, key, value, full_path):
        pass

    def handleEnv(self, key, value, full_path):
        pass
