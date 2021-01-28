import json
import logging
import os.path


import dcos_migrate.utils as utils

from collections import namedtuple
from typing import List, Mapping, NamedTuple, Optional, Union

import dcos_migrate.utils as utils

from .app_secrets import AppSecretMapping

from .common import pod_spec_update, main_container, try_oneline_dump
from .common import InvalidAppDefinition, AdditionalFlagNeeded

from .mapping_utils import Translated, apply_mapping
from .mapping_utils import ListExtension, finalize_unmerged_list_extensions
from .volumes import translate_volumes


class ContainerDefaults(NamedTuple):
    image: Optional[str]
    working_dir: Optional[str]


class Settings(NamedTuple):
    container_defaults: ContainerDefaults
    app_secret_mapping: AppSecretMapping


log = logging.getLogger(__name__) #pylint: disable=invalid-name


def translate_container_command(fields):
    # Marathon either supports args (with a container specified), or cmd. Not both.
    # Marathon does not have a way to override the entrypoint for a container.
    # https://github.com/mesosphere/marathon/blob/b5023142bdf8bd75f187df897ab4d70f4fe03b24/src/test/scala/mesosphere/marathon/api/v2/json/AppDefinitionTest.scala#L131-L132
    if 'cmd' in fields:
        cmdline = ["/bin/sh", "-c", fields['cmd']]

        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'command': cmdline}))

    if 'args' in fields:
        # FIXME: Sanitize the cmdline against DCOS-specific stuff!
        return Translated(update=main_container({'args': fields['args']}))

    return Translated()


RESOURCE_TRANSLATION = {
    'cpus': lambda cpus: ('cpu', cpus),
    'mem': lambda mem: ('memory', '{}Mi'.format(mem)),
    'disk': lambda disk: ('ephemeral-storage', '{}Mi'.format(disk)),
    'gpus': lambda gpus: ('nvidia.com/gpu', '{}'.format(gpus)),
}


def translate_resources(fields):
    app_requests = fields.copy()
    app_limits = app_requests.pop('resourceLimits', {})

    def iter_requests():
        for key, value in app_requests.items():
            if value != 0:
                yield RESOURCE_TRANSLATION[key](value)

    def iter_limits():
        for key in app_requests.keys() | app_limits.keys():
            if key in app_limits:
                limit = app_limits[key]
                if limit != "unlimited":
                    yield RESOURCE_TRANSLATION[key](limit)
            else:
                limit_from_requests = app_requests[key]
                if limit_from_requests != 0:
                    yield RESOURCE_TRANSLATION[key](limit_from_requests)

    resources = {'requests': dict(iter_requests()), 'limits': dict(iter_limits())}
    update = main_container({'resources': {k: v for k, v in resources.items() if v}})
    return Translated(update)


def translate_env(
        env: Mapping[str, Union[dict, str]],
        app_secret_mapping: AppSecretMapping,
    ):
    translated: List[dict] = []
    not_translated = {}

    # FIXME: Sanitize against DCOS-specific stuff.
    for var, value in env.items():
        if isinstance(value, str):
            translated.append({"name": var, "value": value})
            continue

        if value.keys() != {'secret'}:
            not_translated[var] = value
            continue
        ref = app_secret_mapping.get_reference(value['secret'])

        translated.append({
            "name": var,
            "valueFrom": {
                'secretKeyRef': {
                    'name': ref.secret_name,
                    'key': ref.key,
                },
            },
        })

    return Translated(
        update=main_container({'env': translated}),
        warnings=["could not translate the following variables:\n" + json.dumps(not_translated)]\
            if not_translated else [],
    )


def translate_multitenancy(fields):
    # FIXME: Translate groups and roles.

    # TODO(asekretenko): Consider adding prefix or another label to show that
    # this has been generated by the DCOS migration script.


    app_id = utils.dnsify(fields['id'])
    selector_labels = {'app': app_id}
    return Translated(update={
        'metadata': {'name': app_id, 'labels': {'app': app_id}},
        'spec': {
            'selector': {'matchLabels': selector_labels},
            'template': {'metadata': {'labels': selector_labels}}}
    })


