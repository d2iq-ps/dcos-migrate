import argparse
from typing import Dict, Any


class Arg(object):
    """docstring for Arg."""

    def __init__(self,
                 name: str,
                 plugin_name=None,
                 action='store',
                 nargs=None,
                 epilog='',
                 default=None,
                 type=None,
                 choices=None,
                 required=False,
                 help='',
                 metavar=None):
        super(Arg, self).__init__()
        self._name = name
        self._plugin_name = plugin_name
        self._action = action
        self._nargs = nargs
        self._default = default
        self._type = type
        self._choices = choices
        self._required = required
        self._help = help
        self._metavar = metavar

    @ property
    def plugin_name(self) -> str:
        return self._plugin_name

    @ property
    def name(self) -> str:
        return self._name

    @property
    def arg(self) -> str:
        return "-".join(filter(None, [self.plugin_name, self.name]))

    @property
    def attr_arg(self) -> str:
        return self.arg.replace("-", "_")

    @ property
    def arg_name(self) -> str:
        return "--{}".format(self.arg)

    def add_argument(self, parser: argparse.ArgumentParser):
        parser.add_argument(self.arg_name, action=self._action,
                            nargs=self._nargs, default=self._default,
                            type=self._type, choices=self._choices,
                            required=self._required, help=self._help,
                            metavar=self._metavar)

    def get_result(self, namespace: argparse.Namespace) -> Any:
        return getattr(namespace, self.attr_arg)


class BoolArg(Arg):
    """docstring for BoolArg."""

    def __init__(self, name: str, **kwargs: Any):
        super(BoolArg, self).__init__(name, **kwargs)

    def add_argument(self, parser: argparse.ArgumentParser):
        noarg = self.arg_name.replace("--", "--no-", 1)
        parser.add_argument(noarg, action='store_false',
                            default=self._default,
                            required=self._required,
                            help=self._help, dest=self.attr_arg)
        parser.add_argument(self.arg_name, action='store_true',
                            default=self._default,
                            required=self._required,
                            help=self._help, dest=self.attr_arg)


class DictArg(Arg):
    """docstring for BoolAr g."""

    def __init__(self, name: str, **kwargs: Any):
        super(DictArg, self).__init__(name, **kwargs)

        self._nargs = '*'
        if not self._metavar:
            self._metavar = "KEY=VALUE"

    def get_result(self, namespace: argparse.Namespace) -> Dict[str, Any]:
        res = {}
        attr = getattr(namespace, self.attr_arg)
        for a in attr:
            aplit = a.split("=")
            res[aplit[0]] = "=".join(aplit[1:])

        return res


class ArgParse(object):
    """docstring for ArgParse."""

    def __init__(self, args: list,
                 prog: str = 'dcos_migrate',
                 parser: argparse.ArgumentParser = None,
                 usage: str = '',
                 epilog: str = ''):
        super(ArgParse, self).__init__()
        self.args = args
        self._parser = parser
        if not parser:
            self._parser = argparse.ArgumentParser(
                prog=prog, usage=usage, epilog=epilog,
                formatter_class=argparse.ArgumentDefaultsHelpFormatter)

        self.add_args()

    @property
    def parser(self) -> argparse.ArgumentParser:
        return self._parser

    def add_args(self) -> None:
        for a in self.args:
            a.add_argument(self._parser)

    def parse_args(self, args: list) -> Dict[str, Any]:
        parsed_args = self.parser.parse_args(args)[0]

        options: Dict[str, Any] = {}

        for a in self.args:
            pname = "global"
            if a.plugin_name:
                pname = a.plugin_name

            if pname not in options:
                options[pname] = {}

            res = a.get_result(parsed_args)
            if res:
                options[pname][a.name] = res

        return options
