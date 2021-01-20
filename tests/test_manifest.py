from kubernetes.client.models import V1beta1CronJob, V1Secret
from dcos_migrate.system import Manifest


def test_manifest_deserialize_get_model_name():
    assert "V1Job" == Manifest.genModelName("v1", "Job")
    assert "V1beta1CronJob" == Manifest.genModelName(
        "batch/v1beta1", "CronJob")


def test_manifest_deserialize_multidoc_model():
    with open('tests/examples/multiDocManifest.yaml') as yaml_file:
        m = Manifest(pluginName='metronome', manifestName='test')
        m.deserialize(yaml_file)

        assert len(m) == 2
        assert isinstance(m[0], V1beta1CronJob)
        assert isinstance(m[1], V1Secret)

        assert m[0].metadata.name == "hello-world"
