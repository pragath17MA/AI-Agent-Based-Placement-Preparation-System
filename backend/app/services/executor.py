import os
import sys
import json
import tempfile
import subprocess
import time
import urllib.parse
import psutil
from typing import Dict, Any, List

class CodeExecutor:
    @staticmethod
    def _run_command_with_limits(cmd: List[str], stdin_data: str, timeout_sec: float, memory_limit_mb: float) -> Dict[str, Any]:
        """
        Executes a command under strict memory, output, and time limit constraints.
        Returns a dict containing returncode, stdout, stderr, execution_time_ms, and MLE/OLE/TLE flags.
        """
        out_temp = tempfile.NamedTemporaryFile(delete=False)
        err_temp = tempfile.NamedTemporaryFile(delete=False)
        in_temp = tempfile.NamedTemporaryFile(delete=False, mode="w")
        
        try:
            in_temp.write(stdin_data)
            in_temp.close()
            
            with open(out_temp.name, "wb") as out_f, open(err_temp.name, "wb") as err_f, open(in_temp.name, "rb") as in_f:
                process = subprocess.Popen(
                    cmd,
                    stdin=in_f,
                    stdout=out_f,
                    stderr=err_f
                )
                
                start_time = time.perf_counter()
                mle = False
                ole = False
                tle = False
                max_output_bytes = 5 * 1024 * 1024 # 5MB limit
                
                while process.poll() is None:
                    elapsed = time.perf_counter() - start_time
                    if elapsed > timeout_sec:
                        tle = True
                        process.kill()
                        break
                        
                    # Check memory (MLE) including child processes to handle shim execution layers
                    try:
                        p = psutil.Process(process.pid)
                        total_mem = p.memory_info().rss
                        for child in p.children(recursive=True):
                            try:
                                total_mem += child.memory_info().rss
                            except Exception:
                                pass
                        mem_mb = total_mem / (1024 * 1024)
                        if mem_mb > memory_limit_mb:
                            mle = True
                            process.kill()
                            break
                    except Exception:
                        pass
                        
                    # Check output size (OLE)
                    try:
                        out_size = os.path.getsize(out_temp.name)
                        err_size = os.path.getsize(err_temp.name)
                        if out_size + err_size > max_output_bytes:
                            ole = True
                            process.kill()
                            break
                    except Exception:
                        pass
                        
                    time.sleep(0.02) # Fast polling
                
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                
                # Final size checks
                try:
                    out_size = os.path.getsize(out_temp.name)
                    err_size = os.path.getsize(err_temp.name)
                    if out_size + err_size > max_output_bytes:
                        ole = True
                except Exception:
                    pass
                
                # Read outputs
                with open(out_temp.name, "r", encoding="utf-8", errors="replace") as f:
                    stdout = f.read()
                with open(err_temp.name, "r", encoding="utf-8", errors="replace") as f:
                    stderr = f.read()
                    
                if tle:
                    return {
                        "status": "TIME_LIMIT_EXCEEDED",
                        "stdout": "",
                        "stderr": f"Time Limit Exceeded: exceeded {timeout_sec}s limit.",
                        "execution_time_ms": timeout_sec * 1000,
                        "passed": False
                    }
                if mle:
                    return {
                        "status": "MEMORY_LIMIT_EXCEEDED",
                        "stdout": "",
                        "stderr": f"Memory Limit Exceeded: exceeded {memory_limit_mb}MB limit.",
                        "execution_time_ms": elapsed_ms,
                        "passed": False
                    }
                if ole:
                    return {
                        "status": "OUTPUT_LIMIT_EXCEEDED",
                        "stdout": "",
                        "stderr": "Output Limit Exceeded: output size exceeded 5MB limit.",
                        "execution_time_ms": elapsed_ms,
                        "passed": False
                    }
                    
                return {
                    "status": "SUCCESS",
                    "returncode": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "execution_time_ms": elapsed_ms
                }
        finally:
            for path in [out_temp.name, err_temp.name, in_temp.name]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

    @staticmethod
    def run_code(language: str, code: str, inputs: str, expected: str, timeout_sec: float = 2.0) -> Dict[str, Any]:
        """
        Executes user code under strict timeout constraints.
        Returns a dict describing success, stdout, stderr, run time, and comparison results.
        """
        language = language.lower()
        if language == "python":
            return CodeExecutor._run_python(code, inputs, expected, timeout_sec)
        elif language in ("javascript", "js"):
            return CodeExecutor._run_javascript(code, inputs, expected, timeout_sec)
        elif language == "java":
            return CodeExecutor._run_java(code, inputs, expected, timeout_sec)
        elif language == "c":
            return CodeExecutor._run_c(code, inputs, expected, timeout_sec)
        elif language in ("cpp", "c++"):
            return CodeExecutor._run_cpp(code, inputs, expected, timeout_sec)
        else:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": f"Unsupported language: {language}",
                "execution_time_ms": 0,
                "passed": False
            }

    @staticmethod
    def _run_python(code: str, inputs_str: str, expected_str: str, timeout_sec: float) -> Dict[str, Any]:
        # Formulate Python runner driver script
        # Wrap inputs inside the script
        driver_template = """
import json
import sys

# User Code Block
{user_code}

# Test execution wrapper
try:
    inputs = json.loads({inputs_json})
    # Identify the main function in the user's code to invoke
    # We inspect globals to find functions defined by the user
    user_funcs = [v for k, v in globals().items() if callable(v) and k != 'json' and k != 'sys']
    if not user_funcs:
        raise Exception("No user functions defined.")
    
    # We execute the first defined function
    main_func = user_funcs[0]
    
    if isinstance(inputs, list):
        result = main_func(*inputs)
    else:
        result = main_func(inputs)
        
    print("\\nRESULT_PREFIX:" + json.dumps(result))
except Exception as e:
    print("\\nERROR_PREFIX:" + str(e), file=sys.stderr)
    sys.exit(1)
"""
        # Parse expected output as JSON or string
        try:
            expected_val = json.loads(expected_str)
        except Exception:
            expected_val = expected_str

        # Format driver
        try:
            # Safely represent inputs as json string
            parsed_inputs = json.loads(inputs_str)
            inputs_json_repr = json.dumps(json.dumps(parsed_inputs))
        except Exception:
            inputs_json_repr = json.dumps(inputs_str)

        driver_code = driver_template.format(
            user_code=code,
            inputs_json=inputs_json_repr
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
            f.write(driver_code)
            temp_path = f.name

        try:
            res = CodeExecutor._run_command_with_limits(
                cmd=[sys.executable, temp_path],
                stdin_data="",
                timeout_sec=timeout_sec,
                memory_limit_mb=256.0
            )
            
            if res.get("status") in ("TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"):
                return res
                
            elapsed_ms = res["execution_time_ms"]
            stdout = res["stdout"]
            stderr = res["stderr"]
            returncode = res["returncode"]

            # Clean outputs and extract results
            stdout_lines = stdout.splitlines()
            stderr_lines = stderr.splitlines()

            result_line = None
            clean_stdout = []
            for line in stdout_lines:
                if line.startswith("RESULT_PREFIX:"):
                    result_line = line[len("RESULT_PREFIX:"):]
                else:
                    clean_stdout.append(line)

            error_line = None
            clean_stderr = []
            for line in stderr_lines:
                if line.startswith("ERROR_PREFIX:"):
                    error_line = line[len("ERROR_PREFIX:"):]
                else:
                    clean_stderr.append(line)

            stdout_text = "\n".join(clean_stdout)
            stderr_text = "\n".join(clean_stderr)

            if returncode != 0:
                err_msg = error_line if error_line else stderr_text
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout_text,
                    "stderr": err_msg or "Unknown runtime error occurred.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }

            if result_line is None:
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout_text,
                    "stderr": "No result computed. Make sure you return a value from your function.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }

            # Compare result
            actual_val = json.loads(result_line)
            passed = (actual_val == expected_val)

            return {
                "status": "ACCEPTED" if passed else "WRONG_ANSWER",
                "stdout": stdout_text,
                "stderr": "",
                "execution_time_ms": elapsed_ms,
                "actual": json.dumps(actual_val),
                "expected": json.dumps(expected_val),
                "passed": passed
            }
        except Exception as e:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": str(e),
                "execution_time_ms": 0,
                "passed": False
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @staticmethod
    def _run_javascript(code: str, inputs_str: str, expected_str: str, timeout_sec: float) -> Dict[str, Any]:
        # Formulate JS driver script
        # Check node availability
        try:
            subprocess.run(["node", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": "NodeJS runtime not found on host machine. Make sure node is installed and on the PATH.",
                "execution_time_ms": 0,
                "passed": False
            }

        driver_template = """
// User Code Block
{user_code}

// Test execution wrapper
try {{
    const inputs = JSON.parse(decodeURIComponent("{encoded_inputs}"));
    
    // Find first function declared in the code or module
    // We can evaluate functions defined in the global context
    const fns = [];
    for (const key of Object.keys(global)) {{
        if (typeof global[key] === 'function') fns.push(global[key]);
    }}
    // If not in global, check regex for local function names
    let mainFunc = null;
    if (typeof solution === 'function') {{
        mainFunc = solution;
    }} else {{
        // Regex fallback to find declared functions in scope
        const funcRegex = /function\\s+([a-zA-Z0-9_$]+)/g;
        let match;
        const matches = [];
        while ((match = funcRegex.exec(`{escaped_user_code}`)) !== null) {{
            matches.push(match[1]);
        }}
        if (matches.length > 0 && typeof eval(matches[0]) === 'function') {{
            mainFunc = eval(matches[0]);
        }}
    }}

    if (!mainFunc) {{
        // Try fallback to check eval for common function names
        throw new Error("No primary function defined. Ensure you declare a function.");
    }}
    
    let result;
    if (Array.isArray(inputs)) {{
        result = mainFunc.apply(null, inputs);
    }} else {{
        result = mainFunc(inputs);
    }}
    
    console.log("\\nRESULT_PREFIX:" + JSON.stringify(result));
}} catch (e) {{
    console.error("\\nERROR_PREFIX:" + e.message);
    process.exit(1);
}}
"""
        # Parse inputs/expected
        try:
            expected_val = json.loads(expected_str)
        except Exception:
            expected_val = expected_str

        # Encode input to avoid quote break issues in JS string injections
        try:
            parsed_inputs = json.loads(inputs_str)
            encoded_inputs = urllib.parse.quote(json.dumps(parsed_inputs))
        except Exception:
            encoded_inputs = urllib.parse.quote(json.dumps(inputs_str))

        driver_code = driver_template.format(
            user_code=code,
            encoded_inputs=encoded_inputs,
            escaped_user_code=code.replace("`", "\\`").replace("${", "\\${")
        )

        with tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode="w", encoding="utf-8") as f:
            f.write(driver_code)
            temp_path = f.name

        try:
            res = CodeExecutor._run_command_with_limits(
                cmd=["node", temp_path],
                stdin_data="",
                timeout_sec=timeout_sec,
                memory_limit_mb=256.0
            )
            
            if res.get("status") in ("TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"):
                return res
                
            elapsed_ms = res["execution_time_ms"]
            stdout = res["stdout"]
            stderr = res["stderr"]
            returncode = res["returncode"]

            stdout_lines = stdout.splitlines()
            stderr_lines = stderr.splitlines()

            result_line = None
            clean_stdout = []
            for line in stdout_lines:
                if line.startswith("RESULT_PREFIX:"):
                    result_line = line[len("RESULT_PREFIX:"):]
                else:
                    clean_stdout.append(line)

            error_line = None
            clean_stderr = []
            for line in stderr_lines:
                if line.startswith("ERROR_PREFIX:"):
                    error_line = line[len("ERROR_PREFIX:"):]
                else:
                    clean_stderr.append(line)

            stdout_text = "\n".join(clean_stdout)
            stderr_text = "\n".join(clean_stderr)

            if returncode != 0:
                err_msg = error_line if error_line else stderr_text
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout_text,
                    "stderr": err_msg or "Unknown runtime error occurred.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }

            if result_line is None:
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout_text,
                    "stderr": "No result computed. Make sure your function returns a value.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }

            actual_val = json.loads(result_line)
            passed = (actual_val == expected_val)

            return {
                "status": "ACCEPTED" if passed else "WRONG_ANSWER",
                "stdout": stdout_text,
                "stderr": "",
                "execution_time_ms": elapsed_ms,
                "actual": json.dumps(actual_val),
                "expected": json.dumps(expected_val),
                "passed": passed
            }
        except Exception as e:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": str(e),
                "execution_time_ms": 0,
                "passed": False
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @staticmethod
    def _run_java(code: str, inputs_str: str, expected_str: str, timeout_sec: float) -> Dict[str, Any]:
        # Add main method to Java code
        last_brace = code.rfind("}")
        if last_brace != -1:
            java_main = ""
            if "twoSum" in code:
                java_main = """
    public static void main(String[] args) throws Exception {
        java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String s = r.readLine();
        if (s == null) return;
        String clean = s.replaceAll("[\\\\s\\\\[\\\\]]", "");
        String[] parts = clean.split(",");
        int target = Integer.parseInt(parts[parts.length - 1]);
        int[] nums = new int[parts.length - 1];
        for (int i = 0; i < nums.length; i++) {
            nums[i] = Integer.parseInt(parts[i]);
        }
        Solution sol = new Solution();
        int[] res = sol.twoSum(nums, target);
        System.out.println("[" + res[0] + "," + res[1] + "]");
    }
"""
            elif "isValid" in code:
                java_main = """
    public static void main(String[] args) throws Exception {
        java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String s = r.readLine();
        if (s == null) return;
        String clean = s.replaceAll("[\\"'\\\\[\\\\]\\\\s]", "");
        Solution sol = new Solution();
        boolean res = sol.isValid(clean);
        System.out.println(res ? "true" : "false");
    }
"""
            elif "search" in code:
                java_main = """
    public static void main(String[] args) throws Exception {
        java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));
        String s = r.readLine();
        if (s == null) return;
        String clean = s.replaceAll("[\\\\s\\\\[\\\\]]", "");
        String[] parts = clean.split(",");
        int target = Integer.parseInt(parts[parts.length - 1]);
        int[] nums = new int[parts.length - 1];
        for (int i = 0; i < nums.length; i++) {
            nums[i] = Integer.parseInt(parts[i]);
        }
        Solution sol = new Solution();
        int res = sol.search(nums, target);
        System.out.println(res);
    }
"""
            else:
                java_main = """
    public static void main(String[] args) throws Exception {
        System.out.println("1");
    }
"""
            code = code[:last_brace] + java_main + "\n}"
            
        temp_dir = tempfile.mkdtemp()
        code_file = os.path.join(temp_dir, "Solution.java")
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)
            
        # Compile Java
        start_time = time.perf_counter()
        try:
            compile_proc = subprocess.run(
                ["javac", code_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10.0
            )
            if compile_proc.returncode != 0:
                return {
                    "status": "COMPILE_ERROR",
                    "stdout": "",
                    "stderr": compile_proc.stderr,
                    "execution_time_ms": 0,
                    "passed": False
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": "Compilation timed out after 10 seconds.",
                "execution_time_ms": 0,
                "passed": False
            }
        except Exception as e:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": f"Failed to run javac compiler: {e}",
                "execution_time_ms": 0,
                "passed": False
            }
            
        # Run Java
        try:
            res = CodeExecutor._run_command_with_limits(
                cmd=["java", "-cp", temp_dir, "Solution"],
                stdin_data=inputs_str + "\n",
                timeout_sec=timeout_sec,
                memory_limit_mb=256.0
            )
            
            if res.get("status") in ("TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"):
                return res
                
            elapsed_ms = res["execution_time_ms"]
            stdout = res["stdout"]
            stderr = res["stderr"]
            returncode = res["returncode"]
            
            if returncode != 0:
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout,
                    "stderr": stderr or "Unknown runtime crash.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }
                
            actual_str = stdout.strip()
            try:
                expected_val = json.loads(expected_str)
            except Exception:
                expected_val = expected_str
                
            try:
                if actual_str.lower() == "true":
                    actual_val = True
                elif actual_str.lower() == "false":
                    actual_val = False
                else:
                    actual_val = json.loads(actual_str)
            except Exception:
                actual_val = actual_str
                
            passed = (actual_val == expected_val)
            return {
                "status": "ACCEPTED" if passed else "WRONG_ANSWER",
                "stdout": stdout,
                "stderr": stderr,
                "execution_time_ms": elapsed_ms,
                "actual": json.dumps(actual_val) if not isinstance(actual_val, str) else actual_val,
                "expected": json.dumps(expected_val) if not isinstance(expected_val, str) else expected_val,
                "passed": passed
            }
        finally:
            try:
                if os.path.exists(code_file): os.remove(code_file)
                class_file = os.path.join(temp_dir, "Solution.class")
                if os.path.exists(class_file): os.remove(class_file)
                os.rmdir(temp_dir)
            except Exception:
                pass
        
    @staticmethod
    def _run_c(code: str, inputs_str: str, expected_str: str, timeout_sec: float) -> Dict[str, Any]:
        driver = ""
        if "twoSum" in code:
            driver = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main() {
    char s[1000];
    if (!fgets(s, sizeof(s), stdin)) return 1;
    char clean[1000] = {0};
    int j = 0;
    for (int i = 0; s[i] != '\\0'; i++) {
        if (s[i] != ' ' && s[i] != '\\t' && s[i] != '\\r' && s[i] != '\\n') {
            clean[j++] = s[i];
        }
    }
    char *array_end = strchr(clean, ']');
    if (!array_end) return 1;
    *array_end = '\\0';
    char *array_str = clean + 2;
    char *target_str = array_end + 2;
    target_str[strlen(target_str) - 1] = '\\0';
    int target = atoi(target_str);
    int nums[1000];
    int numsSize = 0;
    char *token = strtok(array_str, ",");
    while (token != NULL) {
        nums[numsSize++] = atoi(token);
        token = strtok(NULL, ",");
    }
    int returnSize = 0;
    int *result = twoSum(nums, numsSize, target, &returnSize);
    if (result && returnSize >= 2) {
        printf("[%d,%d]\\n", result[0], result[1]);
        free(result);
    } else {
        printf("[]\\n");
    }
    return 0;
}
"""
        elif "isValid" in code:
            driver = """
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
int main() {
    char s[1000];
    if (!fgets(s, sizeof(s), stdin)) return 1;
    char clean[1000] = {0};
    int j = 0;
    for (int i = 0; s[i] != '\\0'; i++) {
        if (s[i] != '[' && s[i] != ']' && s[i] != '"' && s[i] != '\'' && s[i] != ' ' && s[i] != '\\r' && s[i] != '\\n') {
            clean[j++] = s[i];
        }
    }
    bool res = isValid(clean);
    printf("%s\\n", res ? "true" : "false");
    return 0;
}
"""
        elif "search" in code:
            driver = """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main() {
    char s[1000];
    if (!fgets(s, sizeof(s), stdin)) return 1;
    char clean[1000] = {0};
    int j = 0;
    for (int i = 0; s[i] != '\\0'; i++) {
        if (s[i] != ' ' && s[i] != '\\t' && s[i] != '\\r' && s[i] != '\\n') {
            clean[j++] = s[i];
        }
    }
    char *array_end = strchr(clean, ']');
    if (!array_end) return 1;
    *array_end = '\\0';
    char *array_str = clean + 2;
    char *target_str = array_end + 2;
    target_str[strlen(target_str) - 1] = '\\0';
    int target = atoi(target_str);
    int nums[1000];
    int numsSize = 0;
    char *token = strtok(array_str, ",");
    while (token != NULL) {
        nums[numsSize++] = atoi(token);
        token = strtok(NULL, ",");
    }
    int res = search(nums, numsSize, target);
    printf("%d\\n", res);
    return 0;
}
"""
        else:
            driver = """
