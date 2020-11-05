import argparse
import contextlib
import logging
import os
import shutil
import sys
from collections import namedtuple

import translator
import downloader

# KUBERNETES CLI
kubectl = os.getenv("KUBECTL", "kubectl")

log = logging.getLogger("root")
logging.basicConfig(level=logging.WARN, format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s', )

# Edit/Update as needed
Mapping = namedtuple("Mapping", ["DCOS_VERSION", "JENKINS_VERSION", "KUBERNETES_PLUGIN_VERSION", "CHART_VERSION"])
versions = [Mapping("3.6.1-2.190.1", "2.190.1", "1.24.1", "2.6.4")]  # TODO support more versions

separator = "--------------------------------------------------"


# Return the downloaded package version
def download(args) -> str:
    log.info('Downloading DC/OS package with marathon app id {} into target directory {}'.format(args.app_id, args.target_dir))
    pkg_ver, task_id = downloader.download_dcos_package(args.app_id, args.target_dir, [versions[0][0]])
    downloader.download_task_data(task_id, args.target_dir, args.retain_builds, args.retain_next_build_number)

    if args.retain_builds and args.retain_next_build_number:
        return pkg_ver

    # Perform cleanup. TODO: Instead of downloading and removing, download only what's needed.
    builds_dir = "builds"
    nextBuildNumber_file = "nextBuildNumber"
    jobs_dir = os.path.join(os.path.abspath(args.target_dir), "jobs")
    for dirpath, d_names, f_names in os.walk(jobs_dir):
        if not os.path.exists(dirpath):
            continue
        if not args.retain_builds and builds_dir in d_names:
            shutil.rmtree(os.path.join(dirpath, "builds"), ignore_errors=True)
        # Optionally, remove "nextBuildNumber" file
        if not args.retain_next_build_number and nextBuildNumber_file in f_names:
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(dirpath, nextBuildNumber_file))
    return pkg_ver


def print_instructions(namespace: str, ver: Mapping = versions[0]):  # TODO: support more versions
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
    sidecars:
      configAutoReload:
        enabled: false
'''
    HELM_2_CMD = '''
helm install \\
    --namespace {namespace} \\
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
    --namespace {namespace} \\
    -f values.yaml \\
    --set serviceAccount.create=false \\
    --set serviceAccount.name=jenkins \\
    --set serviceAccountAgent.name=jenkins \\
    --repo https://charts.jenkins.io \\
    --version {version} \\
    jenkins
'''

    PLUGIN_SCRIPT = '''def skipPlugins = ["mesos", "metrics-graphite"]
