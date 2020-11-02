import xml.etree.ElementTree as ET
import logging
import xml.dom.minidom

from string import Template
from xml.sax.saxutils import escape


log = logging.getLogger("translator")

# Defaults with provided values.yaml
# Update according to output of "helm2 list jenkins --output json" if needed
JENKINS_FULL_NAME = "jenkins"
JENKINS_NAMESPACE = "jenkins"
JENKINS_URI_PREFIX = "/jenkins"
JENKINS_URL = "http://{}.{}.svc:8080{}".format(JENKINS_FULL_NAME, JENKINS_NAMESPACE, JENKINS_URI_PREFIX)
JENKINS_TUNNEL = "jenkins-agent.{}:50000".format(JENKINS_NAMESPACE)

JENKINS_AGENT_ENTRYPOINT = '/bin/sh -c "wget {}/jnlpJars/agent.jar && mkdir -p /usr/share/jenkins && mv agent.jar /usr/share/jenkins && cp /var/configmaps/jenkins-agent /usr/local/bin/jenkins-agent && chmod +x /usr/local/bin/jenkins-agent && jenkins-agent"'.format(JENKINS_URL)

# Kubernetes Cloud templates - EDIT ONLY IF YOU KNOW WHAT YOU ARE DOING!
KUBERNETES_CLOUD_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.KubernetesCloud plugin="kubernetes@1.27.1.1">
    <name>$NAME</name>
    <defaultsProviderTemplate></defaultsProviderTemplate>
    <templates>
        $POD_TEMPLATES
    </templates>
    <serverUrl></serverUrl>
    <skipTlsVerify>false</skipTlsVerify>
    <addMasterProxyEnvVars>false</addMasterProxyEnvVars>
    <capOnlyOnAlivePods>false</capOnlyOnAlivePods>
    <webSocket>false</webSocket>
    <directConnection>false</directConnection>
    <jenkinsUrl>$JENKINS_URL</jenkinsUrl>
    <jenkinsTunnel>$JENKINS_TUNNEL</jenkinsTunnel>
    <containerCap>10</containerCap>
    <retentionTimeout>5</retentionTimeout>
    <connectTimeout>5</connectTimeout>
    <readTimeout>15</readTimeout>
    <podLabels/>
    <usageRestricted>false</usageRestricted>
    <maxRequestsPerHost>32</maxRequestsPerHost>
    <waitForPodSec>600</waitForPodSec>
    <podRetention class="org.csanchez.jenkins.plugins.kubernetes.pod.retention.Never"/>
</org.csanchez.jenkins.plugins.kubernetes.KubernetesCloud>
"""

KUBERNETES_POD_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.PodTemplate>
    <inheritFrom></inheritFrom>
    <name>$label</name>
    <namespace></namespace>
    <privileged>false</privileged>
    <capOnlyOnAlivePods>false</capOnlyOnAlivePods>
    <alwaysPullImage>false</alwaysPullImage>
    <instanceCap>$INSTANCE_CAP</instanceCap>
    <slaveConnectTimeout>100</slaveConnectTimeout>
    <idleMinutes>0</idleMinutes>
    <activeDeadlineSeconds>0</activeDeadlineSeconds>
    <label>$label</label>
    <nodeSelector></nodeSelector>
    <nodeUsageMode>$nodeUsageMode</nodeUsageMode>
    <hostNetwork>false</hostNetwork>
    <workspaceVolume class="org.csanchez.jenkins.plugins.kubernetes.volumes.workspace.EmptyDirWorkspaceVolume">
        <memory>false</memory>
    </workspaceVolume>
    <volumes>$VOLUMES</volumes>
    <containers>$CONTAINERS</containers>
    <envVars/>
    <annotations/>
    <imagePullSecrets/>
    <nodeProperties/>
    <yamlMergeStrategy class="org.csanchez.jenkins.plugins.kubernetes.pod.yaml.Overrides"/>
    <showRawYaml>true</showRawYaml>
    <podRetention class="org.csanchez.jenkins.plugins.kubernetes.pod.retention.Default"/>
</org.csanchez.jenkins.plugins.kubernetes.PodTemplate>
"""

KUBERNETES_CONTAINER_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.ContainerTemplate>
    <name>$CONTAINER_NAME</name>
    <image>$image</image>
    <privileged>false</privileged>
    <alwaysPullImage>$alwaysPullImage</alwaysPullImage>
    <workingDir></workingDir>
    <command>$command</command>
    <args></args>
    <ttyEnabled>false</ttyEnabled>
    <resourceRequestCpu></resourceRequestCpu>
    <resourceRequestMemory></resourceRequestMemory>
    <resourceLimitCpu></resourceLimitCpu>
    <resourceLimitMemory></resourceLimitMemory>
    <envVars/>
    <ports/>
    <livenessProbe>
        <execArgs></execArgs>
        <timeoutSeconds>0</timeoutSeconds>
        <initialDelaySeconds>0</initialDelaySeconds>
        <failureThreshold>0</failureThreshold>
        <periodSeconds>0</periodSeconds>
        <successThreshold>0</successThreshold>
    </livenessProbe>