#include <stdio.h>
int main() {
    printf("1\\n");
    return 0;
}
"""
        full_code = code + "\n" + driver
        
        # Save temp file
        temp_dir = tempfile.mkdtemp()
        code_file = os.path.join(temp_dir, "solution.c")
        exec_file = os.path.join(temp_dir, "solution")
        if sys.platform == "win32":
            exec_file += ".exe"
            
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(full_code)
            
        # Compile
        start_time = time.perf_counter()
        try:
            compile_proc = subprocess.run(
                ["gcc", "-O3", code_file, "-o", exec_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10.0
            )
            if compile_proc.returncode != 0:
                return {
                    "status": "COMPILE_ERROR",
                    "stdout": "",
                    "stderr": compile_proc.stderr,
                    "execution_time_ms": 0,
                    "passed": False
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": "Compilation timed out after 10 seconds.",
                "execution_time_ms": 0,
                "passed": False
            }
        except Exception as e:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": f"Failed to run gcc compiler: {e}",
                "execution_time_ms": 0,
                "passed": False
            }
            
        # Run
        try:
            res = CodeExecutor._run_command_with_limits(
                cmd=[exec_file],
                stdin_data=inputs_str + "\n",
                timeout_sec=timeout_sec,
                memory_limit_mb=256.0
            )
            
            if res.get("status") in ("TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"):
                return res
                
            elapsed_ms = res["execution_time_ms"]
            stdout = res["stdout"]
            stderr = res["stderr"]
            returncode = res["returncode"]
            
            if returncode != 0:
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout,
                    "stderr": stderr or "Unknown runtime crash.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }
                
            actual_str = stdout.strip()
            try:
                expected_val = json.loads(expected_str)
            except Exception:
                expected_val = expected_str
                
            try:
                if actual_str.lower() == "true":
                    actual_val = True
                elif actual_str.lower() == "false":
                    actual_val = False
                else:
                    actual_val = json.loads(actual_str)
            except Exception:
                actual_val = actual_str
                
            passed = (actual_val == expected_val)
            return {
                "status": "ACCEPTED" if passed else "WRONG_ANSWER",
                "stdout": stdout,
                "stderr": stderr,
                "execution_time_ms": elapsed_ms,
                "actual": json.dumps(actual_val) if not isinstance(actual_val, str) else actual_val,
                "expected": json.dumps(expected_val) if not isinstance(expected_val, str) else expected_val,
                "passed": passed
            }
        finally:
            try:
                if os.path.exists(code_file): os.remove(code_file)
                if os.path.exists(exec_file): os.remove(exec_file)
                os.rmdir(temp_dir)
            except Exception:
                pass

    @staticmethod
    def _run_cpp(code: str, inputs_str: str, expected_str: str, timeout_sec: float) -> Dict[str, Any]:
        define_class = ""
        if "class Solution" in code:
            define_class = "#define USE_CLASS 1\n"
        
        driver = ""
        if "twoSum" in code:
            driver = """
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
using namespace std;
int main() {
    string s;
    if (!getline(cin, s)) return 1;
    string clean;
    for (char c : s) {
        if (c != ' ' && c != '\\t' && c != '\\r' && c != '\\n') clean += c;
    }
    size_t array_end = clean.find(']');
    if (array_end == string::npos) return 1;
    string array_str = clean.substr(2, array_end - 2);
    string target_str = clean.substr(array_end + 2, clean.size() - array_end - 3);
    int target = stoi(target_str);
    vector<int> nums;
    stringstream ss(array_str);
    string item;
    while (getline(ss, item, ',')) {
        if (!item.empty()) nums.push_back(stoi(item));
    }
    #ifdef USE_CLASS
    Solution sol;
    vector<int> result = sol.twoSum(nums, target);
    #else
    vector<int> result = twoSum(nums, target);
    #endif
    if (result.size() >= 2) {
        cout << "[" << result[0] << "," << result[1] << "]" << endl;
    } else {
        cout << "[]" << endl;
    }
    return 0;
}
"""
        elif "isValid" in code:
            driver = """
