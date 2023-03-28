#!/usr/bin/env python3

"""
Commandline client to upload data to a storage service and double-link the storage location with a metadata store.

Implemented for:
    Storage types:
        iRODS
    Metadata stores:
        Elabjournal
"""
import argparse
import logging
import configparser
import os
import sys
import json
import getpass
from pathlib import Path
from irods.exception import ResourceDoesNotExist
import irodsConnector.keywords as kw
from irodsConnector.manager import IrodsConnector
from utils.utils import setup_logger, get_local_size
from utils.elab_plugin import ElabPlugin

log_colors = {
    0: '\x1b[0m',    # DEFAULT (info)
    1: '\x1b[1;33m', # YEL (warn)
    2: '\x1b[1;31m', # RED (error)
    3: '\x1b[1;34m', # BLUE (success)
}

def print_error(msg):
    """
    Adds color code for error to message and calls logging.error.
    """
    logging.error("%s%s%s", log_colors[2], msg, log_colors[0])

def print_warning(msg):
    """
    Adds color code for warning to message and calls logging.warning.
    """
    logging.warning("%s%s%s", log_colors[1], msg, log_colors[0])

def print_success(msg):
    """
    Adds color code for success to message and calls logging.info.
    """
    logging.info("%s%s%s", log_colors[1], msg, log_colors[0])

def print_message(msg):
    """
    Calls logging.info.
    """
    logging.info(msg)


