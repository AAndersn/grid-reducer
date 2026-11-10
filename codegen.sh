# Regenerate the config models and JSON Schema from the LinkML schema.
LINKML="uvx --from linkml==1.12.1"
$LINKML gen-json-schema src/grid_reducer/schemas/sanitize_config.linkml.yaml > src/grid_reducer/schemas/SanitizeConfig.schema.json
$LINKML gen-pydantic src/grid_reducer/schemas/sanitize_config.linkml.yaml > src/grid_reducer/config_models.py
