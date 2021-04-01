import argparse
import logging as log
import sys

import backup
import translate
import migrate as mig


def download(args):
    log.info("Downloading DC/OS package with app id {} of version {} into target directory {}".format(
        args.app_id, args.app_version, args.target_dir))
    backup.download_dcos_package(args.app_id, args.target_dir, args.app_version)


def install(args):
    log.info("Translating Mesos configurations to K8s configurations")
    is_ok = translate.translate_mesos_to_k8s(args.config_file, args.target_file)
    if is_ok:
        # Print installation instructions for zookeeper
        translate.print_instructions_zk(
            args.namespace,
            "zookeeper-instance",
            args.target_file,
            args.operator_version,
        )
        # Print installation instructions for kafka
        translate.print_instructions_kafka(args.namespace, args.instance, args.target_file, args.operator_version)


def migrate(args):

    # Print migration instructions for DC/OS Kafka to KUDO Kafka
    mig.print_migration_instructions(args.namespace, args.instance, args.dcos_bootstrap_servers)


def main():
    log.basicConfig(
        level=log.INFO,
        format="[%(asctime)s] %(levelname)5s {%(filename)s:%(lineno)d} - %(message)s",
    )

    class ShutdownHandler(log.Handler):
        def emit(self, record):
            log.shutdown()
            sys.exit(1)

    log.getLogger().addHandler(ShutdownHandler(level=50))

    # Dummy parent parser to share common global level args
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-t",
        "--target-dir",
        type=str,
        default="./kafka_home",
        help="Folder to hold configuration of running DC/OS Kafka service (defaults to ./kafka_home)",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="0.0.1-dev")
    subparsers = parser.add_subparsers(help="sub-commands available")

    # Step 1 : Backup the DC/OS Kafka tasks data
    backup_cmd = subparsers.add_parser(
        "backup",
        help="Backup the DC/OS package configurations and data",
        parents=[parent_parser],
    )
    backup_cmd.add_argument("--app-id", type=str, default="kafka", help="Service Name (defaults to kafka)")
    backup_cmd.add_argument(
        "--only-conf",
        type=bool,
        default=True,
        help="Set True if only service configuration is required, no data backup (defaults to true)",
    )
    backup_cmd.add_argument(
        "--app-version",
        type=str,
        default="2.5.1-1.3.3",
        help="Service Version (defaults to 2.5.1-1.3.3)",
    )
    backup_cmd.set_defaults(func=download)

    # Step 2 : Migrate the configs from DC/OS Kafka format to KUDO Kafka format and print install instructions
    install_cmd = subparsers.add_parser(
        "install",
        help="Translate the DC/OS based configs to KUDO based configs and print install instructions.",
    )
    install_cmd.add_argument(
        "-c",
        "--config-file",
        type=str,
        default="./kafka_home/kafka_env.json",
        help="Path of the kafka env file generated by backup command. (defaults to ./kafka_home/kafka_env.json)",
    )
    install_cmd.add_argument(
        "-t",
        "--target-file",
        type=str,
        default="./kafka_home/params.yml",
        help="Path of the target params file (defaults to ./kafka_home/params.yml)",
    )
    install_cmd.add_argument(
        "--namespace",
        type=str,
        default="default",
        help="Namespace of the kafka pods (defaults to default)",
    )
    install_cmd.add_argument(
        "--instance",
        type=str,
        default="kafka-instance",
        help="Name of the KUDO Kafka installation (defaults to kafka-instance)",
    )
    install_cmd.add_argument(
        "--operator-version",
        type=str,
        default="1.3.3",
        help="Kudo Kafka version (defaults to 1.3.3)",
    )
    install_cmd.set_defaults(func=install)

    # Step 3 : Migrate the schema and data from DC/OS Kafka to KUDO Kafka
    migrate_cmd = subparsers.add_parser(
        "migrate",
        help="Restore the Schema and Data from the backup of DC/OS Kafka to KUDO Kafka",
    )
    migrate_cmd.add_argument(
        "--namespace",
        type=str,
        default="default",
        help="Namespace of the kafka pods (defaults to default)",
    )
    migrate_cmd.add_argument(
        "--instance",
        type=str,
        default="kafka-instance",
        help="Name of the Kafka Kudo installation (defaults to kafka-instance)",
    )
    migrate_cmd.add_argument(
        "--dcos-bootstrap-servers",
        type=str,
        required=True,
        default="",
        help="Externally exposed DC/OS Kafka bootstrap servers.",
    )
    migrate_cmd.set_defaults(func=migrate)

    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