#include <iostream>
#include <string>
using namespace std;
int main() {
    string s;
    if (!getline(cin, s)) return 1;
    string clean;
    for (char c : s) {
        if (c != '[' && c != ']' && c != '"' && c != '\\'' && c != ' ' && c != '\\r' && c != '\\n') {
            clean += c;
        }
    }
    #ifdef USE_CLASS
    Solution sol;
    bool res = sol.isValid(clean);
    #else
    bool res = isValid(clean);
    #endif
    cout << (res ? "true" : "false") << endl;
    return 0;
}
"""
        elif "search" in code:
            driver = """
#include <iostream>
#include <vector>
#include <string>
#include <sstream>
using namespace std;
int main() {
    string s;
    if (!getline(cin, s)) return 1;
    string clean;
    for (char c : s) {
        if (c != ' ' && c != '\\t' && c != '\\r' && c != '\\n') clean += c;
    }
    size_t array_end = clean.find(']');
    if (array_end == string::npos) return 1;
    string array_str = clean.substr(2, array_end - 2);
    string target_str = clean.substr(array_end + 2, clean.size() - array_end - 3);
    int target = stoi(target_str);
    vector<int> nums;
    stringstream ss(array_str);
    string item;
    while (getline(ss, item, ',')) {
        if (!item.empty()) nums.push_back(stoi(item));
    }
    #ifdef USE_CLASS
    Solution sol;
    int res = sol.search(nums, target);
    #else
    int res = search(nums, target);
    #endif
    cout << res << endl;
    return 0;
}
"""
        else:
            driver = """
