"""
    Nozbe Teams API

    Nozbe Teams API specification  # noqa: E501

    The version of the OpenAPI document: 0.0.1
    Contact: support@nozbe.com
    Generated by: https://openapi-generator.tech
"""


import re  # noqa: F401
import sys  # noqa: F401

from openapi_client.api_client import ApiClient, Endpoint as _Endpoint
from openapi_client.model_utils import (  # noqa: F401
    check_allowed_values,
    check_validations,
    date,
    datetime,
    file_type,
    none_type,
    validate_and_convert_types,
)
from openapi_client.model.comment import Comment


class CommentsApi(object):
    """NOTE: This class is auto generated by OpenAPI Generator
    Ref: https://openapi-generator.tech

    Do not edit the class manually.
    """

    def __init__(self, api_client=None):
        if api_client is None:
            api_client = ApiClient()
        self.api_client = api_client
        self.delete_comment_by_id_endpoint = _Endpoint(
            settings={
                "response_type": (Comment,),
                "auth": ["ApiKeyAuth"],
                "endpoint_path": "/comments/{id}",
                "operation_id": "delete_comment_by_id",
                "http_method": "DELETE",
                "servers": None,
            },
            params_map={
                "all": [
                    "id",
                ],
                "required": [
                    "id",
                ],
                "nullable": [],
                "enum": [],
                "validation": [
                    "id",
                ],
            },
            root_map={
                "validations": {
                    ("id",): {
                        "max_length": 16,
                        "min_length": 16,
                    },
                },
                "allowed_values": {},
                "openapi_types": {
                    "id": (str,),
                },
                "attribute_map": {
                    "id": "id",
                },
                "location_map": {
                    "id": "path",
                },
                "collection_format_map": {},
            },
            headers_map={
                "accept": ["application/json"],
                "content_type": [],
            },
            api_client=api_client,
        )
        self.get_comment_by_id_endpoint = _Endpoint(
            settings={
                "response_type": (Comment,),
                "auth": ["ApiKeyAuth"],
                "endpoint_path": "/comments/{id}",
                "operation_id": "get_comment_by_id",
                "http_method": "GET",
                "servers": None,
            },
            params_map={
                "all": [
                    "id",
                    "fields",
                ],
                "required": [
                    "id",
                ],
                "nullable": [],
                "enum": [],
                "validation": [
                    "id",
                    "fields",
                ],
            },
            root_map={
                "validations": {
                    ("id",): {
                        "max_length": 16,
                        "min_length": 16,
                    },
                    ("fields",): {
                        "regex": {
                            "pattern": r"^[a-z_,]*$",  # noqa: E501
                        },
                    },
                },
                "allowed_values": {},
                "openapi_types": {
                    "id": (str,),
                    "fields": (str,),
                },
                "attribute_map": {
                    "id": "id",
                    "fields": "fields",
                },
                "location_map": {
                    "id": "path",
                    "fields": "query",
                },
                "collection_format_map": {},
            },
            headers_map={
                "accept": ["application/json"],
                "content_type": [],
            },
            api_client=api_client,
        )
        self.get_comments_endpoint = _Endpoint(
            settings={
                "response_type": ([Comment],),
                "auth": ["ApiKeyAuth"],
                "endpoint_path": "/comments",
                "operation_id": "get_comments",
                "http_method": "GET",
                "servers": None,
            },
            params_map={
                "all": [
                    "limit",
                    "offset",
                    "sort_by",
                    "fields",
                ],
                "required": [],
                "nullable": [],
                "enum": [],
                "validation": [
                    "limit",
                    "offset",
                    "sort_by",
                    "fields",
                ],
            },
            root_map={
                "validations": {
                    ("limit",): {
                        "inclusive_maximum": 10000,
                        "inclusive_minimum": 1,
                    },
                    ("offset",): {
                        "inclusive_minimum": 0,
                    },
                    ("sort_by",): {
                        "regex": {
                            "pattern": r"^[-a-z_,]*$",  # noqa: E501
                        },
                    },
                    ("fields",): {
                        "regex": {
                            "pattern": r"^[a-z_,]*$",  # noqa: E501
                        },
                    },
                },
                "allowed_values": {},
                "openapi_types": {
                    "limit": (int,),
                    "offset": (int,),
                    "sort_by": (str,),
                    "fields": (str,),
                },
                "attribute_map": {
                    "limit": "limit",
                    "offset": "offset",
                    "sort_by": "sortBy",
                    "fields": "fields",
                },
                "location_map": {
                    "limit": "query",
                    "offset": "query",
                    "sort_by": "query",
                    "fields": "query",
                },
                "collection_format_map": {},
            },
            headers_map={
                "accept": ["application/json"],
                "content_type": [],
            },
            api_client=api_client,
        )
        self.post_comment_endpoint = _Endpoint(
            settings={
                "response_type": (Comment,),
                "auth": ["ApiKeyAuth"],
                "endpoint_path": "/comments",
                "operation_id": "post_comment",
                "http_method": "POST",
                "servers": None,
            },
            params_map={
                "all": [
                    "comment",
                ],
                "required": [
                    "comment",
                ],
                "nullable": [],
                "enum": [],
                "validation": [],
            },
            root_map={
                "validations": {},
                "allowed_values": {},
                "openapi_types": {
                    "comment": (Comment,),
                },
                "attribute_map": {},
                "location_map": {
                    "comment": "body",
                },
                "collection_format_map": {},
            },
            headers_map={
                "accept": ["application/json"],
                "content_type": ["application/json"],
            },
            api_client=api_client,
        )
        self.put_comment_by_id_endpoint = _Endpoint(
            settings={
                "response_type": (Comment,),
                "auth": ["ApiKeyAuth"],
                "endpoint_path": "/comments/{id}",
                "operation_id": "put_comment_by_id",
                "http_method": "PUT",
                "servers": None,
            },
            params_map={
                "all": [
                    "id",
                    "body",
                ],
                "required": [
                    "id",
                    "body",
                ],
                "nullable": [],
                "enum": [],
                "validation": [
                    "id",
                ],
            },
            root_map={
                "validations": {
                    ("id",): {
                        "max_length": 16,
                        "min_length": 16,
                    },
                },
                "allowed_values": {},
                "openapi_types": {
                    "id": (str,),
                    "body": (
                        {
                            str: (
                                bool,
                                date,
                                datetime,
                                dict,
                                float,
                                int,
                                list,
                                str,
                                none_type,
                            )
                        },
                    ),
                },
                "attribute_map": {
                    "id": "id",
                },
                "location_map": {
                    "id": "path",
                    "body": "body",
                },
                "collection_format_map": {},
            },
            headers_map={
                "accept": ["application/json"],
                "content_type": ["application/json"],
            },
            api_client=api_client,
        )

    def delete_comment_by_id(self, id, **kwargs):
        """Delete a comment  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.delete_comment_by_id(id, async_req=True)
        >>> result = thread.get()

        Args:
            id (str): Object ID

        Keyword Args:
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            async_req (bool): execute request asynchronously

        Returns:
            Comment
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs["async_req"] = kwargs.get("async_req", False)
        kwargs["_return_http_data_only"] = kwargs.get("_return_http_data_only", True)
        kwargs["_preload_content"] = kwargs.get("_preload_content", True)
        kwargs["_request_timeout"] = kwargs.get("_request_timeout", None)
        kwargs["_check_input_type"] = kwargs.get("_check_input_type", True)
        kwargs["_check_return_type"] = kwargs.get("_check_return_type", True)
        kwargs["_spec_property_naming"] = kwargs.get("_spec_property_naming", False)
        kwargs["_content_type"] = kwargs.get("_content_type")
        kwargs["_host_index"] = kwargs.get("_host_index")
        kwargs["id"] = id
        return self.delete_comment_by_id_endpoint.call_with_http_info(**kwargs)

    def get_comment_by_id(self, id, **kwargs):
        """Get comment by ID  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.get_comment_by_id(id, async_req=True)
        >>> result = thread.get()

        Args:
            id (str): Object ID

        Keyword Args:
            fields (str): List of fields that should be returned for each object, separated with commas. [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            async_req (bool): execute request asynchronously

        Returns:
            Comment
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs["async_req"] = kwargs.get("async_req", False)
        kwargs["_return_http_data_only"] = kwargs.get("_return_http_data_only", True)
        kwargs["_preload_content"] = kwargs.get("_preload_content", True)
        kwargs["_request_timeout"] = kwargs.get("_request_timeout", None)
        kwargs["_check_input_type"] = kwargs.get("_check_input_type", True)
        kwargs["_check_return_type"] = kwargs.get("_check_return_type", True)
        kwargs["_spec_property_naming"] = kwargs.get("_spec_property_naming", False)
        kwargs["_content_type"] = kwargs.get("_content_type")
        kwargs["_host_index"] = kwargs.get("_host_index")
        kwargs["id"] = id
        return self.get_comment_by_id_endpoint.call_with_http_info(**kwargs)

    def get_comments(self, **kwargs):
        """Get accessible comments. Filter results by adding params, e.g. ?task_id=abc&is_pinned=True  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.get_comments(async_req=True)
        >>> result = thread.get()


        Keyword Args:
            limit (int): Max number of objects to return. [optional] if omitted the server will use the default value of 100
            offset (int): Number of objects to skip. [optional] if omitted the server will use the default value of 0
            sort_by (str): List of params for sorting results, separated with commas. Put '-' at the beginning of param for descending order. Example 'created_at,-name,-ended_at'. [optional]
            fields (str): List of fields that should be returned for each object, separated with commas. [optional]
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            async_req (bool): execute request asynchronously

        Returns:
            [Comment]
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs["async_req"] = kwargs.get("async_req", False)
        kwargs["_return_http_data_only"] = kwargs.get("_return_http_data_only", True)
        kwargs["_preload_content"] = kwargs.get("_preload_content", True)
        kwargs["_request_timeout"] = kwargs.get("_request_timeout", None)
        kwargs["_check_input_type"] = kwargs.get("_check_input_type", True)
        kwargs["_check_return_type"] = kwargs.get("_check_return_type", True)
        kwargs["_spec_property_naming"] = kwargs.get("_spec_property_naming", False)
        kwargs["_content_type"] = kwargs.get("_content_type")
        kwargs["_host_index"] = kwargs.get("_host_index")
        return self.get_comments_endpoint.call_with_http_info(**kwargs)

    def post_comment(self, comment, **kwargs):
        """Add a comment  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.post_comment(comment, async_req=True)
        >>> result = thread.get()

        Args:
            comment (Comment):

        Keyword Args:
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            async_req (bool): execute request asynchronously

        Returns:
            Comment
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs["async_req"] = kwargs.get("async_req", False)
        kwargs["_return_http_data_only"] = kwargs.get("_return_http_data_only", True)
        kwargs["_preload_content"] = kwargs.get("_preload_content", True)
        kwargs["_request_timeout"] = kwargs.get("_request_timeout", None)
        kwargs["_check_input_type"] = kwargs.get("_check_input_type", True)
        kwargs["_check_return_type"] = kwargs.get("_check_return_type", True)
        kwargs["_spec_property_naming"] = kwargs.get("_spec_property_naming", False)
        kwargs["_content_type"] = kwargs.get("_content_type")
        kwargs["_host_index"] = kwargs.get("_host_index")
        kwargs["comment"] = comment
        return self.post_comment_endpoint.call_with_http_info(**kwargs)

    def put_comment_by_id(self, id, body, **kwargs):
        """Update a comment  # noqa: E501

        This method makes a synchronous HTTP request by default. To make an
        asynchronous HTTP request, please pass async_req=True

        >>> thread = api.put_comment_by_id(id, body, async_req=True)
        >>> result = thread.get()

        Args:
            id (str): Object ID
            body ({str: (bool, date, datetime, dict, float, int, list, str, none_type)}):

        Keyword Args:
            _return_http_data_only (bool): response data without head status
                code and headers. Default is True.
            _preload_content (bool): if False, the urllib3.HTTPResponse object
                will be returned without reading/decoding response data.
                Default is True.
            _request_timeout (int/float/tuple): timeout setting for this request. If
                one number provided, it will be total request timeout. It can also
                be a pair (tuple) of (connection, read) timeouts.
                Default is None.
            _check_input_type (bool): specifies if type checking
                should be done one the data sent to the server.
                Default is True.
            _check_return_type (bool): specifies if type checking
                should be done one the data received from the server.
                Default is True.
            _spec_property_naming (bool): True if the variable names in the input data
                are serialized names, as specified in the OpenAPI document.
                False if the variable names in the input data
                are pythonic names, e.g. snake case (default)
            _content_type (str/None): force body content-type.
                Default is None and content-type will be predicted by allowed
                content-types and body.
            _host_index (int/None): specifies the index of the server
                that we want to use.
                Default is read from the configuration.
            async_req (bool): execute request asynchronously

        Returns:
            Comment
                If the method is called asynchronously, returns the request
                thread.
        """
        kwargs["async_req"] = kwargs.get("async_req", False)
        kwargs["_return_http_data_only"] = kwargs.get("_return_http_data_only", True)
        kwargs["_preload_content"] = kwargs.get("_preload_content", True)
        kwargs["_request_timeout"] = kwargs.get("_request_timeout", None)
        kwargs["_check_input_type"] = kwargs.get("_check_input_type", True)
        kwargs["_check_return_type"] = kwargs.get("_check_return_type", True)
        kwargs["_spec_property_naming"] = kwargs.get("_spec_property_naming", False)
        kwargs["_content_type"] = kwargs.get("_content_type")
        kwargs["_host_index"] = kwargs.get("_host_index")
        kwargs["id"] = id
        kwargs["body"] = body
        return self.put_comment_by_id_endpoint.call_with_http_info(**kwargs)
