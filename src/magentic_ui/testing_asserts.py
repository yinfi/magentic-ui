from typing import Any, Optional

class CustomAssertionError(AssertionError):
    """Custom assertion error to distinguish from other AssertionErrors if needed."""
    pass

def assert_equal(actual: Any, expected: Any, message: Optional[str] = None) -> None:
    """Asserts that actual is equal to expected."""
    if actual != expected:
        error_message = f"Assertion Failed: Expected '{expected}', but got '{actual}'."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_not_equal(actual: Any, expected: Any, message: Optional[str] = None) -> None:
    """Asserts that actual is not equal to expected."""
    if actual == expected:
        error_message = f"Assertion Failed: Expected not to be '{expected}', but it was."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_true(condition: bool, message: Optional[str] = None) -> None:
    """Asserts that condition is true."""
    if not condition:
        error_message = "Assertion Failed: Expected condition to be True, but it was False."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_false(condition: bool, message: Optional[str] = None) -> None:
    """Asserts that condition is false."""
    if condition:
        error_message = "Assertion Failed: Expected condition to be False, but it was True."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_contains(text: str, substring: str, message: Optional[str] = None) -> None:
    """Asserts that text contains substring."""
    if not isinstance(text, str) or not isinstance(substring, str):
        raise CustomAssertionError(f"Assertion Failed: Both text and substring must be strings. Got text: {type(text)}, substring: {type(substring)}")
    if substring not in text:
        error_message = f"Assertion Failed: Expected text '{text}' to contain substring '{substring}', but it did not."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_not_contains(text: str, substring: str, message: Optional[str] = None) -> None:
    """Asserts that text does not contain substring."""
    if not isinstance(text, str) or not isinstance(substring, str):
        raise CustomAssertionError(f"Assertion Failed: Both text and substring must be strings. Got text: {type(text)}, substring: {type(substring)}")
    if substring in text:
        error_message = f"Assertion Failed: Expected text '{text}' not to contain substring '{substring}', but it did."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_is_none(value: Any, message: Optional[str] = None) -> None:
    """Asserts that value is None."""
    if value is not None:
        error_message = f"Assertion Failed: Expected value to be None, but got '{value}'."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_is_not_none(value: Any, message: Optional[str] = None) -> None:
    """Asserts that value is not None."""
    if value is None:
        error_message = "Assertion Failed: Expected value not to be None, but it was."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_greater(value1: Any, value2: Any, message: Optional[str] = None) -> None:
    """Asserts that value1 is greater than value2."""
    if not value1 > value2:
        error_message = f"Assertion Failed: Expected {value1} to be greater than {value2}."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

def assert_less(value1: Any, value2: Any, message: Optional[str] = None) -> None:
    """Asserts that value1 is less than value2."""
    if not value1 < value2:
        error_message = f"Assertion Failed: Expected {value1} to be less than {value2}."
        if message:
            error_message += f" {message}"
        raise CustomAssertionError(error_message)

# Example usage (outside of agent execution, for direct testing of this module)
if __name__ == '__main__':
    try:
        assert_equal(5, 5)
        print("assert_equal(5, 5) passed")
        assert_equal(5, 6, "Custom message for 5 != 6")
    except CustomAssertionError as e:
        print(e)

    try:
        assert_true(True)
        print("assert_true(True) passed")
        assert_true(False, "Custom message for True == False")
    except CustomAssertionError as e:
        print(e)

    try:
        assert_contains("hello world", "world")
        print("assert_contains('hello world', 'world') passed")
        assert_contains("hello world", "python", "Custom message for contains")
    except CustomAssertionError as e:
        print(e)

    try:
        assert_is_not_none("hello")
        print("assert_is_not_none('hello') passed")
        assert_is_not_none(None, "Custom message for is_not_none")
    except CustomAssertionError as e:
        print(e)
