"""
    Nozbe Teams API

    Nozbe Teams API specification  # noqa: E501

    The version of the OpenAPI document: 0.0.1
    Contact: support@nozbe.com
    Generated by: https://openapi-generator.tech
"""


import re  # noqa: F401
import sys  # noqa: F401

from openapi_client.model_utils import (  # noqa: F401
    ApiTypeError,
    ModelComposed,
    ModelNormal,
    ModelSimple,
    cached_property,
    change_keys_js_to_python,
    convert_js_args_to_python_args,
    date,
    datetime,
    file_type,
    none_type,
    validate_get_composed_info,
    OpenApiModel
)
from openapi_client.exceptions import ApiAttributeError


def lazy_import():
    from openapi_client.model.id16 import Id16
    from openapi_client.model.id16_nullable import Id16Nullable
    from openapi_client.model.id16_read_only import Id16ReadOnly
    from openapi_client.model.name import Name
    from openapi_client.model.project_id import ProjectId
    from openapi_client.model.timestamp_nullable import TimestampNullable
    from openapi_client.model.timestamp_read_only import TimestampReadOnly
    globals()['Id16'] = Id16
    globals()['Id16Nullable'] = Id16Nullable
    globals()['Id16ReadOnly'] = Id16ReadOnly
    globals()['Name'] = Name
    globals()['ProjectId'] = ProjectId
    globals()['TimestampNullable'] = TimestampNullable
    globals()['TimestampReadOnly'] = TimestampReadOnly


