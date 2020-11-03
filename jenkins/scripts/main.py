import argparse
import contextlib
import logging
import os
import shutil
import sys

import mesos_to_k8s_translator
import parse_dcos_package

# KUBERNETES CLI
kubectl = os.getenv("KUBECTL", "kubectl")

log = logging.getLogger("root")
logging.basicConfig(level=logging.WARN, format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s', )


def download(args):
    log.info('Downloading DC/OS package with marathon app id {} into target directory {}'.format(args.app_id, args.target_dir))
    pkg_ver, task_id = parse_dcos_package.download_dcos_package(args.app_id, args.target_dir)
    parse_dcos_package.download_task_data(task_id, args.target_dir, args.retain_builds, args.retain_next_build_number)

    do_cleanup = not args.retain_next_build_number or not args.retain_builds
    if do_cleanup:
        jobs_dir = os.path.join(os.path.abspath(args.target_dir), "jobs")
        for dirpath, d_names, f_names in os.walk(jobs_dir):
            if not os.path.exists(dirpath):
                continue
            if not ("builds" in d_names and "nextBuildCounter" in f_names):
                continue
            if not args.retain_builds:
                shutil.rmtree(os.path.join(dirpath, "builds"), ignore_errors=True)
            # Optionally, remove "nextBuildNumber" file
            if not args.retain_next_build_number:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(os.path.join(dirpath, "nextBuildCounter"))
    parse_dcos_package.print_instructions(pkg_ver)
    print('Create the following serviceaccount, roles, and rolebindings prior to running helm install:\n\n{}\n\n'.format(
        "{} apply -f resources/serviceaccount.yaml --namespace jenkins".format(kubectl)
    ))


def translate(args):
    log.info('Translating mesos config.xml to k8s config.xml from {} to {}'.format(args.config_file, args.target_file))
    # Point to config.xml downloaded from DC/OS Jenkins Installation
    out = mesos_to_k8s_translator.translate_mesos_to_k8s_config_xml(args.config_file, args.target_file)
    if args.print:
        log.info("Generated config.xml\n======\n{}".format(out))
    print('Copy the generated "{}" to Jenkins master node on kubernetes using command :\n\n{}\n\n'.format(
        args.target_file,
        "{} cp {} <jenkins-pod-name>:/var/jenkins_home/config.xml --namespace jenkins --container jenkins".format(kubectl, args.target_file)
    ))
    print(
        'Create the following ConfigMap that will be used to mount the JNLP configuration script for your jenkins agents:\n\n{}\n\n'.format(
            "{} apply -f resources/configmap-jenkins-agent-3-35-5.yaml --namespace jenkins".format(kubectl)))


def jobs_copy(args):
    abs_target_dir = os.path.abspath(args.target_dir)
    folder, pod_path = _jobs_dir(abs_target_dir, args.path)
    ns = args.namespace
    _, name, _ = parse_dcos_package.run_cmd(
        '{} get pods --namespace {} --label app.kubernetes.io/instance={} --no-headers --output custom-columns=":metadata.name"'.format(
            kubectl, ns, args.release_name), check=True)
    cmds = [
        '{} exec {} --namespace {} --container jenkins -- sh -c "mkdir -p /var/jenkins_home{}"'.format(kubectl, name, ns, pod_path),
        '{} --namespace {} --container jenkins cp {} {}:/var/jenkins_home/{}'.format(kubectl, ns, folder, name, pod_path)
    ]

    # Print or execute each command.
    if args.dry_run:
        print("Execute the following commands to copy the jobs:")
        for c in cmds:
            print(c)
    else:
        for c in cmds:
            parse_dcos_package.run_cmd(c)


def jobs_update(args):
    target_dir = os.path.abspath(args.target_dir)
    folder, _ = _jobs_dir(target_dir, args.path)
    count = 0
    for dirpath, d_names, f_names in os.walk(folder):
        if "jobs" in d_names or os.path.basename(dirpath) == "jobs":
            # This folder contains sub-sub directories which has other jobs. Nothing to do in this directory
            continue
        if args.disable_jobs:
            job_config_xml = os.path.join(dirpath, "config.xml")
            parse_dcos_package.run_cmd(
                "sed -i '' 's/{}/{}/' {}".format("<disabled>false<\/disabled>", "<disabled>true<\/disabled>", job_config_xml),
                print_output=False,
                check=False)
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


def _jobs_dir(jenkins_home: str, path: str) -> (str, str):
    folder_path = os.path.join(jenkins_home, "jobs")
    if path == "*":
        return folder_path, "/jobs/"
    # Default to everything in the folder, but honor any specified relative path.
    # In file system we have <folder-name>/jobs/<sub-folder-name>/jobs/<job-name>/config.xml
    # In given path, "jobs" get replaced by "job" but everything else remains the same
    if path.startswith("job/"):
        path = "/" + path
    if not path.startswith("/job/"):
        log.error("invalid path specified : {}".format(path))
    path = path.replace("/job/", "/jobs/")
    folder_path = os.path.join(jenkins_home, path)
    return folder_path, path


def main():
    # Dummy parent parser to share common global level args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-t", "--target-dir", type=str, default="./jenkins_home",
                               help='points to jenkins_home folder with a valid "jobs" folder')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available')

    # Step 1 : Download the DC/OS Jenkins task data
    downloader = subparsers.add_parser("download", help='Download the DC/OS package data', parents=[parent_parser])
    downloader.add_argument("--app-id", type=str, default="jenkins", help="Marathon application ID")
    downloader.add_argument("--retain-builds", action='store_true', help="Set to retain previous builds data")
    downloader.add_argument("--retain-next-build-number", action='store_true', help='Set to retain nextBuildNumber counter')
    downloader.set_defaults(func=download)

    # Step 2 : Migrate the config.xml from DC/OS Jenkins format to Kubernetes Jenkins format
    translator = subparsers.add_parser("translate", help='Translate the MesosCloud based config.xml to KubernetesCloud based config.xml')
    translator.add_argument("-c", "--config-file", type=str, default="./jenkins_home/config.xml", help="path of the config.xml file")
    translator.add_argument("-t", "--target-file", type=str, default="k8s.config.xml", help="path of the target config.xml file")
    translator.add_argument("-p", "--print", action='store_true', help="Print the transformed cloud config element from config.xml")
    translator.set_defaults(func=translate)

    # Step 3 : Optionally disable jobs and copy them
    jobs = subparsers.add_parser("jobs", help='Perform various operations on jobs')
    jobs_helpers = jobs.add_subparsers(help="Perform various operations on jobs")

    # Step 3a: Optional : Disable jobs
    job_path_help = "URL of the job or folder. This is the part after http://<cluster-url>/service/<service-name>/<job-path-here>"
    jobs_update_cmd = jobs_helpers.add_parser("update", parents=[parent_parser])
    jobs_update_cmd.add_argument("--path", type=str, default="*", help=job_path_help)
    jobs_update_cmd.add_argument("--disable-jobs", action='store_true',
                                 help='If set, the job config.xml is updated to disable the job by setting "<disabled>true</disabled>"')
    jobs_update_cmd.set_defaults(func=jobs_update)

    # Step 3b: Copy jobs to kubernetes jenkins instance
    jobs_copy_cmd = jobs_helpers.add_parser("copy", parents=[parent_parser])
    jobs_copy_cmd.add_argument("--path", type=str, default="*", help=job_path_help)
    jobs_copy_cmd.add_argument("--namespace", type=str, default="jenkins", help="Namespace of the jenkins pod (defaults to jenkins)")
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
