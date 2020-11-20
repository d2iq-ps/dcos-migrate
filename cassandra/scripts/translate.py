import os
import json
import logging as log


RACK_TOPOLOGY_TEMPLATE = """
      - rack: {}
        rackLabelValue: {}"""

NODE_TOPOLOGY_TEMPLATE = """
  - datacenter: {}
    datacenterLabels:
      failure-domain.beta.kubernetes.io/region: {}
    nodes: {}
    rackLabelKey: failure-domain.beta.kubernetes.io/zone
    racks: {}"""

OPTIONAL_ENVS = [
    "NODE_TOPOLOGY",
    "SECURE_JMX_RMI_PORT",
    "SECURITY_TRANSPORT_ENCRYPTION_ENABLED",
    "SECURITY_TRANSPORT_ENCRYPTION_ALLOW_PLAINTEXT",
    "AUTHENTICATION_CUSTOM_YAML_BLOCK"
]


def translate_mesos_to_k8s(src_file: str, target_file: str) -> bool:
    log.info(f'Using "{src_file}" file to migrate to kubernetes configuration at "{target_file}"')

    tmpl_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../resources/params.yml.tmpl")

    if not os.path.exists(src_file):
        log.error("Mesos configuration file {} does not exists!".format(src_file))
        return False
    
    with open(src_file, "r") as f:
        src_envs = json.load(f)
    
    if not os.path.exists(tmpl_file):
        log.fatal("Missing Template File {}".format(tmpl_file))
        return False
    
    with open(tmpl_file, "r") as f:
        tmpl_lines = f.readlines()
    
    # Convert Disk Size from MB to GiB
    src_envs["CASSANDRA_DISK_GB"] = str(int(src_envs["CASSANDRA_DISK_MB"])/1024)

    # Convert Cassandra Rack-awareness to K8s Cassandra Node Topology
    if src_envs["PLACEMENT_REFERENCED_ZONE"] == "true":
        racks = ""
        for node in range(int(src_envs["NODES"])):
            racks += RACK_TOPOLOGY_TEMPLATE.format("rack" + str(node+1), src_envs['ZONE'][node])

        src_envs["NODE_TOPOLOGY"] = NODE_TOPOLOGY_TEMPLATE.format(
            src_envs["CASSANDRA_LOCATION_DATA_CENTER"],
            src_envs["REGION"], src_envs["NODES"], racks)
    
    with open(target_file, "w") as f:
        for tmpl in tmpl_lines:
            tmpl_key, tmpl_value = tmpl.split(':')
            tmpl_value = tmpl_value.strip()
            if tmpl_value in src_envs and len(src_envs[tmpl_value]) > 0:
                f.write(tmpl_key + ": " + src_envs[tmpl_value] + '\n')
    return True