</org.csanchez.jenkins.plugins.kubernetes.ContainerTemplate>
"""

CONFIGMAP_VOLUME_MOUNT_TEMPLATE = """
<org.csanchez.jenkins.plugins.kubernetes.volumes.ConfigMapVolume>
    <mountPath>$mountPath</mountPath>
    <configMapName>$configMapName</configMapName>
</org.csanchez.jenkins.plugins.kubernetes.volumes.ConfigMapVolume>
"""


def plugin20Transform(cloud):
    # MesosAgentSpecTemplate in Mesos to PodTemplate in K8
    MESOS_20_TO_KUBERNETES_POD = {
        "label": "label",
        "mode": "nodeUsageMode",
        "idleTerminationMinutes": "idleMinutes",
        "maxExecutors": "containerCap",
    }

    # ContainerInfo in Mesos to ContainerTemplate in K8
    MESOS_20_TO_KUBERNETES_CONTAINER = {
        "dockerImage": "image",
        "dockerForcePullImage": "alwaysPullImage",
    }
    NAME = cloud.find("name").text

    if NAME is None or len(NAME) == 0:
        log.warning("Unnamed cloud found, skipping..")
        return

    INSTANCE_CAP = cloud.find("instanceCap").text

    # Iterate over mesosAgentSpecTemplates
    mesosAgentSpecTemplatesStr = "mesosAgentSpecTemplates"
    specs = cloud.find(mesosAgentSpecTemplatesStr)
    if len(specs) == 0:
        log.warning(f"no {mesosAgentSpecTemplatesStr} found for cloud {NAME}")
        return

    podTemplates = []
    for spec in specs:
        # INSTANCE_CAP is the only field that is configured at Mesos Cloud level but is at K8 Pod Level.
        podTemplateSubs = {"INSTANCE_CAP": INSTANCE_CAP}
        for mesosFieldName, k8FieldName in MESOS_20_TO_KUBERNETES_POD.items():
            field = spec.find(mesosFieldName).text
            k8FieldValue = ""
            if field is not None:
                k8FieldValue = field.text
            if len(k8FieldValue) == 0:
                log.warning(f"Unable to substitute {k8FieldName} in cloud named {NAME}")
                return
            podTemplateSubs[k8FieldName] = k8FieldValue

        # There is a single containerInfo per Agent spec. Can there be more than 1 ? TODO
        containerInfo = spec.find("containerInfo")
        containerTemplateSubs = {}
        if len(containerInfo) == 0:
            log.info("no containerInfo found, skipping...")
        else:
            for mesosFieldName, k8FieldName in MESOS_20_TO_KUBERNETES_CONTAINER.items():
                field = spec.find(f"./containerInfo/{mesosFieldName}")
                k8FieldValue = ""
                if field is not None:
                    k8FieldValue = field.text
                if len(k8FieldValue) == 0:
                    log.warning(f"Unable to substitute {k8FieldName} in cloud named {NAME}")
                    continue
                containerTemplateSubs[k8FieldName] = k8FieldValue
            # Pod name and namespace can be left empty but container name needs to be set to non empty string.
            # K8 plug in injects another container named "jnlp"
            containerTemplateSubs["CONTAINER_NAME"] = "jnlp"

        podTemplateSubs["CONTAINERS"] = Template(KUBERNETES_CONTAINER_TEMPLATE).substitute(containerTemplateSubs)
        podTemplates.append(Template(KUBERNETES_POD_TEMPLATE).substitute(podTemplateSubs))

    CLOUD_CONFIG = Template(KUBERNETES_CLOUD_TEMPLATE).substitute(
        JENKINS_URL=JENKINS_URL,
        JENKINS_TUNNEL=JENKINS_TUNNEL,
        NAME=NAME,
        POD_TEMPLATES='\n'.join(podTemplates)
    )
    return CLOUD_CONFIG


def plugin100Transform(cloud) -> str:
    # slaveInfos in Mesos to PodTemplate in K8
    MESOS_100_TO_KUBERNETES_POD = {
        "labelString": "label",
        "mode": "nodeUsageMode",
        "idleTerminationMinutes": "idleMinutes",
        "maxExecutors": "containerCap",
    }

    # ContainerInfo in Mesos to ContainerTemplate in K8
    MESOS_100_TO_KUBERNETES_CONTAINER = {
        "dockerImage": "image",
        "dockerForcePullImage": "alwaysPullImage",
    }

    NAME = cloud.find("name").text

    if NAME is None or len(NAME) == 0:
        log.warning("Unnamed cloud found, skipping..")
        return

    # Iterate over slaveInfos
    slaveInfosStr = "slaveInfos"
    slaveInfos = cloud.find(slaveInfosStr)
    if len(slaveInfos) == 0:
        log.warning(f"no {slaveInfosStr} found for cloud {NAME}")
        return

    podTemplates = []
    for index in range(len(slaveInfos)):
        slaveInfo = slaveInfos[index]
        # There MUST be a single containerInfo per Agent spec.
        containerInfo = slaveInfo.find("containerInfo")
        containerTemplateSubs = {}
        if containerInfo is None:
            log.info(f'"containerInfo" not found in "{NAME}" cloud at slaveInfo index {index} (probably the default node?). skipping..')
            continue

        podTemplateSubs = {}
        for mesosFieldName, k8FieldName in MESOS_100_TO_KUBERNETES_POD.items():
            field = slaveInfo.find(mesosFieldName)
            k8FieldValue = ""
            if field is not None:
                k8FieldValue = field.text
            if len(k8FieldValue) == 0:
                log.warning(f'Key "{mesosFieldName}" not found in "{NAME}" cloud at slaveInfo index {index}. Defaulting to empty string.')
                k8FieldValue = ""
            podTemplateSubs[k8FieldName] = k8FieldValue

        else:
            for mesosFieldName, k8FieldName in MESOS_100_TO_KUBERNETES_CONTAINER.items():
                field = slaveInfo.find(f"./containerInfo/{mesosFieldName}")
                k8FieldValue = ""
                if field is not None:
                    k8FieldValue = field.text
                if len(k8FieldValue) == 0:
                    log.warning(f"Unable to substitute {k8FieldName} in cloud named {NAME}")
                    continue
                containerTemplateSubs[k8FieldName] = k8FieldValue
            # Override the jnlp container that would usually be injected by kubernetes plug in
            containerTemplateSubs["CONTAINER_NAME"] = "jnlp"
            containerTemplateSubs["command"] = escape(JENKINS_AGENT_ENTRYPOINT)

        podTemplateSubs["CONTAINERS"] = Template(KUBERNETES_CONTAINER_TEMPLATE).substitute(containerTemplateSubs)
        podTemplateSubs["INSTANCE_CAP"] = 10  # TODO
        podTemplateSubs["VOLUMES"] = Template(CONFIGMAP_VOLUME_MOUNT_TEMPLATE).substitute(mountPath="/var/configmaps",
                                                                                          configMapName="jenkins-agent-3-35-5")
        podTemplates.append(Template(KUBERNETES_POD_TEMPLATE).substitute(podTemplateSubs))

    CLOUD_CONFIG = Template(KUBERNETES_CLOUD_TEMPLATE).substitute(
        JENKINS_URL=JENKINS_URL,
        JENKINS_TUNNEL=JENKINS_TUNNEL,
        NAME=NAME,
        POD_TEMPLATES='\n'.join(podTemplates),
    )
    return CLOUD_CONFIG


def translate_mesos_to_k8_config_xml(src_file: str, target_file: str):
    log.info(f'using "{src_file}" file to migrate to kubernetes configuration at "{target_file}"')
    # Currently supported plugin versions
    SUPPORTED_VERSIONS = {
        "mesos@2.0": plugin20Transform,
        "mesos@1.0.0": plugin100Transform,
    }

    root = ET.parse(src_file).getroot()

    clouds = root.find("./clouds")

    mesos_cloud_tag = 'org.jenkinsci.plugins.mesos.MesosCloud'
    modified = False
    num_of_clouds = len(clouds)
    for i in range(num_of_clouds):
        cloud = clouds[i]
        if cloud.tag != mesos_cloud_tag:
            log.info('cloud %s is not supported yet' % cloud.tag)
            continue

        ver = cloud.get("plugin")
        if ver not in SUPPORTED_VERSIONS:
            log.info('cloud %s with version %s is not supported yet' % (cloud.tag, ver))
            continue

        new_cloud_str = SUPPORTED_VERSIONS[ver](cloud)
        if new_cloud_str is None:
            log.info('failed to transform cloud %s with version %s' % (cloud.tag, ver))
            continue

        modified = True
        clouds[i] = ET.fromstring(new_cloud_str)
        log.info(f'Completed translation of "{mesos_cloud_tag}" @ "{ver}" in the config file to the Kubernetes Cloud configuration')

    if not modified:
        # Write to a file.
        log.info("no clouds were transformed")
        return

    ET.ElementTree(root).write(open(target_file, 'wb'), encoding='utf-8', xml_declaration=True)
    pretty_xml = xml.dom.minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    return pretty_xml
