# dcos_migrate
Backup and Migrate DC/OS workloads to DKP

## Running
At the moment only a full backup and migrate run is supported:
`python ./src/dcos_migrate.py`

This will create a sub-folder `dcos-migrate` in the current working directory. It contains a `backup` folder with a complete backup of all workloads. And a `migrate` folder.


## Run with docker
Get the latest version

```
docker pull mesosphere/dcos-migration:latest
```

### Run using your local DC/OS config

```
docker run -v"${HOME}/.dcos:/root/.dcos"  mesosphere/dcos-migration:latest

docker run -v"${HOME}/.dcos:/root/.dcos"  mesosphere/dcos-migration:latest dcos-migrate -h
```

### Run using environment variables
**WIP**
```
docker run -e"DCOS_CLUSTER_"  mesosphere/dcos-migration:latest
```

## Migrated Manifests
This tool creates manifest plugin based for different DC/OS workloads.

### cluster
Cluster manifest is not really meant to be used. Its a configmap containing DC/OS cluster properties. Its annotations being used by other plugins to annotate workloads with DC/OS related properties like `cluster-id` oder the cluster name.

### secrets
This is a 1:1 migration of DC/OS secrets for each secret we create a Manifest with a Kubernetes secret containing exactly 1 secret.

As DC/OS didn't support combining multiple secret key-value-pairs into a single Secret the result might not be best practice on K8s. You can just simply combine the `data` part of a secret and create your own one.

### metronome

### marathon


### packages

#### jenkins


### Docker

To set up an environment to run those tools, you might want to use something like the following to start an interactive shell.

```
docker build -t dcos-migrate .
docker run -it --rm -v "$(echo $PWD):/work" dcos-migrate

# e.g. run a test:
pipenv run pytest metronome/metronome_test.py
```

## Testing

Run `tox` to run all tests.
