# Jenkins migration tool

This guide walks through the various files and their role in performing a successful migration of Jenkins on DC/OS to Jenkins on Konvoy.

## Prerequisites

- `python3` installed in the environment
- DC/OS CLI `dcos` setup to talk to a DC/OS Cluster
- Kubernetes CLI `kubectl` setup to talk to a konvoy cluster
- Basic knowledge of kubernetes, charts and Jenkins.
- Script is tested to work in Linux based environments.

## Commands

Python file located at `scripts/main.py` is the main entrypoint for the tooling used to migrate jenkins. The help menu describes the steps involved in migration:

```
➜ python3 ./jenkins/scripts/main.py --help
usage: main.py [-h] [--version] {backup,install,migrate} ...

positional arguments:
  {backup,install,migrate}
                        sub-commands available
    backup              Backup the DC/OS package data
    install             Translate the MesosCloud based config.xml to
                        KubernetesCloud based config.xml and print install
                        instructions
    migrate             Perform various operations on jobs

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
``` 

At a higher level, migration can be seen as three steps:

1. Backup the DC/OS Jenkins configuration, app definition, jobs locally.
2. Install Jenkins on Konvoy by translating the above downloaded configuration and adding other customization
3. Update the Jobs downloaded from Jenkins on DC/OS and copy over to Jenkins on Konvoy.

These steps are explained in following steps:

### `backup`

By providing a marathon app-id (defaults to `/jenkins`), all the configuration and jobs related data can be downloaded to local file system.

```
➜ python3 ./jenkins/scripts/main.py backup --help
usage: main.py backup [-h] [-t TARGET_DIR] [--app-id APP_ID] [--retain-builds]
                      [--retain-next-build-number]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --app-id APP_ID       Marathon application ID
  --retain-builds       Set to retain previous builds data
  --retain-next-build-number
                        Set to retain nextBuildNumber counter
```

`TARGET_DIR` defaults to `$(pwd)/jenkins_home` and the tooling removes the builds directory by default.

### `install`

```
➜ python3 ./jenkins/scripts/main.py install --help
usage: main.py install [-h] [-c CONFIG_FILE] [-t TARGET_FILE] [-p]
                       [--namespace NAMESPACE] [--fullname FULLNAME]
                       [--uri-prefix URI_PREFIX]

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        path of the config.xml file
  -t TARGET_FILE, --target-file TARGET_FILE
                        path of the target config.xml file
  -p, --print           Print the transformed cloud config element from
                        config.xml
  --namespace NAMESPACE
                        Namespace of the jenkins pod (defaults to jenkins)
  --fullname FULLNAME   Name of the jenkins helm installation (defaults to
                        jenkins)
  --uri-prefix URI_PREFIX
                        Uri prefix for jenkins chart (defaults to /jenkins)
```                        

The `install` command generates a `TARGET_FILE` (that defaults to `$(pwd)/k8s.config.xml` ) and prints instructions on how to use it to install in Jenkins on Konvoy. Other parameters such as `namespace` and `fullname` have sensible defaults in accordance with the upstream helm chart but can be customized.

### `migrate`

```
➜ python3 ./jenkins/scripts/main.py migrate --help
usage: main.py migrate [-h] {update,copy} ...

positional arguments:
  {update,copy}  Perform various operations on jobs
    update       Update the jobs by removing the mesos related build wrappers
                 and optionally disable the jobs
    copy         Copy the jobs from local file system to Jenkins master node

optional arguments:
  -h, --help     show this help message and exit
```

The `migrate` command has two subcommands `update` and `copy` which update the jobs and then copies them to Jenkins on Kubernetes.

#### `update`

```
➜ python3 ./jenkins/scripts/main.py migrate update --help
usage: main.py migrate update [-h] [-t TARGET_DIR] [--path PATH]
                              [--disable-jobs]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --path PATH           URL of the job or folder. This is the part after
                        http://<cluster-url>/service/<service-name>/<job-path-
                        here>
  --disable-jobs        If set, the job config.xml is updated to disable the
                        job by setting "<disabled>true</disabled>"
```

This command updates the jobs by optionally disabling the jobs. This is useful during migration of multiple jobs and the user wants to enable them manually one by one. This command also performs some other cleanup on the job definitions (such as cleaning up MesosSingleUseSlave flag which does not make any sense in the Jenkins on Konvoy)

#### `copy`

```
➜ python3 ./jenkins/scripts/main.py migrate copy --help
usage: main.py migrate copy [-h] [-t TARGET_DIR] [--path PATH]
                            [--namespace NAMESPACE]
                            [--release-name RELEASE_NAME] [--dry-run]

optional arguments:
  -h, --help            show this help message and exit
  -t TARGET_DIR, --target-dir TARGET_DIR
                        points to jenkins_home folder with a valid "jobs"
                        folder
  --path PATH           URL of the job or folder. This is the part after
                        http://<cluster-url>/service/<service-name>/<job-path-
                        here>
  --namespace NAMESPACE
                        Namespace of the jenkins installation (defaults to
                        jenkins)
  --release-name RELEASE_NAME
                        Helm release name (defaults to jenkins)
  --dry-run             Setting this flag would just print the commands
                        without executing them
```

This command copies the job from user file system to the Jenkins master node filesystem.
