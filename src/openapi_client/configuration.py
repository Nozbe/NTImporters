# coding: utf-8



import copy
import logging
from logging import FileHandler
import multiprocessing
import sys
from typing import Optional
import urllib3

import http.client as httplib

JSON_SCHEMA_VALIDATION_KEYWORDS = {
    'multipleOf', 'maximum', 'exclusiveMaximum',
    'minimum', 'exclusiveMinimum', 'maxLength',
    'minLength', 'pattern', 'maxItems', 'minItems'
}

class Configuration:

    _default = None

    def __init__(self, host=None,
                 api_key=None, api_key_prefix=None,
                 username=None, password=None,
                 access_token=None,
                 server_index=None, server_variables=None,
                 server_operation_index=None, server_operation_variables=None,
                 ignore_operation_servers=False,
                 ssl_ca_cert=None,
                 retries=None,
                 *,
                 debug: Optional[bool] = None
                 ) -> None:
        self._base_path = "https://api4.nozbe.com/v1/api" if host is None else host
        self.server_index = 0 if server_index is None and host is None else server_index
        self.server_operation_index = server_operation_index or {}
        self.server_variables = server_variables or {}
        self.server_operation_variables = server_operation_variables or {}
        self.ignore_operation_servers = ignore_operation_servers
        self.temp_folder_path = None
        # Authentication Settings
        self.api_key = {}
        if api_key:
            self.api_key = api_key
        self.api_key_prefix = {}
        if api_key_prefix:
            self.api_key_prefix = api_key_prefix
        self.refresh_api_key_hook = None
        self.username = username
        self.password = password
        self.access_token = access_token
        self.logger = {}
        self.logger["package_logger"] = logging.getLogger("openapi_client")
        self.logger["urllib3_logger"] = logging.getLogger("urllib3")
        self.logger_format = '%(asctime)s %(levelname)s %(message)s'
        self.logger_stream_handler = None
        self.logger_file_handler: Optional[FileHandler] = None
        self.logger_file = None
        if debug is not None:
            self.debug = debug
        else:
            self.__debug = False

        self.verify_ssl = True
        self.ssl_ca_cert = ssl_ca_cert
        self.cert_file = None
        self.key_file = None
        self.assert_hostname = None
        self.tls_server_name = None

        self.connection_pool_maxsize = multiprocessing.cpu_count() * 5

        self.proxy: Optional[str] = None
        self.proxy_headers = None
        self.safe_chars_for_path_param = ''
        self.retries = retries
        # Enable client side validation
        self.client_side_validation = True

        self.socket_options = None

        self.datetime_format = "%Y-%m-%dT%H:%M:%S.%f%z"

        self.date_format = "%Y-%m-%d"

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k not in ('logger', 'logger_file_handler'):
                setattr(result, k, copy.deepcopy(v, memo))
        # shallow copy of loggers
        result.logger = copy.copy(self.logger)
        # use setters to configure loggers
        result.logger_file = self.logger_file
        result.debug = self.debug
        return result

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    @classmethod
    def set_default(cls, default):
        cls._default = default

    @classmethod
    def get_default_copy(cls):
        return cls.get_default()

    @classmethod
    def get_default(cls):
        if cls._default is None:
            cls._default = Configuration()
        return cls._default

    @property
    def logger_file(self):
        return self.__logger_file

    @logger_file.setter
    def logger_file(self, value):
        self.__logger_file = value
        if self.__logger_file:
            # If set logging file,
            # then add file handler and remove stream handler.
            self.logger_file_handler = logging.FileHandler(self.__logger_file)
            self.logger_file_handler.setFormatter(self.logger_formatter)
            for _, logger in self.logger.items():
                logger.addHandler(self.logger_file_handler)

    @property
    def debug(self):
        return self.__debug

    @debug.setter
    def debug(self, value):
        self.__debug = value
        if self.__debug:
            # if debug status is True, turn on debug logging
            for _, logger in self.logger.items():
                logger.setLevel(logging.DEBUG)
            # turn on httplib debug
            httplib.HTTPConnection.debuglevel = 1
        else:
            # if debug status is False, turn off debug logging,
            # setting log level to default `logging.WARNING`
            for _, logger in self.logger.items():
                logger.setLevel(logging.WARNING)
            # turn off httplib debug
            httplib.HTTPConnection.debuglevel = 0

    @property
    def logger_format(self):
        return self.__logger_format

    @logger_format.setter
    def logger_format(self, value):
        self.__logger_format = value
        self.logger_formatter = logging.Formatter(self.__logger_format)

    def get_api_key_with_prefix(self, identifier, alias=None):
        if self.refresh_api_key_hook is not None:
            self.refresh_api_key_hook(self)
        key = self.api_key.get(identifier, self.api_key.get(alias) if alias is not None else None)
        if key:
            prefix = self.api_key_prefix.get(identifier)
            if prefix:
                return "%s %s" % (prefix, key)
            else:
                return key

    def get_basic_auth_token(self):
        username = ""
        if self.username is not None:
            username = self.username
        password = ""
        if self.password is not None:
            password = self.password
        return urllib3.util.make_headers(
            basic_auth=username + ':' + password
        ).get('authorization')

    def auth_settings(self):
        auth = {}
        if 'ApiKeyAuth' in self.api_key:
            auth['ApiKeyAuth'] = {
                'type': 'api_key',
                'in': 'header',
                'key': 'Authorization',
                'value': self.get_api_key_with_prefix(
                    'ApiKeyAuth',
                ),
            }
        return auth

    def to_debug_report(self):
        return "Python SDK Debug Report:\n"\
               "OS: {env}\n"\
               "Python Version: {pyversion}\n"\
               "Version of the API: 0.0.1\n"\
               "SDK Package Version: 1.0.0".\
               format(env=sys.platform, pyversion=sys.version)

    def get_host_settings(self):
        return [
            {
                'url': "https://api4.nozbe.com/v1/api",
                'description': "No description provided",
            },
            {
                'url': "https://api4.nozbe.com/v1/api",
                'description': "No description provided",
            }
        ]

    def get_host_from_settings(self, index, variables=None, servers=None):
        if index is None:
            return self._base_path

        variables = {} if variables is None else variables
        servers = self.get_host_settings() if servers is None else servers

        try:
            server = servers[index]
        except IndexError:
            raise ValueError(
                "Invalid index {0} when selecting the host settings. "
                "Must be less than {1}".format(index, len(servers)))

        url = server['url']

        # go through variables and replace placeholders
        for variable_name, variable in server.get('variables', {}).items():
            used_value = variables.get(
                variable_name, variable['default_value'])

            if 'enum_values' in variable \
                    and used_value not in variable['enum_values']:
                raise ValueError(
                    "The variable `{0}` in the host URL has invalid value "
                    "{1}. Must be {2}.".format(
                        variable_name, variables[variable_name],
                        variable['enum_values']))

            url = url.replace("{" + variable_name + "}", used_value)

        return url

    @property
    def host(self):
        return self.get_host_from_settings(self.server_index, variables=self.server_variables)

    @host.setter
    def host(self, value):
        self._base_path = value
        self.server_index = None
