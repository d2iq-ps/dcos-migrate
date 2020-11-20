import logging as log
import json
import os
import subprocess
import sys

from utils import encoding, remove_prefix, run_cmd

# DCOS CLI
DCOS = os.getenv("DCOS_CLI", "dcos")
MARATHON_JSON = "marathon_app.json"
CASSANDRA_ENV_JSON = "cassandra_env.json"


def _fetch_tasks_envs(app_id: str, task_count: int) -> dict:
    envs = {}
    for task in range(task_count):
        task_name = remove_prefix(app_id, '/').replace('/', '.') + "__node-{}-server__".format(task)
        log.info("Downloading configuration from task: {}".format(task_name))
        _, out, err = run_cmd("{} task exec {} bash -c 'env'".format(DCOS, task_name))
        for env in out.split('\n'):
            key,value = env.split('=')
            if key not in envs:
                envs[key] = [value]
            else:
                envs[key].append(value)
    return envs


def _sanitize_and_merge_envs(app_env: dict, task_env: dict) -> dict:
    envs = {}
    for (k,v) in app_env.items():
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    for (k,v) in task_env.items():
        if v.count(v[0]) == len(v):
            v = v[0]
        envs[remove_prefix(k, "TASKCFG_ALL_")] = v
    return envs


def download_dcos_package(app_id: str, target_dir: str, versions: [str]) -> [str, str]:
    log.info("Validating DC/OS CLI is setup correctly")
    run_cmd("{} --version".format(DCOS), check=True)
    target_dir = os.path.abspath(target_dir)

    _, out, err = run_cmd("{} marathon app show {}".format(DCOS, app_id))
    if len(out) == 0:
        log.error("Empty output detected")
        return

    app = json.loads(out, encoding=encoding)
    os.makedirs(target_dir, exist_ok=True)
    if len(os.listdir(target_dir)) != 0:
        log.fatal('Provided directory "{}" is not empty. Use an empty directory to prevent data corruption.'.format(target_dir))
    with open(os.path.join(target_dir, MARATHON_JSON), "w+") as f:
        f.write(out)
    DCOS_PACKAGE_NAME = app["labels"]["DCOS_PACKAGE_NAME"]
    if DCOS_PACKAGE_NAME != "cassandra":
        log.error('Cannot migrate "{}" package. Supported package is "cassandra"'.format(DCOS_PACKAGE_NAME))
        return
    DCOS_PACKAGE_VERSION = app["labels"]["DCOS_PACKAGE_VERSION"]
    if DCOS_PACKAGE_VERSION not in versions:
        log.error('Cannot migrate "{}" package : version "{}" not yet supported. Supported versions are {}'.format(
            DCOS_PACKAGE_NAME, DCOS_PACKAGE_VERSION, versions))
        return

    if len(app["tasks"]) == 0:
        log.error("No Task Found")
        return
    
    tasks_envs = _fetch_tasks_envs(app_id, int(app["env"]["NODES"]))
    app_envs = _sanitize_and_merge_envs(app["env"], tasks_envs)

    with open(os.path.join(target_dir, CASSANDRA_ENV_JSON), "w+") as f:
        json.dump(app_envs, f)
    
    return DCOS_PACKAGE_VERSION


# def download_task_data(cassandra_ver: str, app_id: str, target_dir: str) -> str:
#    task_name = app_id.lstrip('/').replace('/', '.') + "__node-0-server__"
#    for conf_file in CONFIG_FILES:
#        log.info("Downloading config file: {}".format(conf_file))
#        _, out, err = run_cmd("{} task exec {} bash -c 'cat apache-cassandra-{}/conf/{}'".format(DCOS, task_name, cassandra_ver, conf_file))
#        with open(os.path.join(target_dir, conf_file), "w+") as f:
#            f.write(out)
