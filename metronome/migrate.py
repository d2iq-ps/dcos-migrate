#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys

# This script relies on python-yaml installed via pip, system package manager or some other means.
import yaml

from utils import deep_get, deep_merge, flatten, load_json_file


def info(msg):
    print(f"[INFO] {msg}", file=sys.stderr)


def warn(msg):
    print(f"[WARN] {msg}", file=sys.stderr)


def dnsify(name):
    new_name = re.sub("[^a-z0-9-]+", "-", name.lower())
    if not name == new_name:
        info(
            f'"{name}" is not a valid name in kubernetes. converted it to "{new_name}".'
        )
    return new_name


EXTRACT_COMMAND = dict(
    [(".zip", "gunzip")]
    + [
        (ext, "tar -xf")
        for ext in [".tgz", ".tar.gz", ".tbz2", ".tar.bz2", ".txz", ".tar.xz"]
    ]
)


def generate_fetch_command(uri: str, allow_extract: bool, executable: bool):
    # NOTE: The path separator is always '/', even on Windows.
    _, _, filename = uri.rpartition("/")
    _, ext = os.path.splitext(filename)

    postprocess = (
        "chmod a+x"
        if executable
        else (EXTRACT_COMMAND.get(ext, "") if allow_extract else "")
    )

    fmt = (
        '( wget -O "{fn}" "{uri}" && {postprocess} "{fn}" )'
        if postprocess
        else '( wget -O "{fn}" "{uri}")'
    )

    return fmt.format(fn=filename, uri=uri, postprocess=postprocess)


###############################################################################
#                                   SCHEDULE                                  #
###############################################################################


def translate_schedule_prop(key, val, result):
    def update(props):
        return deep_merge(result, props)

    if ".schedules.0.concurrencyPolicy" == key:
        return update({"spec": {"concurrencyPolicy": val.title()}})

    if ".schedules.0.cron" == key:
        return update({"spec": {"schedule": val}})

    if ".schedules.0.enabled" == key:
        return update({"spec": {"suspend": not val}})

    if ".schedules.0.id" == key:
        return update({"metadata": {"name": dnsify(val)}})

    if ".schedules.0.nextRunAt" == key:
        return result  # Ignore!

    if ".schedules.0.startingDeadlineSeconds" == key:
        return update({"spec": {"startingDeadlineSeconds": val}})

    if ".schedules.0.timeZone" == key:
        if not ("UTC" == val):
            warn(
                f'You might need to edit the cron expression (spec.schedule) to account for an update from "{val}" to your target cluster\'s timezone.'
            )
        return result

    print(f"Unexpected property '{key}'!")
    return result


