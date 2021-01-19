from dcos_migrate.plugins.metronome import MetronomeMigrator
from dcos_migrate.system import ManifestList, Manifest
from kubernetes.client.models import V1ConfigMap, V1ObjectMeta  # type: ignore
from kubernetes.client import ApiClient  # type: ignore

from base64 import b64encode
import datetime
import json
import pytest
import yaml


def create_manifest_list_cluster() -> ManifestList:
    clusterID = "test-1234-test-test"
    ml = ManifestList()
    metadata = V1ObjectMeta(name="dcos-{}".format(clusterID))
    metadata.annotations = {
        "migration.dcos.d2iq.com/cluster-id": clusterID,
        "migration.dcos.d2iq.com/cluster-name": "testcluster",
        "migration.dcos.d2iq.com/backup-date": "2021-01-25",
    }
    cfgmap = V1ConfigMap(metadata=metadata)
    # models do not set defaults -.-
    cfgmap.kind = "ConfigMap"
    cfgmap.api_version = "v1"
    cfgmap.data = {
        "MESOS_MASTER_STATE_SUMMARY_BASE64": b64encode(
            json.dumps({"foo": "bar"}).encode("ascii")
        )
    }

    manifest = Manifest(pluginName="cluster", manifestName="dcos-cluster")
    manifest.append(cfgmap)

    ml.append(manifest)

    return ml


def snapshot_test(snapshot, source, target):
    """
    A helper to run snapshot tests. E.g:

        def test_simple(snapshot):
            snapshot_test(snapshot, "simpleJob.json", "simpleJob.yaml")

    You might want to use the following command to update your snapshots:

        tox -- --snapshot-update
    """
    snapshot.snapshot_dir = "tests/examples"
    with open(f"tests/examples/{source}") as f:
        data = json.load(f)
        ml = create_manifest_list_cluster()
        m = MetronomeMigrator(object=data, manifest_list=ml)
        manifest = m.migrate()[0]
        api = ApiClient()

        assert manifest is not None
        snapshot.assert_match(
            yaml.dump(api.sanitize_for_serialization(manifest)), target
        )


###############################################################################
#                                    TESTS                                    #
###############################################################################
def test_simple(snapshot):
    snapshot_test(snapshot, "simpleJob.json", "simpleJob.yaml")
