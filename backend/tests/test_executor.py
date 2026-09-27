import pytest
from app.services.executor import CodeExecutor

def test_python_executor_success():
    code = """
def twoSum(nums, target):
    lookup = {}
    for i, num in enumerate(nums):
        diff = target - num
        if diff in lookup:
            return [lookup[diff], i]
        lookup[num] = i
    return []
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected)
    
    assert result["status"] == "ACCEPTED"
    assert result["passed"] is True
    assert "actual" in result
    assert result["actual"] == "[0, 1]"

def test_python_executor_wrong_answer():
    code = """
def twoSum(nums, target):
    return [0, 0] # Incorrect output
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected)
    
    assert result["status"] == "WRONG_ANSWER"
    assert result["passed"] is False
    assert result["actual"] == "[0, 0]"

def test_python_executor_runtime_error():
    code = """
def twoSum(nums, target):
    raise ValueError("Custom calculation crash")
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected)
    
    assert result["status"] == "RUNTIME_ERROR"
    assert result["passed"] is False
    assert "Custom calculation crash" in result["stderr"]

def test_python_executor_timeout():
    code = """
def twoSum(nums, target):
    import time
    while True:
        time.sleep(0.1)
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected, timeout_sec=0.5)
    
    assert result["status"] == "TIME_LIMIT_EXCEEDED"
    assert result["passed"] is False

import shutil

def test_js_executor_success():
    if not shutil.which("node"):
        pytest.skip("NodeJS runtime not found")
    code = "function twoSum(nums, target) { return [0, 1]; }"
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("javascript", code, inputs, expected)
    assert result["status"] == "ACCEPTED"
    assert result["passed"] is True

def test_cpp_executor_success():
    if not shutil.which("g++"):
        pytest.skip("g++ compiler not found")
    code = """
#include <vector>
using namespace std;
class Solution {
public:
    vector<int> twoSum(vector<int>& nums, int target) {
        return {0, 1};
    }
};
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("cpp", code, inputs, expected)
    assert result["status"] == "ACCEPTED"
    assert result["passed"] is True

def test_c_executor_success():
    if not shutil.which("gcc"):
        pytest.skip("gcc compiler not found")
    code = """
#include <stdlib.h>
int* twoSum(int* nums, int numsSize, int target, int* returnSize) {
    int* res = (int*)malloc(2 * sizeof(int));
    res[0] = 0;
    res[1] = 1;
    *returnSize = 2;
    return res;
}
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("c", code, inputs, expected)
    assert result["status"] == "ACCEPTED"
    assert result["passed"] is True

def test_java_executor_success():
    if not shutil.which("javac") or not shutil.which("java"):
        pytest.skip("JDK not found")
    code = """
class Solution {
    public int[] twoSum(int[] nums, int target) {
        return new int[]{0, 1};
    }
}
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("java", code, inputs, expected)
    assert result["status"] == "ACCEPTED"
    assert result["passed"] is True

def test_python_executor_memory_limit():
    code = """
def twoSum(nums, target):
    import time
    a = [0] * (150 * 1024 * 1024) # Allocate 1.2GB+
    for i in range(0, len(a), 1024):
        a[i] = i
    time.sleep(0.5) # Hold memory active so polling catches it
    return []
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected, timeout_sec=5.0)
    assert result["status"] == "MEMORY_LIMIT_EXCEEDED"

def test_python_executor_output_limit():
    code = """
def twoSum(nums, target):
    for _ in range(500000):
        print("A" * 50)
    return []
"""
    inputs = "[[2, 7, 11, 15], 9]"
    expected = "[0, 1]"
    result = CodeExecutor.run_code("python", code, inputs, expected, timeout_sec=5.0)
    assert result["status"] == "OUTPUT_LIMIT_EXCEEDED"