###############################################################################
#                                     JOB                                     #
###############################################################################
def translate_job_prop(key, val, result, args):
    def update(props):
        return deep_merge(result, props)

    def update_pod_spec(props):
        return update({"spec": {"template": {"spec": props}}})

    # For now we have the assumption that all jobs only run a single container.
    def update_container(props):
        return update_pod_spec({"containers": [props]})

    if re.match(".dependencies", key):
        warn("Not migrating dependencies")
        return result

    if ".description" == key:
        if not val:
            return result
        return update({"metadata": {"annotations": {"description": val}}})

    if ".id" == key:
        return update(
            {
                "metadata": {"name": dnsify(val)},
                "spec": {"template": {"spec": {"containers": [{"name": dnsify(val)}]}}},
            }
        )

    if ".labels" == key:
        return update({"metadata": {"labels": val}})

    if re.match(".run.args", key):
        args = result.get("run", {}).get("args", [])
        return update_container({"args": args.append(val)})

    if ".run.artifacts" == key:
        if not args.working_dir:
            raise RuntimeError(
                'Job is using "fetch"; please specify non-empty `--working-dir` and run again'
            )

        def iter_command():
            yield "set -x"
            yield "set -e"
            yield "cd /fetch_artifacts"
            yield "FETCH_PID_ARRAY=()"

            for fetch in val:
                fetch = fetch.copy()
                uri = fetch.pop("uri")
                cache = fetch.pop("cache", False)
                extract = fetch.pop("extract", True)
                executable = fetch.pop("executable", False)
                if fetch:
                    warn(f'Unknown fields in "fetch": {json.dumps(fetch)}')
                if cache:
                    warn(
                        f'`cache=true` requested for fetching "{uri}" has been ignored'
                    )
                if uri.startswith("file://"):
                    warn(f"Fetching a local file {uri} is not portable")
                yield generate_fetch_command(
                    uri, extract, executable
                ) + ' & FETCH_PID_ARRAY+=("$!")'
            yield "for pid in ${FETCH_PID_ARRAY[@]}; do wait $pid || exit $?; done"

        return update_pod_spec(
            {
                "containers": [
                    {
                        "volumeMounts": [
                            {"name": "fetch-artifacts", "mountPath": args.working_dir,}
                        ]
                    }
                ],
                "initContainers": {
                    "name": "fetch",
                    "image": "bash:5.0",
                    "command": ["bash", "-c", "\n".join(iter_command())],
                    "volumeMounts": [
                        {"name": "fetch-artifacts", "mountPath": "/fetch-artifacts"}
                    ],
                },
                "volumes": [{"name": "fetch-artifacts", "emptyDir": "{}"}],
            }
        )

    if ".run.cmd" == key:
        if not val:
            return result
        return update_container({"command": ["/bin/sh", "-c", val]})

    if ".run.cpus" == key:
        if val == 0:
            return result
        return update_container({"resources": {"limits": {"cpu": val}}})

    if ".run.docker.forcePullImage" == key:
        return update_container(
            {"imagePullPolicy": "Always" if val else "IfNotPresent"}
        )

    if ".run.docker.image" == key:
        return update_container({"image": val})

    if ".run.docker.parameters" == key:
        warn(f'DKP has no equivalent for "run.docker.parameters", dropping: "{val}"')
        return result

    if ".run.docker.privileged" == key:
        return update_container({"securityContext": {"privileged": val}})

    if ".run.disk" == key:
        if val == 0:
            return result
        return update_container({"resources": {"limits": {"ephemeral-storage": val}}})

    if re.match(".run.env", key):
        env = deep_get(result, "spec.template.spec.containers.0.env", [])
        env.append({"name": key.replace(".run.env.", ""), "value": val})
        return update_container({"env": env})

    if ".run.gpus" == key:
        if val == 0:
            return result
        return update_container(
            {
                "resources": {
                    "requests": {"nvidia.com/gpu": val},
                    "limits": {"nvidia.com/gpu": val},
                },
            }
        )

    if ".run.maxLaunchDelay" == key:
        if not val == 3600:
            warn("maxLaunchDelay is not available in DKP")
        return result

    if ".run.mem" == key:
        if val == 0:
            return result
        return update_container({"resources": {"limits": {"memory": str(val) + "Mi"}}})

    if ".run.networks" == key:
        warn("TODO: conversion of .run.networks is not yet implemented.")
        return result

    if ".run.placement.constraints" == key:
        warn("TODO: conversion of .run.placement.constraints is not yet implemented.")
        return result

    if ".run.restart.policy" == key:
        if val.title() == "Never":
            return update_pod_spec({"restartPolicy": val.title()})
        warn(
            f"restartPolicy '{val}' was dropped. Now the default of 'spec.backoffLimit' will implicitly try 6 times."
        )
        return result

    if ".run.restart.activeDeadlineSeconds" == key:
        warn(
            f'DKP has no equivalent for "run.restart.activeDeadlineSeconds", dropping: {val}'
        )
        return result

    if re.match(".run.secrets", key):
        warn("TODO: conversion of .run.secrets is not yet implemented.")
        return result

    if ".run.taskKillGracePeriodSeconds" == key:
        return update_pod_spec({"terminationGracePeriodSeconds": val})

    if re.match(".run.ucr", key):
        warn(
            f'Migrating "{key}" is not (yet) supported. You might want to manually convert and add your UCR configuration to the resulting yaml.'
        )
        return result

    if ".run.user" == key:
        warn(
            f'Found "run.user": "{val}". You might need to set "spec.template.spec.containers[].securityContext.runAsUser" manually, as we can\'t infer a mapping to the according uid on the target node.'
        )
        return result

    if re.match(".run.volumes", key):
        warn("TODO: conversion of .run.volumes is not yet implemented.")
        return result

    warn(f'Unexpected property "{key}"')
    return result