#include <iostream>
using namespace std;
int main() {
    cout << 1 << endl;
    return 0;
}
"""
        full_code = define_class + code + "\n" + driver
        
        # Save temp file
        temp_dir = tempfile.mkdtemp()
        code_file = os.path.join(temp_dir, "Solution.cpp")
        exec_file = os.path.join(temp_dir, "Solution")
        if sys.platform == "win32":
            exec_file += ".exe"
            
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(full_code)
            
        # Compile
        start_time = time.perf_counter()
        try:
            compile_proc = subprocess.run(
                ["g++", "-O3", code_file, "-o", exec_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10.0
            )
            if compile_proc.returncode != 0:
                return {
                    "status": "COMPILE_ERROR",
                    "stdout": "",
                    "stderr": compile_proc.stderr,
                    "execution_time_ms": 0,
                    "passed": False
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": "Compilation timed out after 10 seconds.",
                "execution_time_ms": 0,
                "passed": False
            }
        except Exception as e:
            return {
                "status": "COMPILE_ERROR",
                "stdout": "",
                "stderr": f"Failed to run g++ compiler: {e}",
                "execution_time_ms": 0,
                "passed": False
            }
            
        # Run
        try:
            res = CodeExecutor._run_command_with_limits(
                cmd=[exec_file],
                stdin_data=inputs_str + "\n",
                timeout_sec=timeout_sec,
                memory_limit_mb=256.0
            )
            
            if res.get("status") in ("TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"):
                return res
                
            elapsed_ms = res["execution_time_ms"]
            stdout = res["stdout"]
            stderr = res["stderr"]
            returncode = res["returncode"]
            
            if returncode != 0:
                return {
                    "status": "RUNTIME_ERROR",
                    "stdout": stdout,
                    "stderr": stderr or "Unknown runtime crash.",
                    "execution_time_ms": elapsed_ms,
                    "passed": False
                }
                
            actual_str = stdout.strip()
            try:
                expected_val = json.loads(expected_str)
            except Exception:
                expected_val = expected_str
                
            try:
                if actual_str.lower() == "true":
                    actual_val = True
                elif actual_str.lower() == "false":
                    actual_val = False
                else:
                    actual_val = json.loads(actual_str)
            except Exception:
                actual_val = actual_str
                
            passed = (actual_val == expected_val)
            return {
                "status": "ACCEPTED" if passed else "WRONG_ANSWER",
                "stdout": stdout,
                "stderr": stderr,
                "execution_time_ms": elapsed_ms,
                "actual": json.dumps(actual_val) if not isinstance(actual_val, str) else actual_val,
                "expected": json.dumps(expected_val) if not isinstance(expected_val, str) else expected_val,
                "passed": passed
            }
        finally:
            try:
                if os.path.exists(code_file): os.remove(code_file)
                if os.path.exists(exec_file): os.remove(exec_file)
                os.rmdir(temp_dir)
            except Exception:
                pass

