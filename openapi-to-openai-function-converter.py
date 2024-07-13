import json
import yaml
from collections.abc import MutableMapping

def load_openapi_spec(file_path):
    with open(file_path, 'r') as file:
        if file_path.endswith('.json'):
            return json.load(file)
        elif file_path.endswith('.yaml') or file_path.endswith('.yml'):
            return yaml.safe_load(file)
        else:
            raise ValueError("Unsupported file format")

def resolve_ref(ref, spec):
    keys = ref.lstrip('#/').split('/')
    result = spec
    for key in keys:
        result = result[key]
    return result

def extract_properties(schema, openapi_spec):
    properties = {}
    required = []

    if '$ref' in schema:
        schema = resolve_ref(schema['$ref'], openapi_spec)

    if 'properties' in schema:
        props = schema['properties']
    else:
        props = {}
    
    required = schema.get('required', [])

    for prop_name, prop_details in props.items():
        if '$ref' in prop_details:
            prop_details = resolve_ref(prop_details['$ref'], openapi_spec)
        prop_type = prop_details.get('type', 'object')
        properties[prop_name] = {
            "type": prop_type,
            "description": prop_details.get('description', '')
        }
    
    return properties, required

def transform_to_openai_format(openapi_spec):
    openai_functions = []
    openai_function_codes = []

    for path, methods in openapi_spec['paths'].items():
        for method, details in methods.items():
            function = {
                "name": details['operationId'],
                "description": details.get('summary', ''),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }

            # Handle parameters
            if 'parameters' in details:
                for param in details['parameters']:
                    if '$ref' in param:
                        param = resolve_ref(param['$ref'], openapi_spec)
                    param_name = param['name']
                    param_schema = param.get('schema', {})
                    if '$ref' in param_schema:
                        param_schema = resolve_ref(param_schema['$ref'], openapi_spec)
                    param_type = param_schema.get('type', 'string')  # Default to 'string' if type is missing
                    param_details = {
                        "type": param_type,
                        "description": param.get('description', '')
                    }
                    function['parameters']['properties'][param_name] = param_details
                    if param.get('required', False):
                        function['parameters']['required'].append(param_name)
            
            # Handle request body
            if 'requestBody' in details:
                request_body = details['requestBody']
                if '$ref' in request_body:
                    request_body = resolve_ref(request_body['$ref'], openapi_spec)
                content = request_body['content']
                for content_type, schema_obj in content.items():
                    schema = schema_obj['schema']
                    if '$ref' in schema:
                        schema = resolve_ref(schema['$ref'], openapi_spec)
                    properties, required = extract_properties(schema, openapi_spec)
                    function['parameters']['properties'].update(properties)
                    function['parameters']['required'].extend(required)

            # Create the corresponding function code
            func_name = details['operationId']
            path_params = [param['name'] for param in details.get('parameters', []) if param.get('in') == 'path']
            query_params = [param['name'] for param in details.get('parameters', []) if param.get('in') == 'query']
            request_body_params = details.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {}).get('properties', {})
            
            function_code = f"def {func_name}({', '.join(path_params + query_params + list(request_body_params.keys()))}):\n"
            function_code += f"    url = '{openapi_spec['servers'][0]['url']}{path}'\n"
            function_code += "    headers = {'Content-Type': 'application/json'}\n"
            
            if query_params:
                function_code += f"    params = {{{', '.join([f'\"{param}\": {param}' for param in query_params])}}}\n"
            else:
                function_code += "    params = {}\n"

            if request_body_params:
                function_code += f"    body = {{{', '.join([f'\"{param}\": {param}' for param in request_body_params.keys()])}}}\n"
                function_code += "    response = requests.post(url, headers=headers, params=params, json=body)\n"
            else:
                function_code += "    response = requests.get(url, headers=headers, params=params)\n"

            function_code += "    return response.json()\n"
            openai_function_codes.append(function_code)
            
            openai_functions.append(function)

    return openai_functions, openai_function_codes

def main():
    openapi_spec_path = 'part.yaml'  # Change this to your file path
    openapi_spec = load_openapi_spec(openapi_spec_path)
    openai_functions, openai_function_codes = transform_to_openai_format(openapi_spec)

    final_output = [openai_functions, openai_function_codes]

    with open('openai_format_functions.json', 'w') as output_file:
        json.dump(final_output, output_file, indent=2)

    print(json.dumps(final_output, indent=2))

if __name__ == "__main__":
    main()
