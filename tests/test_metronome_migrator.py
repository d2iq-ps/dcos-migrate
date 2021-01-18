from dcos_migrate.plugins.metronome import MetronomeMigrator
from dcos_migrate.system import ManifestList, Manifest
from kubernetes.client.models import V1ConfigMap, V1ObjectMeta
from base64 import b64encode
import datetime
import json


def create_manifest_list_cluster() -> ManifestList:
    clusterID = "test-1234-test-test"
    ml = ManifestList()
    metadata = V1ObjectMeta(
        name="dcos-{}".format(clusterID))
    metadata.annotations = {
        "migration.dcos.d2iq.com/cluster-id": clusterID,
        "migration.dcos.d2iq.com/cluster-name": "testcluster",
        "migration.dcos.d2iq.com/backup-date": str(datetime.date.today()),
    }
    cfgmap = V1ConfigMap(metadata=metadata)
    # models do not set defaults -.-
    cfgmap.kind = "ConfigMap"
    cfgmap.api_version = "v1"
    cfgmap.data = {
        'MESOS_MASTER_STATE_SUMMARY_BASE64': b64encode(json.dumps({"foo": "bar"}).encode('ascii'))
    }

    manifest = Manifest(pluginName="cluster",
                        manifestName="dcos-cluster")
    manifest.append(cfgmap)

    ml.append(manifest)

    return ml


def test_simple():
    with open('tests/examples/simpleJob.json') as json_file:
        data = json.load(json_file)

        ml = create_manifest_list_cluster()

        m = MetronomeMigrator(object=data, manifest_list=ml)

        mres = m.migrate()

        assert mres is not None
        assert m.manifest[0].metadata.name == 'hello-world'
        for k, v in data['labels'].items():
            assert m.manifest[0].metadata.annotations['migration.dcos.d2iq.com/label/{k}'.format(
                k=k)] == v
        assert m.manifest[0].metadata.annotations['migration.dcos.d2iq.com/description'] == data['description']

        assert m.manifest[0].spec.job_template.spec.template.containers[0].resources.limits is not None
        assert m.manifest[0].spec.job_template.spec.template.containers[0].resources.limits["cpu"] == data['run']['cpus']
