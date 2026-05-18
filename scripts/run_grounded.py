"""
Grounded evaluation: replicates @DTDL/Debug LLM repair suggestions.

Reproduces exactly the prompt construction from +Debug.svelte tryToFixWithLLM():
  - System: "You are an expert in DTDL (Digital Twins Definition Language) v4.
             You receive structured diagnostic information from a symbolic ASP-based validator.
             Explain the root cause of the error and suggest a concrete, actionable fix
             including the corrected DTDL JSON-LD snippet.
             Do not invent properties or fields not defined in the DTDL v4 specification.
             Be concise: max 200 words."
  - User: structured context produced by atom_to_structured_context(), derived from
          the __debug__ atoms produced by debug.lp.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    uv run --with openai --with clingo run_grounded.py

Outputs: grounded_responses.json
"""

# /// script
# requires-python = ">=3.11"
# dependencies = ["openai", "clingo"]
# ///

import os
import json
import clingo

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MODEL = "deepseek/deepseek-v3.2"
BASE_URL = "https://openrouter.ai/api/v1"

# debug.lp is copied here from asp-chef/src/lib/operations/@DTDL/res/debug.lp
DEBUG_LP = os.path.join(os.path.dirname(__file__), "debug.lp")

# ASP facts for the vineyard model + property_value_defined requirements.
# These are the facts produced by @DTDL/Parse on the vineyard DTDL model,
# plus the property_value_defined/2 facts added in the recipe.
VINEYARD_FACTS = """
interface("dtmi:agriculture:vineyard:VineyardProperty;1").
interface("dtmi:agriculture:vineyard:PestTrap;1").
interface("dtmi:agriculture:vineyard:SoilMoistureSensor;1").
interface("dtmi:agriculture:vineyard:IrrigationController;1").
interface("dtmi:agriculture:vineyard:GrapeMonitor;1").

relationship(("dtmi:agriculture:vineyard:VineyardProperty;1","hasVineyardPlots")).
relationship(("dtmi:agriculture:vineyard:VineyardProperty;1","hasWeatherStation")).
relationship(("dtmi:agriculture:vineyard:VineyardProperty;1","hasWinery")).
relationship(("dtmi:agriculture:vineyard:PestTrap;1","installedIn")).
relationship(("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installedIn")).
relationship(("dtmi:agriculture:vineyard:IrrigationController;1","controlsPlot")).
relationship(("dtmi:agriculture:vineyard:IrrigationController;1","connectedSensors")).
relationship(("dtmi:agriculture:vineyard:GrapeMonitor;1","monitoringPlot")).

target(("dtmi:agriculture:vineyard:VineyardProperty;1","hasVineyardPlots"),"dtmi:agriculture:vineyard:VineyardPlot;1").
target(("dtmi:agriculture:vineyard:VineyardProperty;1","hasWeatherStation"),"dtmi:agriculture:vineyard:WeatherStation;1").
target(("dtmi:agriculture:vineyard:VineyardProperty;1","hasWinery"),"dtmi:agriculture:vineyard:Winery;1").
target(("dtmi:agriculture:vineyard:PestTrap;1","installedIn"),"dtmi:agriculture:vineyard:VineyardPlot;1").
target(("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installedIn"),"dtmi:agriculture:vineyard:VineyardPlot;1").
target(("dtmi:agriculture:vineyard:IrrigationController;1","controlsPlot"),"dtmi:agriculture:vineyard:VineyardPlot;1").
target(("dtmi:agriculture:vineyard:IrrigationController;1","connectedSensors"),"dtmi:agriculture:vineyard:SoilMoistureSensor;1").
target(("dtmi:agriculture:vineyard:GrapeMonitor;1","monitoringPlot"),"dtmi:agriculture:vineyard:VineyardPlot;1").

has_property("dtmi:agriculture:vineyard:VineyardProperty;1","name",("dtmi:agriculture:vineyard:VineyardProperty;1","name")).
has_property("dtmi:agriculture:vineyard:VineyardProperty;1","owner",("dtmi:agriculture:vineyard:VineyardProperty;1","owner")).
has_property("dtmi:agriculture:vineyard:VineyardProperty;1","totalArea",("dtmi:agriculture:vineyard:VineyardProperty;1","totalArea")).
has_property("dtmi:agriculture:vineyard:VineyardProperty;1","elevation",("dtmi:agriculture:vineyard:VineyardProperty;1","elevation")).
has_property("dtmi:agriculture:vineyard:VineyardProperty;1","location",("dtmi:agriculture:vineyard:VineyardProperty;1","location")).
has_property("dtmi:agriculture:vineyard:PestTrap;1","trapId",("dtmi:agriculture:vineyard:PestTrap;1","trapId")).
has_property("dtmi:agriculture:vineyard:PestTrap;1","targetPest",("dtmi:agriculture:vineyard:PestTrap;1","targetPest")).
has_property("dtmi:agriculture:vineyard:PestTrap;1","installationDate",("dtmi:agriculture:vineyard:PestTrap;1","installationDate")).
has_property("dtmi:agriculture:vineyard:PestTrap;1","batteryLevel",("dtmi:agriculture:vineyard:PestTrap;1","batteryLevel")).
has_property("dtmi:agriculture:vineyard:SoilMoistureSensor;1","sensorId",("dtmi:agriculture:vineyard:SoilMoistureSensor;1","sensorId")).
has_property("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installationDepth",("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installationDepth")).
has_property("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installationDate",("dtmi:agriculture:vineyard:SoilMoistureSensor;1","installationDate")).
has_property("dtmi:agriculture:vineyard:SoilMoistureSensor;1","batteryLevel",("dtmi:agriculture:vineyard:SoilMoistureSensor;1","batteryLevel")).
has_property("dtmi:agriculture:vineyard:IrrigationController;1","controllerId",("dtmi:agriculture:vineyard:IrrigationController;1","controllerId")).
has_property("dtmi:agriculture:vineyard:IrrigationController;1","model",("dtmi:agriculture:vineyard:IrrigationController;1","model")).
has_property("dtmi:agriculture:vineyard:IrrigationController;1","installationDate",("dtmi:agriculture:vineyard:IrrigationController;1","installationDate")).
has_property("dtmi:agriculture:vineyard:IrrigationController;1","waterSource",("dtmi:agriculture:vineyard:IrrigationController;1","waterSource")).
has_property("dtmi:agriculture:vineyard:IrrigationController;1","operatingStatus",("dtmi:agriculture:vineyard:IrrigationController;1","operatingStatus")).
has_property("dtmi:agriculture:vineyard:GrapeMonitor;1","monitorId",("dtmi:agriculture:vineyard:GrapeMonitor;1","monitorId")).
has_property("dtmi:agriculture:vineyard:GrapeMonitor;1","grapeVariety",("dtmi:agriculture:vineyard:GrapeMonitor;1","grapeVariety")).
has_property("dtmi:agriculture:vineyard:GrapeMonitor;1","installationDate",("dtmi:agriculture:vineyard:GrapeMonitor;1","installationDate")).
has_property("dtmi:agriculture:vineyard:GrapeMonitor;1","batteryLevel",("dtmi:agriculture:vineyard:GrapeMonitor;1","batteryLevel")).
has_property("dtmi:agriculture:vineyard:GrapeMonitor;1","cameraResolution",("dtmi:agriculture:vineyard:GrapeMonitor;1","cameraResolution")).

% External requirements: properties declared mandatory by the recipe author
property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1","soilType").
property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1","plotArea").
property_value_defined("dtmi:agriculture:vineyard:VineyardPlot;1","grapeVariety").
property_value_defined("dtmi:agriculture:vineyard:WeatherStation;1","stationId").
property_value_defined("dtmi:agriculture:vineyard:WeatherStation;1","location").
property_value_defined("dtmi:agriculture:vineyard:Winery;1","wineryId").
property_value_defined("dtmi:agriculture:vineyard:Winery;1","capacity").
"""


MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "models")


PRIMITIVE_SCHEMAS = {
    "boolean", "date", "dateTime", "double", "duration", "float",
    "integer", "long", "string", "time",
}


def schema_id(schema, owner_id, name):
    if isinstance(schema, str):
        return f'"{schema}"'
    if isinstance(schema, dict) and "@id" in schema:
        return f'"{schema["@id"]}"'
    return f'({owner_id}, "{name}")'


def process_schema(sid, schema, facts):
    if isinstance(schema, str):
        return
    t = schema.get("@type")
    if t == "Enum":
        vs = schema_id(schema.get("valueSchema", "string"), sid, "value")
        facts.append(f'enum({sid}, {vs}).')
        for ev in schema.get("enumValues", []):
            val = f'"{ev["enumValue"]}"' if isinstance(ev["enumValue"], str) else str(ev["enumValue"])
            facts.append(f'enum_value({sid}, "{ev["name"]}", {val}).')
    elif t == "Object":
        facts.append(f'object({sid}).')
        for field in schema.get("fields", []):
            fsid = schema_id(field.get("schema", "string"), sid, field["name"])
            facts.append(f'has_field({sid}, "{field["name"]}", {fsid}).')
            process_schema(fsid, field.get("schema", "string"), facts)
    elif t == "Array":
        esid = schema_id(schema.get("elementSchema", "string"), sid, "element")
        facts.append(f'array({sid}, {esid}).')
        process_schema(esid, schema.get("elementSchema", "string"), facts)
    elif t == "Map":
        vsid = schema_id(schema.get("mapValue", {}).get("schema", "string"), sid, "value")
        facts.append(f'map({sid}, {vsid}).')


