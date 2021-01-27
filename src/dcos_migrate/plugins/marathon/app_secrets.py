import abc
import re
from typing import Dict, Mapping, NamedTuple, Optional, Sequence

import dcos_migrate.utils as utils

from .common import InvalidAppDefinition, AdditionalFlagNeeded


class SecretReference(NamedTuple):
    secret_name: str
    key: str


class AppSecretMapping(abc.ABC):
    """
    Provides a mapping from Marathon app's internal secret names
    to name(s) and keys in the migrated DCOS secret.
    """
    @abc.abstractmethod
    def get_reference(self, app_secret_name: str) -> SecretReference:
        pass


class SecretRemapping(NamedTuple):
    """Settings for remapping keys of the monolithic DCOS secret into app-specific secrets"""
    dest_name: str
    dest_type: Optional[str]
    key_mapping: Dict[str, str]


class TrackingAppSecretMapping(AppSecretMapping):
    """
    Tracks which secrets are used by callers of `AppSecretMapping` interface
    and reports them via `get_secrets_to_remap()`.
    """
    def __init__(
        self,
        app_id: str,
        app_secrets: Mapping[str, Mapping[str, str]],
    ):
        self._app_secrets = app_secrets

        self._generic_remapping = SecretRemapping(
            dest_name="marathonsecret-{}".format(utils.dnsify(app_id)),
            dest_type=None,
            key_mapping={}
        )

    def get_reference(self, app_secret_name: str) -> SecretReference:
        try:
            dcos_name = self._app_secrets[app_secret_name]['source']
        except KeyError:
            raise InvalidAppDefinition(
                'No source specified for a secret "{}"'.format(app_secret_name))

        k8s_key = utils.dnsify(dcos_name)
        self._generic_remapping.key_mapping[k8s_key] = k8s_key
        return SecretReference(self._generic_remapping.dest_name, k8s_key)


    def get_secrets_to_remap(self) -> Sequence[SecretRemapping]:
        # TODO (asekretenko): add SecretRemapping for creating an image pull secret.
        return (self._generic_remapping, )