def get_network_probe_builder(get_port_by_index):
    def build_network_probe(fields):
        protocol = fields.pop('protocol')
        port = fields.pop('port', None)
        index = fields.pop('portIndex', 0)
        path = fields.pop('path', '/')

        warnings = [] if not fields else \
            ['Non-translatable health check fields: {}'.format(try_oneline_dump(fields))]

        use_host_port = protocol in ['TCP', 'HTTP', 'HTTPS']
        port = get_port_by_index(index, use_host_port) if port is None else port

        # TODO (asekretenko): The app translator should choose a value for each port==0
        # once, and ensure that the same value is used for the same port
        # by different parts of the generated manifest.
        if port == 0:
            warnings.append(
                "The app is using port 0 (auto-assigned by Marathon) in a health check."
                " Please make sure that the generated K8s probe is using a correct port number.")

        if protocol in ['MESOS_TCP', 'TCP']:
            return Translated({'tcpSocket': {'port': port}}, warnings)

        if protocol in ['MESOS_HTTP', 'HTTP', 'MESOS_HTTPS', 'HTTPS']:
            scheme = 'HTTPS' if protocol in ['MESOS_HTTPS', 'HTTPS'] else 'HTTP'
            return Translated({'httpGet': {'port': port, 'scheme': scheme, 'path': path}}, warnings)

        raise InvalidAppDefinition("Invalid `protocol` in a health check: {}".format(protocol))

    return build_network_probe


def rename(name):
    return lambda _: Translated({name: _})


def health_check_to_probe(check, get_port_by_index, error_location):
    flattened_check = flatten(check)

    mapping = {
        'gracePeriodSeconds': rename('initialDelaySeconds'),
        'intervalSeconds': rename('periodSeconds'),
        'maxConsecutiveFailures': rename('failureThreshold'),
        'timeoutSeconds': rename('timeoutSeconds'),
        'delaySeconds': skip_if_equals(15),
        'ipProtocol': skip_if_equals("IPv4"),
        'ignoreHttp1xx': skip_if_equals(False),
        'protocol': skip_quietly,
    }

    if check['protocol'] == 'COMMAND':
        mapping['command.value'] = \
            lambda command: Translated({'command': ["/bin/sh", "-c", command]})
    else:
        mapping[('protocol', 'port', 'portIndex', 'path')] = \
            get_network_probe_builder(get_port_by_index)

    probe, warnings = apply_mapping(mapping, flattened_check, error_location)
    probe.setdefault('initialDelaySeconds', 300)
    probe.setdefault('periodSeconds', 60)
    probe.setdefault('timeoutSeconds', 20)

    if check['protocol'] in ['TCP', 'HTTP', 'HTTPS']:
        warnings.append(
            "The app is using a deprecated Marathon-level health check:\n" +
            try_oneline_dump(check) +
            "\nPlease check that the K8s probe is using the correct port.")

    return probe, warnings


def translate_health_checks(fields, error_location):
    def get_port_by_index(index, use_host_port=False):
        port_mappings = fields.get('container', {}).get('portMappings')
        port_definitions = fields.get('portDefinitions')
        if port_mappings is None == port_definitions is None:
            raise InvalidAppDefinition(
                "Cannot get port by index as both portDefinitions"
                " and container.portMappings are set")

        if port_definitions is None:
            port_list, name = port_mappings, 'container.portMappings'
            key = 'hostPort' if use_host_port else 'containerPort'
        else:
            port_list, name = port_definitions, 'portDefinitions'
            key = 'port'

        try:
            port_data = port_list[index]
        except IndexError:
            raise InvalidAppDefinition(
                "Port index {} used in a health check is missing from `{}`".format(index, name))

        try:
            return port_data[key]
        except KeyError:
            raise InvalidAppDefinition(
                "`{}` contain no '{}' at index {} used in health check".format(name, key, index))

    health_checks = fields.get('healthChecks', [])
    if len(health_checks) < 1:
        return Translated()

    liveness_probe, warnings = health_check_to_probe(
        health_checks[0], get_port_by_index, error_location)

    excess_health_checks = health_checks[1:]
    if excess_health_checks:
        warnings.append(
            'Only the first app health check is converted into a liveness probe.\n'
            'Dropped health checks:\n{}'.format(
                try_oneline_dump(excess_health_checks)))

    return Translated(
        update=main_container({'livenessProbe': liveness_probe}),
        warnings=warnings
    )


def skip_quietly(_):
    return Translated()


def not_translatable(_):
    return Translated(warnings=["field not translatable"])