Jenkins.instance.pluginManager.plugins.each{
  plugin ->
    name = plugin.getShortName()
    if (!skipPlugins.contains(name)) {
        println ("- ${name}:${plugin.getVersion()}")
    }
}
'''
    print(separator)
    print('Create the following serviceaccount, roles, and rolebindings prior to running helm install:\n{}'.format(
        "{} apply -f ./jenkins/resources/serviceaccount.yaml --namespace jenkins".format(kubectl)
    ))
    print(separator)
    print('Use following values.yaml to install helm chart\ncat <<EOF >> values.yaml{}EOF'.format(
        GENERIC_VALUES.format(tag=ver.JENKINS_VERSION, kubernetes_plugin=ver.KUBERNETES_PLUGIN_VERSION)))
    print(separator)
    print('For migrating the plugins, go to "<jenkins-url>/script" and run the following script:\n\n{}\nto get a list of plugins '
          'which can be added under "master.additionalPlugins" field in values.yaml'.format(PLUGIN_SCRIPT))
    print(separator)
    print("Run the following command to install the chart:\nUsing helm v2:\n{}\nUsing helm v3:\n{}".format(
        HELM_2_CMD.format(version=ver.CHART_VERSION, namespace=namespace),
        HELM_3_CMD.format(version=ver.CHART_VERSION, namespace=namespace)))
    print(separator)


def translate(args):
    print_instructions(args.namespace)
    log.info('Translating mesos config.xml to k8s config.xml from {} to {}'.format(args.config_file, args.target_file))
    os.environ["JENKINS_NAMESPACE"] = args.namespace
    os.environ["JENKINS_FULL_NAME"] = args.fullname
    os.environ["JENKINS_URI_PREFIX"] = args.uri_prefix
    out = translator.translate_mesos_to_k8s_config_xml(args.config_file, args.target_file)
    if args.print:
        log.info("Generated config.xml\n======\n{}".format(out))
    print(separator)
    pod_name_cmd = '{} get pods --namespace {} -l=app.kubernetes.io/instance=jenkins --no-headers --output custom-columns=":metadata.name"'.format(kubectl, args.namespace)
    print('Copy the generated "{}" to Jenkins master node on kubernetes using command :\n{}'.format(
        args.target_file,
        "{} cp {} $({}):/var/jenkins_home/config.xml --namespace {} --container jenkins".format(kubectl, args.target_file, pod_name_cmd, args.namespace)
    ))
    print(separator)
    print(
        'Create the following ConfigMap that will be used to mount the JNLP configuration script for your jenkins agents:\n{}'.format(
            "{} apply -f ./jenkins/resources/configmap-jenkins-agent-3-35-5.yaml --namespace {}".format(kubectl, args.namespace)))
    print(separator)


def jobs_copy(args):
    abs_target_dir = os.path.abspath(args.target_dir)
    src_folder, target_folder = _jobs_dir(abs_target_dir, args.path)
    ns = args.namespace
    _, name, _ = downloader.run_cmd(
        '{} get pods --namespace {} -l=app.kubernetes.io/instance={} --no-headers --output custom-columns=":metadata.name"'.format(
            kubectl, ns, args.release_name), check=True)
    cmds = [
        '{} exec {} --namespace {} --container jenkins -- sh -c "mkdir -p {}"'.format(kubectl, name, ns, target_folder),
        '{} --namespace {} --container jenkins cp {} {}:{}'.format(kubectl, ns, src_folder, name, os.path.dirname(target_folder.rstrip("/")))
    ]

    # Print or execute each command.
    if args.dry_run:
        print("Execute the following commands to copy the jobs:")
        for c in cmds:
            print(c)
        return
    for c in cmds:
        downloader.run_cmd(c, print_output=True, print_cmd=True)


def jobs_update(args):
    target_dir = os.path.abspath(args.target_dir)
    folder, _ = _jobs_dir(target_dir, args.path)
    count = 0
    for dirpath, d_names, f_names in os.walk(folder):
        if "jobs" in d_names or os.path.basename(dirpath) == "jobs":
            # This folder contains sub-sub directories which has other jobs. Nothing to do in this directory
            continue
        job_config_xml = os.path.join(dirpath, "config.xml")
        if not os.path.exists(job_config_xml):
            continue
        modified = False
        if args.disable_jobs:
            downloader.run_cmd(
                "sed -i '' -e 's/{}/{}/g' {}".format("<disabled>false<\/disabled>", "<disabled>true<\/disabled>", job_config_xml),
                print_output=False,
                check=False)
            modified = True
        if args.remove_single_slave:
            downloader.run_cmd(
                "sed -i '' -e 's/{}//g' {}".format('<org.jenkinsci.plugins.mesos.MesosSingleUseSlave plugin="mesos@[0-9.]*"\/>',
                                                   job_config_xml),
                print_output=False,
                check=False)
            modified = True
        if modified:
            count = count + 1

    log.info('Processed "{}" jobs from "{}"'.format(count, folder))


def _is_job_folder(path: str) -> bool:
    # We ensure a folder corresponds to a job by:
    #
    # 1. Making sure parent of current folder is "jobs" AND
    # 2. Making sure the current folder does not have any folder named "jobs"
    # BOTH the above criteria needs to be true for a folder to be a valid job folder
    if not os.path.exists(path):
        return False
    if not os.path.dirname(path).endswith("/jobs"):
        return False
    if os.path.isdir(os.path.join(path, "jobs")):
        return False
    return True


# Returns source folder name and absolute target folder name that always starts with "/var/jenkins_home/jobs..."
def _jobs_dir(jenkins_home: str, path: str) -> (str, str):
    folder_path = os.path.join(jenkins_home, "jobs")
    var_jenkins_home = "/var/jenkins_home"
    if path == "*":
        return folder_path, "{}/jobs/".format(var_jenkins_home)
    # Default to everything in the folder, but honor any specified relative path.
    # In file system we have <folder-name>/jobs/<sub-folder-name>/jobs/<job-name>/config.xml
    # In given path, "jobs" get replaced by "job" but everything else remains the same
    if path.startswith("job/"):
        path = "/" + path
    if not path.startswith("/job/"):
        log.fatal("invalid path specified : {}".format(path))
    path = path.replace("/job/", "/jobs/")
    folder_path = os.path.join(jenkins_home, path.lstrip("/"))
    return folder_path, "{}{}".format(var_jenkins_home, path)


def main():
    # Dummy parent parser to share common global level args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-t", "--target-dir", type=str, default="./jenkins_home",
                               help='points to jenkins_home folder with a valid "jobs" folder')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available')

    # Step 1 : Download the DC/OS Jenkins task data
    downloader_cmd = subparsers.add_parser("download", help='Download the DC/OS package data', parents=[parent_parser])
    downloader_cmd.add_argument("--app-id", type=str, default="jenkins", help="Marathon application ID")
    downloader_cmd.add_argument("--retain-builds", action='store_true', help="Set to retain previous builds data")
    downloader_cmd.add_argument("--retain-next-build-number", action='store_true', help='Set to retain nextBuildNumber counter')
    downloader_cmd.set_defaults(func=download)

    # Step 2 : Migrate the config.xml from DC/OS Jenkins format to Kubernetes Jenkins format
    translator_cmd = subparsers.add_parser("translate",
                                           help='Translate the MesosCloud based config.xml to KubernetesCloud based config.xml')
    translator_cmd.add_argument("-c", "--config-file", type=str, default="./jenkins_home/config.xml", help="path of the config.xml file")
    translator_cmd.add_argument("-t", "--target-file", type=str, default="k8s.config.xml", help="path of the target config.xml file")
    translator_cmd.add_argument("-p", "--print", action='store_true', help="Print the transformed cloud config element from config.xml")
    translator_cmd.add_argument("--namespace", type=str, default="jenkins", help="Namespace of the jenkins pod (defaults to jenkins)")
    translator_cmd.add_argument("--fullname", type=str, default="jenkins", help="Name of the jenkins helm installation (defaults to jenkins)")
    translator_cmd.add_argument("--uri-prefix", type=str, default="/jenkins", help="Uri prefix for jenkins chart (defaults to /jenkins)")
    translator_cmd.set_defaults(func=translate)

    # Step 3 : Optionally disable jobs and copy them
    jobs = subparsers.add_parser("jobs", help='Perform various operations on jobs')
    jobs_helpers = jobs.add_subparsers(help="Perform various operations on jobs")

    # Step 3a: Optional : Disable jobs
    job_path_help = "URL of the job or folder. This is the part after http://<cluster-url>/service/<service-name>/<job-path-here>"
    jobs_update_cmd = jobs_helpers.add_parser("update", parents=[parent_parser])
    jobs_update_cmd.add_argument("--path", type=str, default="*", help=job_path_help)
    jobs_update_cmd.add_argument("--disable-jobs", action='store_true',
                                 help='If set, the job config.xml is updated to disable the job by setting "<disabled>true</disabled>"')
    jobs_update_cmd.add_argument("--remove-single-slave", action='store_true',
                                 help='If set, the job config.xml is updated by removing the MesosSingleUseSlave build wrapper')
    jobs_update_cmd.set_defaults(func=jobs_update)

    # Step 3b: Copy jobs to kubernetes jenkins instance
    jobs_copy_cmd = jobs_helpers.add_parser("copy", parents=[parent_parser])
    jobs_copy_cmd.add_argument("--path", type=str, default="*", help=job_path_help)
    jobs_copy_cmd.add_argument("--namespace", type=str, default="jenkins", help="Namespace of the jenkins installation (defaults to jenkins)")
    jobs_copy_cmd.add_argument("--release-name", type=str, default="jenkins", help="Helm release name (defaults to jenkins)")
    jobs_copy_cmd.add_argument("--dry-run", action='store_true',
                               help="Setting this flag would just print the commands without executing them")
    jobs_copy_cmd.set_defaults(func=jobs_copy)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