def parse_dtdl_to_facts(model_path):
    """Convert a DTDL JSON file to ASP facts for debug.lp."""
    with open(model_path) as f:
        data = json.load(f)
    items = data if isinstance(data, list) else [data]
    facts = []
    all_iids = set()
    for iface in items:
        iid = f'"{iface["@id"]}"'
        all_iids.add(iface["@id"])
        facts.append(f'interface({iid}).')
        for idx, c in enumerate(iface.get("contents", [])):
            raw_type = c["@type"]
            t = raw_type[0] if isinstance(raw_type, list) else raw_type
            name = c["name"]
            cid = f'({iid}, "{name}", {idx})'
            if t == "Property":
                facts.append(f'has_property({iid}, "{name}", {cid}).')
                facts.append(f'property({cid}).')
                sch = c.get("schema", "string")
                sid = schema_id(sch, iid, name)
                facts.append(f'schema({cid}, {sid}).')
                process_schema(sid, sch, facts)
                if c.get("writable"):
                    facts.append(f'writable({cid}).')
                if isinstance(raw_type, list) and len(raw_type) > 1:
                    facts.append(f'semantic_type({cid}, "{raw_type[1]}").')
                if c.get("unit"):
                    facts.append(f'unit({cid}, "{c["unit"]}").')
            elif t == "Telemetry":
                facts.append(f'has_telemetry({iid}, "{name}", {cid}).')
                facts.append(f'telemetry({cid}).')
                sch = c.get("schema", "string")
                sid = schema_id(sch, iid, name)
                facts.append(f'schema({cid}, {sid}).')
                process_schema(sid, sch, facts)
                if isinstance(raw_type, list) and len(raw_type) > 1:
                    facts.append(f'semantic_type({cid}, "{raw_type[1]}").')
                if c.get("unit"):
                    facts.append(f'unit({cid}, "{c["unit"]}").')
            elif t == "Relationship":
                facts.append(f'has_relationship({iid}, "{name}", {cid}).')
                facts.append(f'relationship({cid}).')
                if "target" in c:
                    facts.append(f'target({cid}, "{c["target"]}").')
            elif t == "Component":
                facts.append(f'has_component({iid}, "{name}", {cid}).')
                facts.append(f'component({cid}).')
                sch = c.get("schema", "")
                if sch:
                    sid = schema_id(sch, cid, name)
                    facts.append(f'schema({cid}, {sid}).')
            elif t == "Command":
                facts.append(f'has_command({iid}, "{name}", {cid}).')
                facts.append(f'command({cid}).')
                if "request" in c:
                    req = c["request"]
                    rsid = schema_id(req.get("schema", "string"), iid, req.get("name", "request"))
                    facts.append(f'command_request({cid}, {rsid}).')
                    process_schema(rsid, req.get("schema", "string"), facts)
                if "response" in c:
                    resp = c["response"]
                    rpsid = schema_id(resp.get("schema", "string"), iid, resp.get("name", "response"))
                    facts.append(f'command_response({cid}, {rpsid}).')
                    process_schema(rpsid, resp.get("schema", "string"), facts)
        extends = iface.get("extends", [])
        if isinstance(extends, str):
            extends = [extends]
        for parent in extends:
            facts.append(f'extends({iid}, "{parent}").')
    return "\n".join(facts)


