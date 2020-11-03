import logging
import json
import os
import subprocess
from collections import namedtuple

# DCOS CLI
DCOS = os.getenv("DCOS_CLI", "dcos")
MARATHON_JSON = "marathon.json"

# Edit/Update as needed
Mapping = namedtuple("Mapping", ["DCOS_VERSION", "JENKINS_VERSION", "KUBERNETES_PLUGIN_VERSION", "CHART_VERSION"])
versions = [Mapping("3.6.1-2.190.1", "2.190.1", "1.24.1", "2.6.4")]

# Constants
encoding = "utf-8"
log = logging.getLogger("parser")
logging.basicConfig(level=logging.INFO)


def run_cmd(cmd: str, print_output: bool = False, check: bool = True, timeout_seconds: int = 300) -> [int, str, str]:
    log.info('running command "{}"'.format(cmd, check))
    result = subprocess.run(
        [cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        check=check,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        log.info("Got exit code {} to command: {}".format(result.returncode, cmd))

    if result.stdout:
        stdout = result.stdout.decode(encoding).strip()
    else:
        stdout = ""

    if result.stderr:
        stderr = result.stderr.decode(encoding).strip()
    else:
        stderr = ""

    if print_output:
        if stdout:
            log.info("STDOUT:\n{}".format(stdout))
        if stderr:
            log.info("STDERR:\n{}".format(stderr))

    return result.returncode, stdout, stderr


def download_dcos_package(app_id: str, target_dir: str) -> [str, str]:
    log.info("Validating DC/OS CLI is setup correctly")
    run_cmd("{} --version".format(DCOS), check=True)

    _, out, err = run_cmd("{} marathon app show {}".format(DCOS, app_id))
    if len(out) == 0:
        log.error("Empty output detected")
        return

    app = json.loads(out, encoding=encoding)
    f = open(os.path.join(target_dir, MARATHON_JSON), "w")
    f.write(out)
    f.close()
    DCOS_PACKAGE_NAME = app["labels"]["DCOS_PACKAGE_NAME"]
    if DCOS_PACKAGE_NAME != "jenkins":
        log.error('Cannot migrate "{}" package'.format(DCOS_PACKAGE_NAME))
        return
    DCOS_PACKAGE_VERSION = app["labels"]["DCOS_PACKAGE_VERSION"]
    match = False
    for ver in versions:
        if ver.DCOS_VERSION == DCOS_PACKAGE_VERSION:
            match = True
            break
    if not match:
        log.error('Cannot migrate "{}" package : version "{}" not yet supported'.format(DCOS_PACKAGE_NAME, DCOS_PACKAGE_VERSION))
        return
    TASKS = app["tasks"]
    if len(TASKS) != 1:
        log.error("Ambiguity finding task id")
        return
    TASK_ID = TASKS[0]["id"]
    return DCOS_PACKAGE_VERSION, TASK_ID


def download_task_data(task_id: str, target_dir: str, retain_builds: bool, retain_next_build_number: bool) -> str:
    log.info("Downloading config.xml")
    run_cmd("{} -v task download {} jenkins_home/config.xml --target-dir={}".format(DCOS, task_id, target_dir), check=True)
    log.info('Downloading jobs folder')
    run_cmd("{} task download {} jenkins_home/jobs --target-dir={}".format(DCOS, task_id, target_dir), check=True)
    return "{}/config.xml".format(target_dir)


def print_instructions(pkg_ver):
    GENERIC_VALUES = '''
master:
  tag: {tag}
  useSecurity: false
  installPlugins:
    - kubernetes:{kubernetes_plugin}
  additionalPlugins: []
  csrf:
    defaultCrumbIssuer:
      enabled: false
      proxyCompatability: false
  prometheus:
    enabled: true
    serviceMonitorNamespace: "kubeaddons"
    serviceMonitorAdditionalLabels:
      app: jenkins
      release: prometheus-kubeaddons
  serviceType: "LoadBalancer"
  jenkinsUriPrefix: "/jenkins"
  ingress:
    enabled: true
    path: /jenkins
    annotations:
      kubernetes.io/ingress.class: traefik
  JCasC:
    enabled: false
'''
    HELM_2_CMD = '''
helm install \\
    --namespace jenkins \\
    --name jenkins \\
    -f values.yaml \\
    --set serviceAccount.create=false \\
    --set serviceAccount.name=jenkins \\
    --set serviceAccountAgent.name=jenkins \\
    --repo https://charts.jenkins.io \\
    --version {version} \\
    jenkins
'''
    HELM_3_CMD = '''
helm install jenkins \\
    --namespace jenkins \\
    -f values.yaml \\
    --set serviceAccount.create=false \\
    --set serviceAccount.name=jenkins \\
    --set serviceAccountAgent.name=jenkins \\
    --repo https://charts.jenkins.io \\
    --version {version} \\
    jenkins
'''

    PLUGIN_SCRIPT = '''Jenkins.instance.pluginManager.plugins.each{
  plugin -> 
    println ("- ${plugin.getShortName()}:${plugin.getVersion()}")
}'''

    for ver in versions:
        if ver.DCOS_VERSION == pkg_ver:
            log.info('''Use following values.yaml to install helm chart:
cat <<EOF >> values.yaml{values}EOF
==========
For migrating the plugins, go to "<jenkins-url>/script" and run the following script:

{plugin}

to get a list of plugins which can be added under "master.additionalPlugins" field in values.yaml supplied to helm install command
==========
Run the following command to install the chart:
Using helm v2:
{helm_2_cmd}
Using helm v3:
{helm_3_cmd}
'''.format(values=GENERIC_VALUES.format(tag=ver.JENKINS_VERSION, kubernetes_plugin=ver.KUBERNETES_PLUGIN_VERSION),
           plugin=PLUGIN_SCRIPT, helm_2_cmd=HELM_2_CMD.format(version=ver.CHART_VERSION),
           helm_3_cmd=HELM_3_CMD.format(version=ver.CHART_VERSION)))