class iBridgesCli:                          # pylint: disable=too-many-instance-attributes
    """
    Class for up- and downloading to YODA/iRODS via the command line.
    Includes option for writing metadata to Elab Journal.
    """
    def __init__(self,                      # pylint: disable=too-many-arguments
                 config_file: str,
                 local_path: str,
                 irods_path: str,
                 irods_env: str,
                 irods_resc: str,
                 operation: str,
                 logdir: str,
                 plugins: list[dict] = None) -> None:

        self.irods_env = None
        self.irods_path = None
        self.irods_resc = None
        self.local_path = None
        self.config_file = None

        # reading optional config file
        if config_file:
            if not os.path.exists(config_file):
                self._clean_exit(f"{config_file} does not exist")

            self.config_file = os.path.expanduser(config_file)
            if not self.get_config('iRODS'):
                self._clean_exit(f"{config_file} misses iRODS section")

        # CLI parameters override config-file
        self.irods_env = irods_env or self.get_config('iRODS', 'irodsenv') \
                         or self._clean_exit("need iRODS environment file", True)
        self.irods_path = irods_path or self.get_config('iRODS', 'irodscoll') \
                          or self._clean_exit("need iRODS path", True)
        self.local_path = local_path or self.get_config('LOCAL', 'path') \
                          or self._clean_exit("need local path", True)

        self.irods_env = Path(os.path.expanduser(self.irods_env))
        self.local_path = Path(os.path.expanduser(self.local_path))
        self.irods_path = self.irods_path.rstrip("/")
        logdir = Path(logdir)

        # checking if paths actually exist
        for path in [self.irods_env, self.local_path, logdir]:
            if not path.exists():
                self._clean_exit(f"{path} does not exist")

        # reading default irods_resc from env file if not specified otherwise
        self.irods_resc = irods_resc or self.get_config('iRODS', 'irodsresc') or None
        if not self.irods_resc:
            with open(self.irods_env,'r',encoding='utf-8') as file:
                cfg = json.load(file)
                if 'default_resource_name' in cfg:
                    self.irods_resc = cfg['default_resource_name']

        if not self.irods_resc:
            self._clean_exit("need an iRODS resource", True)

        self.operation = operation
        self.plugins = self._cleanup_plugins(plugins)
        setup_logger(logdir, "iBridgesCli")
        self._run()

    @classmethod
    def _cleanup_plugins(cls, plugins):
        plugins = [x for x in plugins if 'hook' in x and 'actions' in x]
        for k, v in enumerate(plugins):
            plugins[k]['actions'] = [x for x in v['actions'] 
                                     if 'function' in x and callable(x['function']) 
                                     and 'slot' in x and x['slot'] in ['pre', 'post']]
        
        return [x for x in plugins if len(x['actions'])>0]

    def get_config(self, section: str, option: str=None):
        """
        Reads config file.
        """
        if not self.config_file:
            return False

        config = configparser.ConfigParser()
        with open(self.config_file, encoding='utf-8') as file:
            config.read_file(file)

            if section not in config.sections():
                return False

            if not option:
                return dict(config.items(section))

            if option in [x[0] for x in config.items(section)]:
                return config.get(section, option)

        return False

    @classmethod
    def from_arguments(cls, **kwargs):
        cls.parser = argparse.ArgumentParser(
            prog='python iBridgesCli.py',
            description="",
            epilog=""
            )

        default_logdir = os.path.join(str(os.getenv('HOME')), '.irods')
        default_irods_env = os.path.join(str(os.getenv('HOME')), '.irods', 'irods_environment.json')

        cls.parser.add_argument('--config', '-c',
                            type=str,
                            help='Config file')
        cls.parser.add_argument('--local_path', '-l',
                            help='Local path to download to, or upload from',
                            type=str)
        cls.parser.add_argument('--irods_path', '-i',
                            help='iRods path to upload to, or download from',
                            type=str)
        cls.parser.add_argument('--operation', '-o',
                            type=str,
                            choices=['upload', 'download'],
                            required=True)
        cls.parser.add_argument('--env', '-e', type=str,
                            help=f'iRods environment file. (example: {default_irods_env})')
        cls.parser.add_argument('--irods_resc', '-r', type=str,
                            help='iRods resource. If omitted default will be read from iRods env file.')
        cls.parser.add_argument('--logdir', type=str,
                            help=f'Directory for logfile. Default: {default_logdir}',
                            default=default_logdir)

        args = cls.parser.parse_args()

        return cls(config_file=args.config,
                   irods_env=args.env,
                   irods_resc=args.irods_resc,
                   local_path=args.local_path,
                   irods_path=args.irods_path,
                   operation=args.operation,
                   logdir=args.logdir,
                   plugins=kwargs["plugins"] if "plugins" in kwargs else None
                   )

    def _clean_exit(self, message=None, show_help=False, exit_code=1):
        if message:
            print_message(message) if exit_code==0 else print_error(message)
        if show_help:
            iBridgesCli.parser.print_help()
        if self.irods_conn:
            self.irods_conn.cleanup()
        sys.exit(exit_code)

    @classmethod
    def connect_irods(cls, irods_env):
        attempts = 0
        while True:
            secret = getpass.getpass(f'Password for {irods_env} (leave empty to use cached): ')
            try:
                irods_conn = IrodsConnector(irods_env, secret)
                _ = irods_conn.session
                break
            except Exception as exception:
                # print_error(f"AUTHENTICATION failed. {repr(exception)}")
                print_error(f"Failed to connect")
                attempts += 1
                if attempts >= 3 or input('Try again (Y/n): ').lower() == 'n':
                    return False

        return irods_conn

    def plugin_hook(func):
        def wrapper(self, **kwargs):
            pre_fs = post_fs = []
            actions = [x['actions'] for x in self.plugins if x['hook']==func.__name__]
            if actions:
                pre_fs = [x['function'] for x in actions[0] if x['slot']=='pre']
                post_fs = [x['function'] for x in actions[0] if x['slot']=='post']

            for pre_f in pre_fs:
                pre_f(calling_class=self, **kwargs)

            func(self, **kwargs)

            for post_f in post_fs:
                post_f(calling_class=self, **kwargs)

        return wrapper

    @plugin_hook
    def download(self):
        # checks if remote object exists and if it's an object or a collection
        if self.irods_conn.collection_exists(self.irods_path):
            item = self.irods_conn.get_collection(self.irods_path)
        elif self.irods_conn.dataobject_exists(self.irods_path):
            item = self.irods_conn.get_dataobject(self.irods_path)
        else:
            print_error(f'iRODS path {self.irods_path} does not exist')
            return False

        # get its size to check if there's enough space
        download_size = self.irods_conn.get_irods_size([self.irods_path])
        print_message(f"Downloading '{self.irods_path}' (approx. {round(download_size * kw.MULTIPLIER, 2)}GB)")

        # download
        self.irods_conn.download_data(src_obj=item, dst_path=self.local_path, size=download_size, force=False)

        print_success('Download complete')
        return True

    @plugin_hook
    def upload(self):
        # check if intended upload target exists
        try:
            self.irods_conn.ensure_coll(self.target_path)
            print_warning(f"Uploading to {self.target_path}")
        except Exception:
            print_error(f"Collection path invalid: {self.target_path}")
            return False

        # check if there's enough space left on the resource
        upload_size = get_local_size([self.local_path])

        # TODO: does irods_conn.get_free_space() work yet?
        # free_space = int(irods_conn.get_free_space(resc_name=irods_resc))
        free_space = None
        if free_space is not None and free_space-1000**3 < upload_size:
            print_error('Not enough space left on iRODS resource to upload.')
            return False

        self.irods_conn.upload_data(
            source=self.local_path,
            destination=self.irods_conn.get_collection(self.target_path),
            res_name=self.irods_resc,
            size=upload_size,
            force=True)

        return True

    def _run(self):
        self.irods_conn = self.connect_irods(irods_env=self.irods_env)

        if not self.irods_conn:
            self._clean_exit("Connection failed")

        if self.operation == 'download':

            if not self.download():
                self._clean_exit()

        elif self.operation == 'upload':

            try:
                _ = self.irods_conn.session.resources.get(self.irods_resc)
            except ResourceDoesNotExist:
                self._clean_exit(f"iRODS resource '{self.irods_resc}' not found")

            self.target_path = self.irods_path

            if not self.upload():
                self._clean_exit()

        else:
            print_error(f'Unknown operation: {self.operation}')

        self._clean_exit(message="Done", exit_code=0)

if __name__ == "__main__":

    elab = ElabPlugin()

    plugins = [
        {
            'hook': 'upload',
            'actions' : [
                { 'slot': 'pre', 'function': elab.setup },
                { 'slot': 'post', 'function': elab.annotate }
            ]
        }
    ]

    cli = iBridgesCli.from_arguments(plugins=plugins)

