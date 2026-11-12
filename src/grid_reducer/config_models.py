from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.12.0"
version = "0.1.0"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'gridreducer',
     'default_range': 'string',
     'description': 'What grid-reducer does to a feeder model before it is shared: '
                    'which concepts to drop, whether to reduce transformers and '
                    'lines, how much noise each category of values gets, and what '
                    'to write. The passes always run in one order: filter, reduce '
                    'transformers, reduce lines, layout, noise, rename, validate, '
                    'write.',
     'id': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config',
     'imports': ['linkml:types'],
     'license': 'BSD-3-Clause',
     'name': 'sanitize_config',
     'prefixes': {'gridreducer': {'prefix_prefix': 'gridreducer',
                                  'prefix_reference': 'https://w3id.org/grid-kitchen/grid-reducer/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': 'src/grid_reducer/schemas/sanitize_config.linkml.yaml',
     'title': 'Grid Reducer Sanitize Config'} )

class PrivacyLevel(str, Enum):
    none = "none"
    """
    Values are published unchanged.
    """
    low = "low"
    moderate = "moderate"
    high = "high"


class OutputFormat(str, Enum):
    cimtbl = "cimtbl"
    cim_xml = "cim_xml"



class SanitizeConfig(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config',
         'tree_root': True})

    source: str = Field(default=..., description="""The model to sanitize (a .cimtbl master file), relative to the config file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    seed: Optional[int] = Field(default=None, description="""Seed for every random choice; omit for a fresh random run.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    filters: Optional[Filters] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    reduce: Optional[Reduce] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    layout: Optional[Layout] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig', 'Noise']} })
    noise: Optional[Noise] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    rename: Optional[Rename] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })
    outputs: Optional[list[OutputFormat]] = Field(default=None, description="""Formats written at the end of the run; cimtbl when omitted.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig']} })


class Filters(ConfiguredBaseModel):
    """
    Concepts removed from the model before anything else runs.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config'})

    drop_classes: Optional[list[str]] = Field(default=None, description="""CIM classes whose objects are deleted, with their subclasses and the parts they own (Terminals, phases, Locations, ...). e.g. FunctionBlock.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Filters']} })
    drop_attributes: Optional[list[str]] = Field(default=None, description="""Class.attribute values cleared on every object of that class or a subclass, e.g. Fuse.ratedCurrent.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Filters']} })

    @field_validator('drop_classes')
    def pattern_drop_classes(cls, v):
        pattern=re.compile(r"^[A-Z][A-Za-z0-9]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid drop_classes format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid drop_classes format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('drop_attributes')
    def pattern_drop_attributes(cls, v):
        pattern=re.compile(r"^[A-Z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid drop_attributes format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid drop_attributes format: {v}"
            raise ValueError(err_msg)
        return v


class Reduce(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config'})

    transformers: Optional[bool] = Field(default=False, description="""Collapse service transformers and their secondaries into the primary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Reduce', 'Noise'], 'ifabsent': 'false'} })
    lines: Optional[bool] = Field(default=False, description="""Merge series line segments between preserved nodes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Reduce', 'Noise'], 'ifabsent': 'false'} })


class Layout(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config'})

    enabled: Optional[bool] = Field(default=False, description="""Replace coordinates with a force-directed layout pinned at trunk branch points.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Layout', 'Rename'], 'ifabsent': 'false'} })
    pin_degrees: Optional[list[int]] = Field(default=None, description="""Node degrees pinned on the trunk.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Layout']} })
    obfuscation: Optional[PrivacyLevel] = Field(default=PrivacyLevel("moderate"), description="""How few trunk taps are pinned.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Layout'], 'ifabsent': 'PrivacyLevel(moderate)'} })


class Noise(ConfiguredBaseModel):
    """
    The noise catalog's privacy mode for each category of values.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config'})

    transformers: Optional[PrivacyLevel] = Field(default=PrivacyLevel("none"), json_schema_extra = { "linkml_meta": {'domain_of': ['Reduce', 'Noise'], 'ifabsent': 'PrivacyLevel(none)'} })
    lines: Optional[PrivacyLevel] = Field(default=PrivacyLevel("none"), json_schema_extra = { "linkml_meta": {'domain_of': ['Reduce', 'Noise'], 'ifabsent': 'PrivacyLevel(none)'} })
    loads: Optional[PrivacyLevel] = Field(default=PrivacyLevel("none"), json_schema_extra = { "linkml_meta": {'domain_of': ['Noise'], 'ifabsent': 'PrivacyLevel(none)'} })
    layout: Optional[PrivacyLevel] = Field(default=PrivacyLevel("none"), json_schema_extra = { "linkml_meta": {'domain_of': ['SanitizeConfig', 'Noise'], 'ifabsent': 'PrivacyLevel(none)'} })


class Rename(ConfiguredBaseModel):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://w3id.org/grid-kitchen/grid-reducer/sanitize-config'})

    enabled: Optional[bool] = Field(default=True, description="""Replace every name and identifier with canonical ones; turn off only to inspect a run, since the output then carries the source's names.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Layout', 'Rename'], 'ifabsent': 'true'} })
    model_name: Optional[str] = Field(default="feeder", description="""The published Model name, and the output files' name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Rename'], 'ifabsent': 'string(feeder)'} })

    @field_validator('model_name')
    def pattern_model_name(cls, v):
        pattern=re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.search(element):
                    err_msg = f"Invalid model_name format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.search(v):
            err_msg = f"Invalid model_name format: {v}"
            raise ValueError(err_msg)
        return v


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
SanitizeConfig.model_rebuild()
Filters.model_rebuild()
Reduce.model_rebuild()
Layout.model_rebuild()
Noise.model_rebuild()
Rename.model_rebuild()