def run_debug_lp():
    """Run debug.lp on vineyard facts + new model files, return __debug__ atoms."""
    with open(DEBUG_LP) as f:
        debug_program = f.read() + "\n#show __debug__/3."

    all_atoms = []

    # Original vineyard facts (11 diagnostics, IDs 1-11)
    ctl = clingo.Control(["--models=1", "--warn=none"])
    ctl.add("base", [], VINEYARD_FACTS)
    ctl.add("base", [], debug_program)
    ctl.ground([("base", [])])
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "__debug__":
                    all_atoms.append(("vineyard_original", atom))

    # New models with injected errors (IDs 15+)
    if os.path.isdir(MODELS_DIR):
        for fname in sorted(os.listdir(MODELS_DIR)):
            if not fname.endswith(".json"):
                continue
            facts = parse_dtdl_to_facts(os.path.join(MODELS_DIR, fname))
            ctl = clingo.Control(["--models=1", "--warn=none"])
            ctl.add("base", [], facts)
            ctl.add("base", [], debug_program)
            ctl.ground([("base", [])])
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    for atom in model.symbols(shown=True):
                        if atom.name == "__debug__":
                            all_atoms.append((fname, atom))

    return all_atoms


def sym_to_str(sym):
    """Extract a readable string from a clingo symbol (string or compound)."""
    if sym.type == clingo.SymbolType.String:
        return sym.string
    # compound tuple like (interface_id, rel_name, idx) — find last string arg
    if sym.type == clingo.SymbolType.Function and sym.arguments:
        for arg in reversed(sym.arguments):
            if arg.type == clingo.SymbolType.String:
                return arg.string
    return str(sym)