# we have some jobs on SOAK that use run.ucr.image.kind == 'docker' and seem to work well when converting:
def convert_ucr_to_docker(model):
    if not "docker" == model.pop(".run.ucr.image.kind", None):
        return

    warn(
        "Converting UCR configuration as .kind is 'docker'. Please check whether UCR is required for your use case."
    )
    if ".run.ucr.image.forcePull" in model:
        model[".run.docker.forcePullImage"] = model.pop(".run.ucr.image.forcePull")
    if ".run.ucr.image.id" in model:
        model[".run.docker.image"] = model.pop(".run.ucr.image.id")
    if ".run.ucr.privileged" in model:
        model[".run.docker.privileged"] = model.pop(".run.ucr.privileged")


###############################################################################
#                                     CLI                                     #
###############################################################################


def translate(args):
    plain_json = load_json_file(args.path)
    artifacts = plain_json["run"].pop("artifacts", None)
    labels = plain_json.pop("labels", None)
    secrets = plain_json["run"].pop("secrets", None)

    if secrets is not None:
        warn(
            """TODO: definition contains secrets. you'll need to go through the env vars and look for those ending in '.secret', migrate the according secret and add a section like the following for each:
- name: MY_ENV_VAR
  valueFrom:
  secretKeyRef:
      name: mysecret
      key: SECRET_KEY
"""
        )

    model = flatten(plain_json)
    convert_ucr_to_docker(model)
    if artifacts:
        model[".run.artifacts"] = artifacts
    if labels:
        model[".labels"] = labels

    job_props = [(k, v) for k, v in model.items() if not re.match(".schedules", k)]
    schedule_props = [(k, v) for k, v in model.items() if re.match(".schedules", k)]

    plain_job = {}
    for k, v in job_props:
        plain_job = translate_job_prop(k, v, plain_job, args)

    # ensure an image is set
    if plain_job["spec"]["template"]["spec"]["containers"][0].get("image") is None:
        if not args.image:
            raise RuntimeError(
                "Job does not specify an image; please specify an `--image` to use."
            )
        plain_job = translate_job_prop(".run.docker.image", args.image, plain_job, args)

    if any(schedule_props) > 0:
        cron_job = {
            "apiVersion": "batch/v1beta1",
            "kind": "CronJob",
            "spec": {"jobTemplate": plain_job},
        }

        for k, v in schedule_props:
            cron_job = translate_schedule_prop(k, v, cron_job)

        print(yaml.safe_dump(cron_job))

    else:
        job = deep_merge(plain_job, {"apiVersion": "batch/v1", "kind": "Job"})
        print(yaml.safe_dump(job))


def download():
    subprocess.call("./downloadAll.sh", shell=True)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="sub-commands available")

    translate_cmd = subparsers.add_parser(
        "translate", help="Translate the Metronome Job into a K8s Job/CronJob"
    )
    translate_cmd.add_argument("path", help="path to a Metronome JobSpec")
    translate_cmd.add_argument(
        "--working-dir", help="Needs to be set in case your Job used 'artifacts'"
    )
    translate_cmd.add_argument(
        "--image",
        help="A docker image to fall back to in case your Job definition does not contain one",
    )
    translate_cmd.set_defaults(func=lambda args: translate(args))

    download_cmd = subparsers.add_parser(
        "download",
        help="Download all Metronome Jobs from a DC/OS cluster to ./metronome-jobs/<id>.json",
    )
    download_cmd.set_defaults(func=lambda args: download())

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()