from ..lib import app_translator
import os
import sys

def test_sleep():
    container_defaults = app_translator.Settings(
        app_translator.ContainerDefaults(
            image="busybox",
            working_dir=".",
        ),
        imported_k8s_secret_name = "dummy"
    )

    hello_app = app_translator.load("test/resources/hello.json")[0]
    result, warnings = app_translator.translate_app(hello_app, container_defaults)

    assert(result['kind'] == "Deployment")
    assert(result['metadata']['name'] == "sleep")
    assert(result['metadata']['labels'] == {'app': 'sleep'})
    assert(result['spec']['replicas'] == 10)
    container = result['spec']['template']['spec']['containers'][0]

    assert(container['command'] == ['/bin/sh', '-c', 'sleep 3600'])
    assert(container['image'] == 'busybox')
    assert(container['resources'] == {'requests': {'cpu': 0.01, 'memory': '64Mi'}})
    assert(container['name'] == 'main')