def skip_if_equals(default):
    if not default:
        return lambda value: Translated(warnings=[] if not value else [
            'Cannot translate non-empty value\n{}'.format(try_oneline_dump(value))])

    return lambda value: Translated(warnings=[] if value == default else [
        'A value\n{}\ndifferent from the default\n{}\ncannot be translated.'.format(
            try_oneline_dump(value),
            try_oneline_dump(default)
        )])


def generate_root_mapping(
        container_defaults: ContainerDefaults,
        app_secrets_mapping: AppSecretMapping,
        error_location: str,
    ):

    return {
        ('args', 'cmd'): translate_container_command,

        ('backoffFactor', 'backoffSeconds'):
            skip_if_equals({'backoffFactor':1.0, 'backoffSeconds': 1.0}),

        'constraints': skip_if_equals([]),

        ('container',):
            get_container_translator(container_defaults, app_secrets_mapping, error_location),

        ('cpus', 'mem', 'disk', 'gpus', 'resourceLimits'): translate_resources,

        'dependencies': skip_if_equals([]),

        'deployments': skip_quietly,

        'env': lambda env: translate_env(env, app_secrets_mapping),

        'executor': skip_if_equals(""),

        'fetch': lambda fetches: translate_fetch(fetches, container_defaults, error_location),

        ('healthChecks', 'container', 'portDefinitions'):
            lambda fields: translate_health_checks(fields, error_location),

        ('acceptedResourceRoles', 'id', 'role'): translate_multitenancy,

        'instances': lambda n: Translated(update={'spec': {'replicas': n}}),

        'killSelection': skip_if_equals("YOUNGEST_FIRST"),

        'labels': skip_if_equals({}),  # translate_labels,

        'maxLaunchDelaySeconds': skip_if_equals(300),

        ('networks', 'portDefinitions', 'requirePorts'):
            skip_if_equals({}),  # translate_networking,

        'residency': skip_if_equals({}),

        # 'secrets' do not map to anything and are used only in combination with other fields.
        'secrets': skip_quietly,

        'taskKillGracePeriodSeconds': not_translatable,

        'tasksHealthy': skip_quietly,
        'tasksRunning': skip_quietly,
        'tasksStaged': skip_quietly,
        'tasksUnhealthy': skip_quietly,

        'unreachableStrategy': not_translatable,

        'upgradeStrategy': not_translatable,

        'user': skip_if_equals("nobody"),

        'version': skip_quietly,
        'versionInfo': skip_quietly,
    }


EXTRACT_COMMAND = dict(
    [('.zip', 'gunzip')] +\
    [(ext, 'tar -xf') for ext in ['.tgz', '.tar.gz', '.tbz2', '.tar.bz2', '.txz', '.tar.xz']]
)


def generate_fetch_command(uri: str, allow_extract: bool, executable: bool):
    _, _, filename = uri.rpartition('/') # NOTE: The path separator is always '/', even on Windows.
    _, ext = os.path.splitext(filename)

    postprocess = 'chmod a+x' if executable else \
        (EXTRACT_COMMAND.get(ext, '') if allow_extract else '')

    fmt = '( wget -O "{fn}" "{uri}" && {postprocess} "{fn}" )' if postprocess else\
          '( wget -O "{fn}" "{uri}")'

    return fmt.format(fn=filename, uri=uri, postprocess=postprocess)