def atom_to_error_string(atom):
    """Replicates error_templates from +Debug.svelte."""
    template_key = atom.arguments[0].string
    if template_key == "undefined_target":
        rel = sym_to_str(atom.arguments[1])
        target = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Relationship '{rel}' references undefined interface '{target}'\n"
            f"Check DTDL model or add missing interface definition"
        )
    elif template_key == "missing_required_property":
        dtdl_interface = sym_to_str(atom.arguments[1])
        prop = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{dtdl_interface}' missing required property '{prop}'\n"
            f"Add property definition or mark as optional"
        )
    elif template_key == "extends_undefined":
        iface = sym_to_str(atom.arguments[1])
        parent = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' extends undefined interface '{parent}'\n"
            f"Add missing interface definition or remove the extends declaration"
        )
    elif template_key == "duplicate_property_name":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' has duplicate property name '{name}'\n"
            f"Remove or rename one of the duplicate property definitions"
        )
    elif template_key == "duplicate_telemetry_name":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' has duplicate telemetry name '{name}'\n"
            f"Remove or rename one of the duplicate telemetry definitions"
        )
    elif template_key == "self_referencing_relationship":
        iface = sym_to_str(atom.arguments[1])
        rel = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' has self-referencing relationship '{rel}'\n"
            f"Update the relationship target to a different interface"
        )
    elif template_key == "component_schema_undefined":
        iface = sym_to_str(atom.arguments[1])
        comp = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' component '{comp}' references undefined schema\n"
            f"Add missing interface definition for the component schema"
        )
    elif template_key == "duplicate_relationship_name":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' has duplicate relationship name '{name}'\n"
            f"Remove or rename one of the duplicate relationship definitions"
        )
    elif template_key == "ambiguous_name":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' uses '{name}' as both a property and a telemetry\n"
            f"Rename one of the two to avoid the ambiguity"
        )
    elif template_key == "circular_extends":
        iface = sym_to_str(atom.arguments[1])
        return (
            f"ERROR: Interface '{iface}' is part of a circular extends chain\n"
            f"Remove the extends declaration that creates the cycle"
        )
    elif template_key == "ambiguous_name_rel":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' uses '{name}' as both a relationship and a property or telemetry\n"
            f"Rename the relationship or the property/telemetry to avoid the clash"
        )
    elif template_key == "duplicate_command_name":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' has duplicate command name '{name}'\n"
            f"Remove or rename one of the duplicate command definitions"
        )
    elif template_key == "ambiguous_name_cmd":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' uses '{name}' as both a command and a property or telemetry\n"
            f"Rename the command or the property/telemetry to remove the ambiguity"
        )
    elif template_key == "component_self_reference":
        iface = sym_to_str(atom.arguments[1])
        comp = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' component '{comp}' references its own containing interface as schema\n"
            f"Update the component schema to point to a different interface"
        )
    elif template_key == "inherited_name_conflict":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' redefines inherited member '{name}' already declared in a parent interface\n"
            f"Remove the redefinition or rename the member to avoid shadowing the inherited declaration"
        )
    elif template_key == "deep_extends_chain":
        iface = sym_to_str(atom.arguments[1])
        return (
            f"ERROR: Interface '{iface}' is part of an extends chain deeper than 3 levels\n"
            f"Flatten the hierarchy or extract shared members into a common base interface"
        )
    elif template_key == "property_schema_undefined":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' property '{name}' references an undefined schema\n"
            f"Replace the schema with a primitive type or add the missing interface/schema definition"
        )
    elif template_key == "enum_no_values":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' member '{name}' declares an Enum schema with no enumValues\n"
            f"Add at least one enumValue entry to the Enum definition"
        )
    elif template_key == "object_no_fields":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' member '{name}' declares an Object schema with no fields\n"
            f"Add at least one field to the Object definition"
        )
    elif template_key == "isolated_interface":
        iface = sym_to_str(atom.arguments[1])
        return (
            f"ERROR: Interface '{iface}' is never referenced by any other interface (no relationship target, extends, or component schema)\n"
            f"Either remove the interface or add a reference to it from another interface"
        )
    elif template_key == "unit_without_semantic_type":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' member '{name}' declares a unit but no semantic type\n"
            f"Add a semantic type (e.g. Temperature, Humidity) alongside the unit declaration"
        )
    elif template_key == "semantic_type_without_unit":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' member '{name}' declares a semantic type but no unit\n"
            f"Add a unit (e.g. degreeCelsius, kilogram) alongside the semantic type declaration"
        )
    elif template_key == "command_request_schema_undefined":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' command '{name}' request payload references an undefined schema\n"
            f"Replace the schema with a primitive type or add the missing schema definition"
        )
    elif template_key == "command_response_schema_undefined":
        iface = sym_to_str(atom.arguments[1])
        name = sym_to_str(atom.arguments[2])
        return (
            f"ERROR: Interface '{iface}' command '{name}' response payload references an undefined schema\n"
            f"Replace the schema with a primitive type or add the missing schema definition"
        )
    elif template_key == "max_multiplicity_exceeded":
        rel = sym_to_str(atom.arguments[1])
        count = sym_to_str(atom.arguments[2])
        max_ = sym_to_str(atom.arguments[3])
        overflow = int(count) - int(max_)
        return (
            f"ERROR: Relationship '{rel}' exceeds maximum multiplicity\n"
            f"Current: {count}, Maximum: {max_}\nRemove {overflow} instances"
        )
    elif template_key == "external_interface_reference":
        ref = sym_to_str(atom.arguments[1])
        return (
            f"WARNING: Interface '{ref}' is referenced but not defined in this model set\n"
            f"Ensure the referenced interface is provided in the full deployment model set"
        )
    else:
        return f"ERROR: {atom}"


