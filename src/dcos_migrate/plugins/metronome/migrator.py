from dcos_migrate.system import Migrator, Manifest
import kubernetes.client.models as K  # type: ignore
import logging
import re


# FIXME: reuse version from secrets migration. BEWARE: added lstrip(".")!
_invalid_secret_key = re.compile("[^-._a-zA-Z0-9]")


def clean_key(s: str) -> str:
    # Replace DC/OS folders with dots
    s = s.replace("/", ".")
    # Replace other invalid characters with `_`
    # `folder/sec!ret` becomes `folder.sec_ret`
    return _invalid_secret_key.sub("_", s).lstrip(".")


class MetronomeMigrator(Migrator):
    """docstring for SecretsMigrator."""

    def __init__(
        self, defaultImage="alpine:latest", forceJob=False, secretOverwrites={}, **kw
    ):
        super(MetronomeMigrator, self).__init__(**kw)

        self.manifest = None

        self.image = defaultImage
        self.forceJob = forceJob
        self.secretOverwrites = secretOverwrites
        self._warnings = dict()
        self.translate = {
            "id": self.initCronJob,
            "dependencies|run.docker.parameters": self.noEquivalent,
            "description": self.handleDescription,
            "labels.*": self.handleLabels,
            "run.args": self.handleRunArgs,
            "run.artifacts": self.handleArtifacts,
            "run.cmd": self.handleCmd,
            "run.cpus": self.handleLimitsCPUs,
            "run.disk": self.handleLimitsDisk,
            "run.docker.forcePullImage": self.handleForcePull,
            "run.docker.image": self.handleImage,
            "run.docker.privileged": self.handlePrivileged,
            "run.env": self.handleEnv,
            "run.gpus": self.handleLimitsGPUs,
            "run.maxLaunchDelay": self.handleMaxLaunchDelay,
            "run.mem": self.handleLimitsMem,
            "run.networks": self.handleNetworks,
            "run.placement.constraints": self.handlePlacementConstraints,
            "run.restart.activeDeadlineSeconds": self.handleActiveDeadlineSeconds,
            "run.restart.policy": self.handleRestartPolicy,
            # run.secrets does not need to be handled explicitly. run.env will use its data.
            "run.taskKillGracePeriodSeconds": self.handleTaskKillGracePeriod,
            "run.ucr": self.handleUCR,
            "run.user": self.handleUser,
            "run.volumes": self.handleVolumes,
            "schedules[0]": self.handleSchedule,
        }

    @property
    def cronJob(self):
        return self.manifest[0]

    @property
    def job(self):
        return self.cronJob.spec.job_template

    @property
    def container(self):
        return self.job.spec.template.containers[0]

    def warn(self, path, msg):
        self._warnings[path] = msg

    def initCronJob(self, key, value, full_path):
        name = self.dnsify(value)
        self.manifest = Manifest(data=[None], pluginName="metronome", manifestName=name)
        metadata = K.V1ObjectMeta(name=name)
        clusterMeta = self.manifest_list.clusterMeta()
        if clusterMeta:
            metadata.annotations = clusterMeta.annotations
        self.manifest = [K.V1beta1CronJob(metadata=metadata)]
        # self.cronJob.kind = "CronJob"
        # self.cronJob.apiVersion = "batch/v1beta1"

        resources = K.V1ResourceRequirements(limits={}, requests={})
        container1 = K.V1Container(name=name, resources=resources)
        podSpec = K.V1PodSpec(containers=[container1])
        jobTmpl = K.V1beta1JobTemplateSpec(spec=K.V1JobSpec(template=podSpec))
        self.cronJob.spec = K.V1beta1CronJobSpec(
            schedule="* * * * *", suspend=True, job_template=jobTmpl,
        )

    def handleActiveDeadlineSeconds(self, key, value, full_path):
        self.warn(
            full_path,
            f'DKP has no equivalent for "run.restart.activeDeadlineSeconds", dropping: {value}',
        )

    def handleArtifacts(self, key, value, full_path):
        pass

    def handleCmd(self, key, value, full_path):
        if value and value != "":
            self.container.command = ["/bin/sh", "-c", value]

    def handleDescription(self, key, value, full_path):
        self.cronJob.metadata.annotations["migration.dcos.d2iq.com/description"] = value

    def handleEnv(self, key, value, full_path):
        env = []
        for k, v in value:
            if "secret" in v:
                keyRef = clean_key(self.object.get("secrets").get(k).get("source"))
                # TODO: find ref from secrets metadata
                key_selector = K.V1SecretKeySelector(key=keyRef, name="TODO_ref")
                env_var_src = K.V1EnvVarSource(secret_key_ref=key_selector)
                env.append(K.V1EnvVar(name=k, value_from=env_var_src))
            else:
                env.append(K.V1EnvVar(name=k, value=v))

        self.container.env = env

    def handleForcePull(self, key, value, full_path):
        self.container.imagePullPolicy = "Always" if value else "IfNotPresent"

    def handleImage(self, key, value, full_path):
        self.container.image = value

    def handleLabels(self, key, value, full_path):
        k = f"migration.dcos.d2iq.com/label/{key}"
        self.cronJob.metadata.annotations[k] = value

    def handleLimitsCPUs(self, key, value, full_path):
        self.container.resources.limits.update({"cpu": value})

    def handleLimitsDisk(self, key, value, full_path):
        if value == 0:
            return
        self.container.resources.limits["ephemeral-storage"] = value

    def handleLimitsGPUs(self, key, value, full_path):
        self.container.resources.requests["nvidia.com/gpu"] = value
        self.container.resources.limits["nvidia.com/gpu"] = value

    def handleLimitsMem(self, key, value, full_path):
        self.container.resources.limits["memory"] = str(value) + "Mi"

    def handleMaxLaunchDelay(self, key, value, full_path):
        if not value == 3600:
            self.warn(full_path, "maxLaunchDelay is not available in DKP")

    def handleNetworks(self, key, value, full_path):
        if value != []:
            self.warn(full_path, "conversion of .run.networks is not yet implemented.")

    def handlePlacementConstraints(self, key, value, full_path):
        if value != []:
            self.warn(
                full_path, "conversion of .run.placement.constraints not implemented.",
            )

    def handlePrivileged(self, key, value, full_path):
        self.container.securityContext = K.V1PodSecurityContext(dict(privileged=value))

    def handleRestartPolicy(self, key, value, full_path):
        if value.title() == "Never":
            self.job.spec.restartPolicy = value.title()
        else:
            self.warn(
                full_path,
                f"restartPolicy '{value}' was dropped. Now the default of 'spec.backoffLimit' will implicitly try 6 times.",
            )

    def handleRunArgs(self, key, value, full_path):
        self.job.spec.template.spec.containers[0].args = value

    def handleSchedule(self, key, value, full_path):
        if "concurrencyPolicy" in value:
            self.cronJob.spec.concurrencyPolicy = value["concurrencyPolicy"].title()
        if "cron" in value:
            self.cronJob.spec.schedule = value["cron"]
        if "enabled" in value:
            self.cronJob.spec.suspend = not value["enabled"]
        if "startingDeadlineSeconds" in value:
            self.cronJob.spec.startingDeadlineSeconds = value["startingDeadlineSeconds"]
        if "timeZone" in value:
            v = value["timeZone"]
            if not ("UTC" == v):
                self.warn(
                    full_path,
                    f'You might need to edit the cron expression (spec.schedule) to account for an update from "{value}" to your target cluster\'s timezone.',
                )

    def handleTaskKillGracePeriod(self, key, value, full_path):
        self.job.spec.terminationGracePeriodSeconds = value

    def handleUCR(self, key, value, full_path):
        self.warn(
            full_path,
            f'Migrating "{full_path}" is not (yet) supported. You might want to manually convert and add your UCR configuration to the resulting yaml.',
        )
        # if not "docker" == model.pop(".run.ucr.image.kind", None):
        #     return
        # warn("Converting UCR configuration as .kind is 'docker'. Please check whether UCR is required for your use case.")
        # if ".run.ucr.image.forcePull" in model:
        #     model[".run.docker.forcePullImage"] = model.pop(".run.ucr.image.forcePull")
        # if ".run.ucr.image.id" in model:
        #     model[".run.docker.image"] = model.pop(".run.ucr.image.id")
        # if ".run.ucr.privileged" in model:
        #     model[".run.docker.privileged"] = model.pop(".run.ucr.privileged")

    def handleUser(self, key, value, full_path):
        self.warn(
            full_path,
            f'Found "run.user": "{value}". You might need to set "spec.template.spec.containers[].securityContext.runAsUser" manually, as we can\'t infer a mapping to the according uid on the target node.',
        )
        pass

    def handleVolumes(self, key, value, full_path):
        self.warn(full_path, "TODO: conversion of .run.volumes is not yet implemented.")