def translate_fetch(fetches, defaults: ContainerDefaults, error_location):
    if not defaults.working_dir:
        raise AdditionalFlagNeeded(
            '{} is using "fetch"; please specify non-empty'
            ' `--container-working-dir` and run again'.format(error_location)
        )

    warnings = ['This app uses "fetch"; consider using a container image instead.']

    def iter_command():
        yield 'set -x'
        yield 'set -e'
        yield 'FETCH_PID_ARRAY=()'

        for fetch in fetches:
            fetch = fetch.copy()
            uri = fetch.pop('uri')
            cache = fetch.pop('cache', False)
            extract = fetch.pop('extract', True)
            executable = fetch.pop('executable', False)
            if fetch:
                warnings.append('Unknown fields in "fetch": {}', json.dumps(fetch))

            if cache:
                warnings.append(
                    '`cache=true` requested for fetching "{}" has been ignored'.format(uri))

            if uri.startswith('file://'):
                warnings.append('Fetching a local file {} is not portable'.format(uri))

            yield generate_fetch_command(uri, extract, executable) + ' & FETCH_PID_ARRAY+=("$!")'

        yield 'for pid in ${FETCH_PID_ARRAY[@]}; do wait $pid || exit $?; done'

    return Translated(
        update=pod_spec_update({
            "initContainers": [{
                "name": "fetch",
                "image": "bash:5.0",
                "command": ['bash', '-c', '\n'.join(iter_command())],
                "volumeMounts": [{
                    "name": "fetch-artifacts",
                    "mountPath": "/fetch_artifacts"
                }],
                "workingDir": "/fetch_artifacts",
            }],
            "containers": [{
                "volumeMounts": ListExtension([{
                    "name": "fetch-artifacts",
                    "mountPath": defaults.working_dir,
                }]),
            }],
            "volumes": ListExtension([{"name": "fetch-artifacts", "emptyDir": {}}])
        }),
        warnings=warnings,
    )


def get_container_translator(
        defaults: ContainerDefaults,
        app_secret_mapping: AppSecretMapping,
        error_location: str,
    ):
    def translate_image(image_fields):
        if 'docker.image' in image_fields:
            return Translated(main_container({'image': image_fields['docker.image']}))

        if not defaults.image:
            raise AdditionalFlagNeeded(
                '{} has no image; please specify non-empty'
                ' `--default-image` and run again'.format(error_location)
            )
        container_update = {'image': defaults.image}

        # TODO (asekretenko): This sets 'workingDir' only if 'docker.image' is
        # not specified. Figure out how we want to treat a combination of
        # a 'fetch' with a non-default 'docker.image'.
        if defaults.working_dir:
            container_update['workingDir'] = defaults.working_dir
        return Translated(main_container(container_update))

    def translate_container(fields):
        update, warnings = apply_mapping(
            mapping={
                "docker.forcePullImage":
                    lambda _: Translated(main_container({
                        'imagePullPolicy': "Always" if _ else "IfNotPresent"})),

                ("docker.image", ): translate_image,
                "docker.parameters": skip_if_equals([]),
                "docker.privileged": skip_if_equals(False),
                "docker.pullConfig.secret":
                    lambda dcos_name: Translated(pod_spec_update({'imagePullSecrets': [{
                        'name': app_secret_mapping.get_image_pull_secret_name(dcos_name)}]})),

                "linuxInfo": skip_if_equals({}),
                "portMappings": skip_if_equals({}),
                "volumes": lambda _: translate_volumes(_, app_secret_mapping),
                "type": skip_quietly,
            },
            data=flatten(fields.get('container', {})),
            error_location=error_location + ", container"
        )

        return Translated(update, warnings)

    return translate_container


def flatten(dictionary):
    """
    >>> flatten({'foo':{'bar':{'baz': 0}, 'deadbeef': 1}, '42': 3})
    {'foo.bar.baz': 0, 'foo.deadbeef': 1, '42': 3}
    """
    def iterate(data, prefix):
        for key, value in data.items():
            prefixed_key = prefix + key
            if isinstance(value, dict):
                for prefixed_subkey, val in iterate(value, prefixed_key + '.'):
                    yield prefixed_subkey, val
            else:
                yield prefixed_key, value

    return dict(iterate(dictionary, ""))


class InvalidInput(Exception):
    pass

def load(path: str):
    with open(path) as input_file:
        apps = json.load(input_file)

    if isinstance(apps, list):
        return apps

    if not isinstance(apps, dict):
        raise InvalidInput(
            "The top level of {} is neither a dict nor a list".format(path))

    if 'apps' in apps:
        return apps['apps']

    log.warning("Interpreting %s as containing a single app", path)
    return [apps]



def translate_app(app: dict, settings: Settings):
    error_location = "app " + app.get('id', '(NO ID)')

    mapping = generate_root_mapping(
        settings.container_defaults,
        settings.app_secret_mapping,
        error_location
    )

    try:
        definition, warnings = apply_mapping(mapping, app, error_location)
    except InvalidAppDefinition as err:
        raise InvalidAppDefinition('{} at {}'.format(err, error_location))

    definition = finalize_unmerged_list_extensions(definition)

    definition.update({'apiVersion': 'apps/v1', 'kind': 'Deployment'})
    return definition, warnings