class Task(ModelNormal):
    """NOTE: This class is auto generated by OpenAPI Generator.
    Ref: https://openapi-generator.tech

    Do not edit the class manually.

    Attributes:
      allowed_values (dict): The key is the tuple path to the attribute
          and the for var_name this is (var_name,). The value is a dict
          with a capitalized key describing the allowed value and an allowed
          value. These dicts store the allowed enum values.
      attribute_map (dict): The key is attribute name
          and the value is json key in definition.
      discriminator_value_class_map (dict): A dict to go from the discriminator
          variable value to the discriminator class name.
      validations (dict): The key is the tuple path to the attribute
          and the for var_name this is (var_name,). The value is a dict
          that stores validations for max_length, min_length, max_items,
          min_items, exclusive_maximum, inclusive_maximum, exclusive_minimum,
          inclusive_minimum, and regex.
      additional_properties_type (tuple): A tuple of classes accepted
          as additional properties values.
    """

    allowed_values = {
        ('review_reason',): {
            'None': None,
            'NULL': "null",
            'DUE_DATE': "due_date",
            'REMINDER': "reminder",
            'DELEGATED': "delegated",
            'MENTION': "mention",
            'NEWLY_ADDED': "newly_added",
        },
    }

    validations = {
        ('responsible_id',): {
            'max_length': 16,
            'min_length': 6,
            'regex': {
                'pattern': r'^([a-zA-Z0-9]{16}|author)$',  # noqa: E501
            },
        },
        ('missed_repeats',): {
            'inclusive_minimum': 0,
        },
    }

    @cached_property
    def additional_properties_type():
        """
        This must be a method because a model may have properties that are
        of type self, this must run after the class is loaded
        """
        lazy_import()
        return (bool, date, datetime, dict, float, int, list, str, none_type,)  # noqa: E501

    _nullable = False

    @cached_property
    def openapi_types():
        """
        This must be a method because a model may have properties that are
        of type self, this must run after the class is loaded

        Returns
            openapi_types (dict): The key is attribute name
                and the value is attribute type.
        """
        lazy_import()
        return {
            'name': (Name,),  # noqa: E501
            'project_id': (ProjectId,),  # noqa: E501
            'author_id': (Id16ReadOnly,),  # noqa: E501
            'created_at': (TimestampReadOnly,),  # noqa: E501
            'last_activity_at': (TimestampReadOnly,),  # noqa: E501
            'id': (Id16,),  # noqa: E501
            'project_section_id': (Id16Nullable,),  # noqa: E501
            'responsible_id': (str, none_type,),  # noqa: E501
            'pinned_comment_id': (Id16Nullable,),  # noqa: E501
            'recurrence_id': (Id16Nullable,),  # noqa: E501
            'last_modified': (TimestampReadOnly,),  # noqa: E501
            'due_at': (TimestampNullable,),  # noqa: E501
            'ended_at': (TimestampNullable,),  # noqa: E501
            'last_seen_activity_at': (TimestampNullable,),  # noqa: E501
            'last_reviewed_at': (TimestampNullable,),  # noqa: E501
            'review_triggered_at': (TimestampNullable,),  # noqa: E501
            'review_reason': (str, none_type,),  # noqa: E501
            'is_followed': (bool,),  # noqa: E501
            'is_abandoned': (bool,),  # noqa: E501
            'is_all_day': (bool,),  # noqa: E501
            'project_position': (float,),  # noqa: E501
            'priority_position': (float, none_type,),  # noqa: E501
            'missed_repeats': (int,),  # noqa: E501
        }

    @cached_property
    def discriminator():
        return None


    attribute_map = {
        'name': 'name',  # noqa: E501
        'project_id': 'project_id',  # noqa: E501
        'author_id': 'author_id',  # noqa: E501
        'created_at': 'created_at',  # noqa: E501
        'last_activity_at': 'last_activity_at',  # noqa: E501
        'id': 'id',  # noqa: E501
        'project_section_id': 'project_section_id',  # noqa: E501
        'responsible_id': 'responsible_id',  # noqa: E501
        'pinned_comment_id': 'pinned_comment_id',  # noqa: E501
        'recurrence_id': 'recurrence_id',  # noqa: E501
        'last_modified': 'last_modified',  # noqa: E501
        'due_at': 'due_at',  # noqa: E501
        'ended_at': 'ended_at',  # noqa: E501
        'last_seen_activity_at': 'last_seen_activity_at',  # noqa: E501
        'last_reviewed_at': 'last_reviewed_at',  # noqa: E501
        'review_triggered_at': 'review_triggered_at',  # noqa: E501
        'review_reason': 'review_reason',  # noqa: E501
        'is_followed': 'is_followed',  # noqa: E501
        'is_abandoned': 'is_abandoned',  # noqa: E501
        'is_all_day': 'is_all_day',  # noqa: E501
        'project_position': 'project_position',  # noqa: E501
        'priority_position': 'priority_position',  # noqa: E501
        'missed_repeats': 'missed_repeats',  # noqa: E501
    }

    read_only_vars = {
    }

    _composed_schemas = {}

    @classmethod
    @convert_js_args_to_python_args
    def _from_openapi_data(cls, name, project_id, author_id, created_at, last_activity_at, *args, **kwargs):  # noqa: E501
        """Task - a model defined in OpenAPI

        Args:
            name (Name):
            project_id (ProjectId):
            author_id (Id16ReadOnly):
            created_at (TimestampReadOnly):
            last_activity_at (TimestampReadOnly):

        Keyword Args:
            _check_type (bool): if True, values for parameters in openapi_types
                                will be type checked and a TypeError will be
                                raised if the wrong type is input.
                                Defaults to True
            _path_to_item (tuple/list): This is a list of keys or values to
                                drill down to the model in received_data
                                when deserializing a response
            _spec_property_naming (bool): True if the variable names in the input data
                                are serialized names, as specified in the OpenAPI document.
                                False if the variable names in the input data
                                are pythonic names, e.g. snake case (default)
            _configuration (Configuration): the instance to use when
                                deserializing a file_type parameter.
                                If passed, type conversion is attempted
                                If omitted no type conversion is done.
            _visited_composed_classes (tuple): This stores a tuple of
                                classes that we have traveled through so that
                                if we see that class again we will not use its
                                discriminator again.
                                When traveling through a discriminator, the
                                composed schema that is
                                is traveled through is added to this set.
                                For example if Animal has a discriminator
                                petType and we pass in "Dog", and the class Dog
                                allOf includes Animal, we move through Animal
                                once using the discriminator, and pick Dog.
                                Then in Dog, we will make an instance of the
                                Animal class but this time we won't travel
                                through its discriminator because we passed in
                                _visited_composed_classes = (Animal,)
            id (Id16): [optional]  # noqa: E501
            project_section_id (Id16Nullable): [optional]  # noqa: E501
            responsible_id (str, none_type): [optional]  # noqa: E501
            pinned_comment_id (Id16Nullable): [optional]  # noqa: E501
            recurrence_id (Id16Nullable): [optional]  # noqa: E501
            last_modified (TimestampReadOnly): [optional]  # noqa: E501
            due_at (TimestampNullable): [optional]  # noqa: E501
            ended_at (TimestampNullable): [optional]  # noqa: E501
            last_seen_activity_at (TimestampNullable): [optional]  # noqa: E501
            last_reviewed_at (TimestampNullable): [optional]  # noqa: E501
            review_triggered_at (TimestampNullable): [optional]  # noqa: E501
            review_reason (str, none_type): [optional]  # noqa: E501
            is_followed (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            is_abandoned (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            is_all_day (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            project_position (float): [optional]  # noqa: E501
            priority_position (float, none_type): [optional]  # noqa: E501
            missed_repeats (int): [optional]  # noqa: E501
        """

        _check_type = kwargs.pop('_check_type', True)
        _spec_property_naming = kwargs.pop('_spec_property_naming', False)
        _path_to_item = kwargs.pop('_path_to_item', ())
        _configuration = kwargs.pop('_configuration', None)
        _visited_composed_classes = kwargs.pop('_visited_composed_classes', ())

        self = super(OpenApiModel, cls).__new__(cls)

        if args:
            raise ApiTypeError(
                "Invalid positional arguments=%s passed to %s. Remove those invalid positional arguments." % (
                    args,
                    self.__class__.__name__,
                ),
                path_to_item=_path_to_item,
                valid_classes=(self.__class__,),
            )

        self._data_store = {}
        self._check_type = _check_type
        self._spec_property_naming = _spec_property_naming
        self._path_to_item = _path_to_item
        self._configuration = _configuration
        self._visited_composed_classes = _visited_composed_classes + (self.__class__,)

        self.name = name
        self.project_id = project_id
        self.author_id = author_id
        self.created_at = created_at
        self.last_activity_at = last_activity_at
        for var_name, var_value in kwargs.items():
            if var_name not in self.attribute_map and \
                        self._configuration is not None and \
                        self._configuration.discard_unknown_keys and \
                        self.additional_properties_type is None:
                # discard variable.
                continue
            setattr(self, var_name, var_value)
        return self

    required_properties = set([
        '_data_store',
        '_check_type',
        '_spec_property_naming',
        '_path_to_item',
        '_configuration',
        '_visited_composed_classes',
    ])

    @convert_js_args_to_python_args
    def __init__(self, name, project_id, author_id, created_at, last_activity_at, *args, **kwargs):  # noqa: E501
        """Task - a model defined in OpenAPI

        Args:
            name (Name):
            project_id (ProjectId):
            author_id (Id16ReadOnly):
            created_at (TimestampReadOnly):
            last_activity_at (TimestampReadOnly):

        Keyword Args:
            _check_type (bool): if True, values for parameters in openapi_types
                                will be type checked and a TypeError will be
                                raised if the wrong type is input.
                                Defaults to True
            _path_to_item (tuple/list): This is a list of keys or values to
                                drill down to the model in received_data
                                when deserializing a response
            _spec_property_naming (bool): True if the variable names in the input data
                                are serialized names, as specified in the OpenAPI document.
                                False if the variable names in the input data
                                are pythonic names, e.g. snake case (default)
            _configuration (Configuration): the instance to use when
                                deserializing a file_type parameter.
                                If passed, type conversion is attempted
                                If omitted no type conversion is done.
            _visited_composed_classes (tuple): This stores a tuple of
                                classes that we have traveled through so that
                                if we see that class again we will not use its
                                discriminator again.
                                When traveling through a discriminator, the
                                composed schema that is
                                is traveled through is added to this set.
                                For example if Animal has a discriminator
                                petType and we pass in "Dog", and the class Dog
                                allOf includes Animal, we move through Animal
                                once using the discriminator, and pick Dog.
                                Then in Dog, we will make an instance of the
                                Animal class but this time we won't travel
                                through its discriminator because we passed in
                                _visited_composed_classes = (Animal,)
            id (Id16): [optional]  # noqa: E501
            project_section_id (Id16Nullable): [optional]  # noqa: E501
            responsible_id (str, none_type): [optional]  # noqa: E501
            pinned_comment_id (Id16Nullable): [optional]  # noqa: E501
            recurrence_id (Id16Nullable): [optional]  # noqa: E501
            last_modified (TimestampReadOnly): [optional]  # noqa: E501
            due_at (TimestampNullable): [optional]  # noqa: E501
            ended_at (TimestampNullable): [optional]  # noqa: E501
            last_seen_activity_at (TimestampNullable): [optional]  # noqa: E501
            last_reviewed_at (TimestampNullable): [optional]  # noqa: E501
            review_triggered_at (TimestampNullable): [optional]  # noqa: E501
            review_reason (str, none_type): [optional]  # noqa: E501
            is_followed (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            is_abandoned (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            is_all_day (bool): [optional] if omitted the server will use the default value of False  # noqa: E501
            project_position (float): [optional]  # noqa: E501
            priority_position (float, none_type): [optional]  # noqa: E501
            missed_repeats (int): [optional]  # noqa: E501
        """

        _check_type = kwargs.pop('_check_type', True)
        _spec_property_naming = kwargs.pop('_spec_property_naming', False)
        _path_to_item = kwargs.pop('_path_to_item', ())
        _configuration = kwargs.pop('_configuration', None)
        _visited_composed_classes = kwargs.pop('_visited_composed_classes', ())

        if args:
            raise ApiTypeError(
                "Invalid positional arguments=%s passed to %s. Remove those invalid positional arguments." % (
                    args,
                    self.__class__.__name__,
                ),
                path_to_item=_path_to_item,
                valid_classes=(self.__class__,),
            )

        self._data_store = {}
        self._check_type = _check_type
        self._spec_property_naming = _spec_property_naming
        self._path_to_item = _path_to_item
        self._configuration = _configuration
        self._visited_composed_classes = _visited_composed_classes + (self.__class__,)

        self.name = name
        self.project_id = project_id
        self.author_id = author_id
        self.created_at = created_at
        self.last_activity_at = last_activity_at
        for var_name, var_value in kwargs.items():
            if var_name not in self.attribute_map and \
                        self._configuration is not None and \
                        self._configuration.discard_unknown_keys and \
                        self.additional_properties_type is None:
                # discard variable.
                continue
            setattr(self, var_name, var_value)
            if var_name in self.read_only_vars:
                raise ApiAttributeError(f"`{var_name}` is a read-only attribute. Use `from_openapi_data` to instantiate "
                                     f"class with read only attributes.")
