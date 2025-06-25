from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    PENDING = "PENDING"

class TestStepAction(Enum):
    # Navigation
    NAVIGATE_URL = "navigate_url"
    # UI Interactions
    CLICK = "click"
    TYPE_TEXT = "type_text"
    SELECT_OPTION = "select_option"
    HOVER = "hover"
    PRESS_KEY = "press_key"
    UPLOAD_FILE = "upload_file"
    SCROLL_PAGE_UP = "scroll_page_up"
    SCROLL_PAGE_DOWN = "scroll_page_down"
    # Assertions
    ASSERT_ELEMENT_TEXT_EQUALS = "assert_element_text_equals"
    ASSERT_ELEMENT_TEXT_CONTAINS = "assert_element_text_contains"
    ASSERT_ELEMENT_VISIBLE = "assert_element_visible"
    ASSERT_ELEMENT_NOT_VISIBLE = "assert_element_not_visible"
    ASSERT_ELEMENT_ENABLED = "assert_element_enabled"
    ASSERT_ELEMENT_NOT_ENABLED = "assert_element_not_enabled"
    ASSERT_URL_EQUALS = "assert_url_equals"
    ASSERT_TITLE_EQUALS = "assert_title_equals"
    ASSERT_TEXT_PRESENT = "assert_text_present" # General text on page
    ASSERT_TEXT_NOT_PRESENT = "assert_text_not_present" # General text on page
    # Waits
    WAIT_FOR_ELEMENT_VISIBLE = "wait_for_element_visible"
    WAIT_FOR_ELEMENT_CLICKABLE = "wait_for_element_clickable"
    WAIT_FOR_TIMEOUT = "wait_for_timeout" # Simple sleep
    # Data/API
    FETCH_DATA = "fetch_data" # For API calls
    VALIDATE_JSON_RESPONSE = "validate_json_response"
    # File Operations
    VERIFY_DOWNLOADED_FILE = "verify_downloaded_file"
    # Custom Code
    EXECUTE_SCRIPT = "execute_script" # For CoderAgent to run arbitrary Python
    # Meta
    COMMENT = "comment" # For adding comments in the test steps

class TestStepResult(BaseModel):
    description: str
    status: TestStatus = TestStatus.PENDING
    message: Optional[str] = None
    duration: float = 0.0  # in seconds
    screenshot_path: Optional[str] = None # Path to screenshot on failure or for visual logs
    details: Optional[Dict[str, Any]] = None # For extra details like LLM reasoning, etc.

class TestStep(BaseModel):
    step_id: str = Field(..., description="Unique identifier for the test step")
    description: str = Field(..., description="Natural language description of the test step")
    action: TestStepAction = Field(..., description="The action to be performed for this step")
    target: Optional[str] = Field(None, description="Selector for the target element (e.g., CSS, XPath, or AI-identified ID)")
    value: Optional[Any] = Field(None, description="Value to be used for the action (e.g., text to type, URL, assertion value)")
    expected_outcome: Optional[Any] = Field(None, description="Expected outcome for assertions")
    agent_name: Optional[str] = Field(None, description="Preferred agent to execute this step (e.g., web_surfer, coder_agent)")
    timeout_seconds: int = Field(30, description="Timeout for this specific step")
    retry_attempts: int = Field(0, description="Number of retry attempts for this step on failure")
    on_failure: Optional[str] = Field(None, description="Action to take on failure (e.g., 'continue', 'stop_test_case', 'stop_all_tests')")
    result: Optional[TestStepResult] = None

    class Config:
        use_enum_values = True

class TestCase(BaseModel):
    case_id: str = Field(..., description="Unique identifier for the test case")
    name: str = Field(..., description="Name of the test case")
    description: Optional[str] = Field(None, description="Detailed description of the test case")
    tags: List[str] = Field(default_factory=list, description="Tags for categorizing the test case")
    priority: int = Field(3, description="Priority of the test case (e.g., 1-High, 2-Medium, 3-Low)")
    steps: List[TestStep] = Field(..., description="List of test steps")
    setup_steps: List[TestStep] = Field(default_factory=list, description="Steps to run before the main test steps")
    teardown_steps: List[TestStep] = Field(default_factory=list, description="Steps to run after the main test steps, regardless of outcome")
    test_data: Optional[Dict[str, Any]] = Field(None, description="Data to be used for parameterizing this test case")
    status: TestStatus = TestStatus.PENDING

    class Config:
        use_enum_values = True

class TestSuite(BaseModel):
    suite_id: str = Field(..., description="Unique identifier for the test suite")
    name: str = Field(..., description="Name of the test suite")
    description: Optional[str] = Field(None, description="Detailed description of the test suite")
    test_cases: List[TestCase] = Field(..., description="List of test cases in this suite")

class TestRunResult(BaseModel):
    run_id: str = Field(..., description="Unique identifier for this test run")
    suite_name: str
    start_time: str
    end_time: Optional[str] = None
    duration: float = 0.0 # Total duration in seconds
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    status: TestStatus = TestStatus.PENDING
    results: List[TestCase] # Stores the TestCase objects with their updated statuses and step results

    class Config:
        use_enum_values = True