def atom_to_structured_context(atom):
    """Replicates structuredContext from +Debug.svelte tryToFixWithLLM()."""
    key = atom.arguments[0].string
    iface = sym_to_str(atom.arguments[1]) if len(atom.arguments) > 1 else ""
    arg2 = sym_to_str(atom.arguments[2]) if len(atom.arguments) > 2 else ""
    arg3 = sym_to_str(atom.arguments[3]) if len(atom.arguments) > 3 else ""
    problems = {
        "undefined_target":
            f"Diagnostic: undefined_target\nRelationship ID: {iface}\nReferenced target interface: {arg2}\nProblem: the target interface is not defined in the model.",
        "missing_required_property":
            f"Diagnostic: missing_required_property\nInterface ID: {iface}\nMissing property name: {arg2}\nProblem: the interface lacks a required property declared by domain constraints.",
        "extends_undefined":
            f"Diagnostic: extends_undefined\nInterface ID: {iface}\nMissing parent interface: {arg2}\nProblem: the interface extends an interface not defined in this model.",
        "duplicate_property_name":
            f"Diagnostic: duplicate_property_name\nInterface ID: {iface}\nDuplicate name: {arg2}\nProblem: DTDL requires all contents names to be unique within an interface.",
        "duplicate_telemetry_name":
            f"Diagnostic: duplicate_telemetry_name\nInterface ID: {iface}\nDuplicate name: {arg2}\nProblem: DTDL requires all contents names to be unique within an interface.",
        "duplicate_relationship_name":
            f"Diagnostic: duplicate_relationship_name\nInterface ID: {iface}\nDuplicate name: {arg2}\nProblem: DTDL requires all contents names to be unique within an interface.",
        "duplicate_command_name":
            f"Diagnostic: duplicate_command_name\nInterface ID: {iface}\nDuplicate name: {arg2}\nProblem: DTDL requires all contents names to be unique within an interface.",
        "ambiguous_name":
            f"Diagnostic: ambiguous_name\nInterface ID: {iface}\nAmbiguous name: {arg2}\nProblem: the same name is used by both a property and a telemetry element.",
        "ambiguous_name_rel":
            f"Diagnostic: ambiguous_name_rel\nInterface ID: {iface}\nAmbiguous name: {arg2}\nProblem: the same name is used by a relationship and another contents element.",
        "ambiguous_name_cmd":
            f"Diagnostic: ambiguous_name_cmd\nInterface ID: {iface}\nAmbiguous name: {arg2}\nProblem: the same name is used by a command and another contents element.",
        "self_referencing_relationship":
            f"Diagnostic: self_referencing_relationship\nInterface ID: {iface}\nRelationship name: {arg2}\nProblem: the relationship target points to the same interface that declares it.",
        "component_schema_undefined":
            f"Diagnostic: component_schema_undefined\nInterface ID: {iface}\nComponent name: {arg2}\nProblem: the component schema does not reference a defined Interface.",
        "component_self_reference":
            f"Diagnostic: component_self_reference\nInterface ID: {iface}\nComponent name: {arg2}\nProblem: the component schema references the containing interface itself.",
        "inherited_name_conflict":
            f"Diagnostic: inherited_name_conflict\nInterface ID: {iface}\nConflicting name: {arg2}\nProblem: an element name in this interface shadows an inherited element with the same name.",
        "circular_extends":
            f"Diagnostic: circular_extends\nInterface ID: {iface}\nProblem: the interface is part of a cyclic extends chain, which DTDL forbids.",
        "deep_extends_chain":
            f"Diagnostic: deep_extends_chain\nInterface ID: {iface}\nProblem: the extends chain exceeds 3 levels of inheritance. Consider flattening the hierarchy.",
        "property_schema_undefined":
            f"Diagnostic: property_schema_undefined\nInterface ID: {iface}\nProperty name: {arg2}\nProblem: the property schema is not a primitive type, enum, object, array, map, or known interface.",
        "enum_no_values":
            f"Diagnostic: enum_no_values\nInterface ID: {iface}\nElement name: {arg2}\nProblem: the Enum schema has no enumValues defined.",
        "object_no_fields":
            f"Diagnostic: object_no_fields\nInterface ID: {iface}\nElement name: {arg2}\nProblem: the Object schema has no fields defined.",
        "isolated_interface":
            f"Diagnostic: isolated_interface\nInterface ID: {iface}\nProblem: this interface is not referenced by any other interface (no target, extends, or component schema points to it).",
        "command_request_schema_undefined":
            f"Diagnostic: command_request_schema_undefined\nInterface ID: {iface}\nCommand name: {arg2}\nProblem: the command request schema is not a known type.",
        "command_response_schema_undefined":
            f"Diagnostic: command_response_schema_undefined\nInterface ID: {iface}\nCommand name: {arg2}\nProblem: the command response schema is not a known type.",
        "max_multiplicity_exceeded":
            f"Diagnostic: max_multiplicity_exceeded\nRelationship ID: {iface}\nCount: {arg2}, Maximum: {arg3}\nProblem: the relationship has more instances than its maxMultiplicity allows.",
        "external_interface_reference":
            f"Diagnostic: external_interface_reference\nReferenced DTMI: {iface}\nProblem: this interface is referenced (as target, extends, or schema) but is not defined in the current model set. Validate as an external dependency or add the missing interface.",
    }
    return problems.get(key, f"Diagnostic: {key}\nRaw atom: {atom}")


