import argparse
import contextlib
import glob
import logging
import os
import shutil
import sys

import mesos_to_k8_translator
import parse_dcos_package

# KUBERNETES CLI
kubectl = os.getenv("KUBECTL", "kubectl")

log = logging.getLogger("root")
logging.basicConfig(level=logging.WARN, format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s', )


def load(args):
    log.info('loading DC/OS package with marathon app id {} into target directory {}'.format(args.app_id, args.target_dir))
    pkg_ver, task_id = parse_dcos_package.load_dcos_package(args.app_id)
    parse_dcos_package.download_task_data(task_id, args.target_dir)
    parse_dcos_package.print_instructions(pkg_ver)
    print('Create the following serviceaccount, roles, and rolebindings prior to running helm install:\n\n{}\n\n'.format(
        "{} apply -f resources/serviceaccount.yaml --namespace jenkins".format(kubectl)
    ))


def translate(args):
    log.info('translating mesos config.xml to k8 config.xml from {} to {}'.format(args.config_file, args.target_file))
    # Point to config.xml downloaded from DC/OS Jenkins Installation
    out = mesos_to_k8_translator.translate_mesos_to_k8_config_xml(args.config_file, args.target_file)
    if args.print:
        log.info("generated config.xml\n======\n{}".format(out))
    print('Copy the generated "{}" to Jenkins master node on kubernetes using command :\n\n{}\n\n'.format(
        args.target_file,
        "{} cp {} <jenkins-pod-name>:/var/jenkins_home/config.xml --namespace jenkins --container jenkins".format(kubectl, args.target_file)
    ))
    print(
        'Create the following ConfigMap that will be used to mount the JNLP configuration script for your jenkins agents:\n\n{}\n\n'.format(
            "{} apply -f resources/configmap-jenkins-agent-3-35-5.yaml --namespace jenkins".format(kubectl)))


def jobs_list(args):
    printed_once = False
    job_folders = {}
    target_dir = os.path.abspath(args.target_dir)
    jobs, expanded = _jobs_dir(args.target_dir, args.pattern)
    folder_icons = {}
    for job in jobs:
        abspath = os.path.abspath(job)
        simplename = abspath.replace(target_dir, "").lstrip("jobs/").lstrip("/jobs/")
        if not _is_job_folder(job):
            if os.path.isdir(os.path.join(job, "jobs")):
                # This folder contains other jobs, add config.xml to create a valid folder
                folder_icons[simplename] = os.path.join(abspath, "config.xml")
            continue
        if not printed_once:
            log.info("following jobs are detected:")
            print("-------------")
            printed_once = True
        job_folders[simplename] = abspath
        print(simplename)
    if printed_once:
        print("-------------")
    else:
        print('no jobs were found in given directory "{}". exiting...'.format(target_dir))
        return

    # If list only is set, print the names and exit
    if args.list_only:
        log.info("exiting the script after printing the list of jobs")
        return

    name = args.name
    ns = args.namespace
    cmds = []
    for simplename, abspath in job_folders.items():
        cmds.append('{} exec {} --namespace {} --container jenkins -- sh -c "mkdir -p /var/jenkins_home/jobs/{}"'.format(kubectl, name, ns, simplename))
        cmds.append("{} --namespace {} --container jenkins cp {} {}:/var/jenkins_home/jobs/{}".format(kubectl, ns, abspath, name, simplename))
    for target, src in folder_icons.items():
        print(
            "{} --namespace {} --container jenkins cp {} {}:/var/jenkins_home/jobs/{}".format(kubectl, ns, src, name, target))

    dry_run = args.dry_run or name.startswith("<") or ns.startswith("<")

    if expanded:
        # Print or execute each command.
        if dry_run:
            print("Execute the following commands to copy the jobs:")
            for c in cmds:
                print(c)
        else:
            for c in cmds:
                parse_dcos_package.run_cmd(c)
    else:
        # No need to print multiple commands. Just bulk copy single folder.
        cmd = "{} --namespace {} --container jenkins cp {} {}:/var/jenkins_home/".format(
            kubectl, ns, os.path.join(target_dir, "jobs"), name)
        if dry_run:
            print("Execute the following command to copy the jobs:\n{}".format(cmd))
        else:
            parse_dcos_package.run_cmd(cmd, print_output=True, check=True)


def jobs_cleanup(args):
    jobs, _ = _jobs_dir(args.target_dir, args.pattern)
    count = 0
    for job in jobs:
        if not _is_job_folder(job):
            continue
        count = count + 1
        # Optionally, remove "builds" folder
        if not args.skip_builds:
            shutil.rmtree(os.path.join(job, "builds"), ignore_errors=True)

        # Optionally, remove "nextBuildNumber" file
        if not args.skip_next_build_number:
            with contextlib.suppress(FileNotFoundError):
                os.remove(os.path.join(job, "nextBuildNumber"))

        # Optionally, update config.xml to disable job
        if args.disable_jobs:
            job_config_xml = os.path.join(job, "config.xml")
            parse_dcos_package.run_cmd(
                "sed -i '' 's/{}/{}/' {}".format("<disabled>false<\/disabled>", "<disabled>true<\/disabled>", job_config_xml),
                print_output=False,
                check=False)
    log.info("processed {} jobs".format(count))


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


def _jobs_dir(jenkins_home: str, pattern: str) -> ([str], bool):
    jobs_dir = os.path.join(jenkins_home, "jobs")
    paths = [jobs_dir]
    expanded = False
    if pattern != "*":
        expanded = True
        # Default to everything in the folder, but honor any specified glob expression.
        expanded_dirs = glob.glob(os.path.join(jobs_dir, pattern))
        if len(expanded_dirs) == 0:
            log.error('error parsing given glob expression : {}, found 0 paths matching the expr'.format(pattern))
        paths = expanded_dirs
    dirs = [p[0] for path in paths for p in os.walk(path)]
    return dirs, expanded


def main():
    # Dummy parent parser to share common global level args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("-t", "--target-dir", type=str, default="./jenkins_home",
                               help='points to jenkins_home folder with a valid "jobs" folder')

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='sub-commands available')

    # Step 1 : Download the DC/OS Jenkins task data
    loader = subparsers.add_parser("load", help='Load the DC/OS package data', parents=[parent_parser])
    loader.add_argument("--app-id", type=str, default="jenkins", help="Marathon application ID")
    loader.set_defaults(func=load)

    # Step 2 : Migrate the config.xml from DC/OS Jenkins format to Kubernetes Jenkins format
    translator = subparsers.add_parser("translate", help='Translate the MesosCloud based config.xml to KubernetesCloud based config.xml')
    translator.add_argument("-c", "--config-file", type=str, default="./jenkins_home/config.xml", help="path of the config.xml file")
    translator.add_argument("-t", "--target-file", type=str, default="k8s.config.xml", help="path of the target config.xml file")
    translator.add_argument("-p", "--print", action='store_true', help="Print the transformed cloud config element from config.xml")
    translator.set_defaults(func=translate)

    # Step 3 : Cleanup jobs
    jobs = subparsers.add_parser("jobs", help='Clean and copy jobs')
    jobs.add_argument("-p", "--pattern", type=str, default="*",
                      help="glob expression to select jobs. E.g.: hello* OR hello/world/* etc.,")
    jobs_helpers = jobs.add_subparsers(help="perform various operations on jobs")

    # Step 3a: Optional : Clean up build history and reset build counter
    jobs_cleanup_cmd = jobs_helpers.add_parser("clean", parents=[parent_parser])
    jobs_cleanup_cmd.add_argument("--skip-builds", action='store_true', help="Set to skip removal of previous builds")
    jobs_cleanup_cmd.add_argument("--skip-next-build-number", action='store_true', help='Set to skip removal of nextBuildNumber counter')
    jobs_cleanup_cmd.add_argument("--disable-jobs", action='store_true',
                                  help='If set, the job config.xml is updated to disable the job by setting "<disabled>true</disabled>"')
    # jobs_cleanup_cmd.add_argument("-p", "--pattern", type=str, default="*",
    #                               help="glob expression to select jobs. E.g.: hello* OR hello/world/* etc.,")
    jobs_cleanup_cmd.set_defaults(func=jobs_cleanup)

    # Step 3b: List jobs and copy them to kubernetes jenkins instance
    jobs_list_cmd = jobs_helpers.add_parser("list", parents=[parent_parser])
    jobs_list_cmd.add_argument("--name", type=str, default="<pod-name-here>", help="Name of the jenkins pod")
    jobs_list_cmd.add_argument("--namespace", type=str, default="<pod-name-here>", help="Namespace of the jenkins pod")
    jobs_list_cmd.add_argument("--list-only", action='store_true', help="Set the flag to print the list of jobs and exit")
    jobs_list_cmd.add_argument("--dry-run", action='store_true',
                               help="Setting this flag would just print the commands without executing them")
    jobs_list_cmd.set_defaults(func=jobs_list)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()
