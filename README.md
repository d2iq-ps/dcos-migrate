# dcos-migration
Tools for migrating workloads and other resources from DCOS to DKP

## Running

See the `README.md` file in each subdirectory for how to use each tool.

### Docker 

To set up an environment to run those tools, you might want to use something like the following to start an interactive shell.

```
docker build -t dcos-migrate .
docker run -it --rm -v "$(echo $PWD):/work" dcos-migrate
```

## Testing

Run `make test` to run all tests.

Integration tests require a DC/OS installer file in `tests/dcos_generate_config.ee.sh` and a license file in `tests/license.txt`.