def build_prompts(atom):
    """Replicates prompt construction from +Debug.svelte tryToFixWithLLM()."""
    system = (
        "You are an expert in DTDL (Digital Twins Definition Language) v4. "
        "You receive structured diagnostic information from a symbolic ASP-based validator. "
        "Explain the root cause of the error and suggest a concrete, actionable fix "
        "including the corrected DTDL JSON-LD snippet. "
        "Do not invent properties or fields not defined in the DTDL v4 specification. "
        "Be concise: max 200 words."
    )
    user = atom_to_structured_context(atom)
    return system, user


def run():
    if not API_KEY:
        print("ERROR: set OPENROUTER_API_KEY environment variable.")
        return

    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    print("Running debug.lp with clingo...")
    debug_atoms = run_debug_lp()
    print(f"Found {len(debug_atoms)} __debug__ atoms.\n")

    results = []
    for i, (source, atom) in enumerate(debug_atoms, 1):
        template_key = atom.arguments[0].string
        error = atom_to_error_string(atom)
        system, user = build_prompts(atom)

        print(f"[{i:02d}/{len(debug_atoms)}] [{source}] {error.splitlines()[0][:60]}...")
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = response.choices[0].message.content.strip()

        results.append({
            "id": i,
            "source": source,
            "type": template_key,
            "atom": str(atom),
            "error_string": error,
            "system_prompt": system,
            "user_prompt": user,
            "response": text,
            "ratings": {
                "diagnostic_consistency": "",
                "repair_usefulness": "",
            },
        })
        print(f"       -> {len(text)} chars\n")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "responses", "grounded_responses.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(results)} responses to {out_path}")
    print("Fill in the 'ratings' fields (H/M/L), then run score.py")


if __name__ == "__main__":
    run()
