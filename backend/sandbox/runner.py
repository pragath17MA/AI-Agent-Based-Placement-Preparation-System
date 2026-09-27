import json
import sys
import os

def main():
    if len(sys.argv) < 3:
        print("ERROR_PREFIX:Missing arguments")
        sys.exit(1)
    
    code_path = sys.argv[1]
    inputs_json = sys.argv[2]
    
    # Read user code
    with open(code_path, 'r', encoding='utf-8') as f:
        user_code = f.read()

    # Execute user code in a controlled namespace
    namespace = {}
    try:
        exec(user_code, namespace)
    except Exception as e:
        print(f"ERROR_PREFIX:Compilation Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    try:
        inputs = json.loads(inputs_json)
        
        # Find the first user-defined function
        user_funcs = [v for k, v in namespace.items() if callable(v) and not k.startswith('__')]
        if not user_funcs:
            raise Exception("No user functions defined.")
            
        main_func = user_funcs[0]
        
        if isinstance(inputs, list):
            result = main_func(*inputs)
        else:
            result = main_func(inputs)
            
        print("\\nRESULT_PREFIX:" + json.dumps(result))
    except Exception as e:
        print("\\nERROR_PREFIX:" + str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
