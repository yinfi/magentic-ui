import json
import os
import html
from typing import IO, List
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent as xml_indent

from .testing_types import TestRunResult, TestCase, TestStep, TestStatus, TestStepResult

def generate_json_report(test_run_result: TestRunResult, output_path: str) -> None:
    """
    Generates a JSON report from the TestRunResult.

    Args:
        test_run_result (TestRunResult): The test run result data.
        output_path (str): The path to save the JSON report.
    """
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        # Pydantic's model_dump_json is perfect for this
        f.write(test_run_result.model_dump_json(indent=2))
    print(f"JSON report generated at {output_path}")


def generate_html_report(test_run_result: TestRunResult, output_path: str) -> None:
    """
    Generates an HTML report from the TestRunResult.

    Args:
        test_run_result (TestRunResult): The test run result data.
        output_path (str): The path to save the HTML report.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html>\n")
        f.write("<html lang='en'>\n<head>\n")
        f.write("    <meta charset='UTF-8'>\n")
        f.write("    <meta name='viewport' content='width=device-width, initial-scale=1.0'>\n")
        f.write(f"    <title>Test Report: {html.escape(test_run_result.suite_name)}</title>\n")
        _add_html_styles(f)
        f.write("</head>\n<body>\n")
        f.write(f"    <div class='container'>\n")
        f.write(f"        <h1>Test Run Report: {html.escape(test_run_result.suite_name)}</h1>\n")

        # Summary Table
        f.write("        <h2>Summary</h2>\n")
        f.write("        <table class='summary-table'>\n")
        f.write(f"            <tr><th>Run ID</th><td>{html.escape(test_run_result.run_id)}</td></tr>\n")
        f.write(f"            <tr><th>Start Time</th><td>{html.escape(test_run_result.start_time)}</td></tr>\n")
        if test_run_result.end_time:
            f.write(f"            <tr><th>End Time</th><td>{html.escape(test_run_result.end_time)}</td></tr>\n")
        f.write(f"            <tr><th>Duration</th><td>{test_run_result.duration:.2f}s</td></tr>\n")
        f.write(f"            <tr><th>Total Tests</th><td>{test_run_result.total_tests}</td></tr>\n")
        f.write(f"            <tr class='status-pass'><th>Passed</th><td>{test_run_result.passed_tests}</td></tr>\n")
        f.write(f"            <tr class='status-fail'><th>Failed</th><td>{test_run_result.failed_tests}</td></tr>\n")
        f.write(f"            <tr class='status-skip'><th>Skipped</th><td>{test_run_result.skipped_tests}</td></tr>\n")
        f.write(f"            <tr><th>Overall Status</th><td class='status-{test_run_result.status.value.lower()}'>{test_run_result.status.value}</td></tr>\n")
        f.write("        </table>\n")

        # Test Cases Details
        f.write("        <h2>Test Cases</h2>\n")
        for tc_index, test_case in enumerate(test_run_result.results):
            f.write(f"        <div class='test-case status-{test_case.status.value.lower()}'>\n")
            f.write(f"            <h3>{tc_index + 1}. {html.escape(test_case.name)} (ID: {html.escape(test_case.case_id)}) - Status: {test_case.status.value}</h3>\n")
            if test_case.description:
                f.write(f"            <p><strong>Description:</strong> {html.escape(test_case.description)}</p>\n")
            if test_case.tags:
                f.write(f"            <p><strong>Tags:</strong> {', '.join(html.escape(tag) for tag in test_case.tags)}</p>\n")

            if test_case.steps:
                f.write("            <h4>Steps:</h4>\n")
                f.write("            <ul class='steps-list'>\n")
                for step_index, step in enumerate(test_case.steps):
                    if step.result:
                        step_result = step.result
                        f.write(f"                <li class='step status-{step_result.status.value.lower()}'>\n")
                        f.write(f"                    <strong>Step {step_index + 1}:</strong> {html.escape(step.description)} - <strong>{step_result.status.value}</strong> ({step_result.duration:.2f}s)\n")
                        if step_result.message:
                            f.write(f"                    <div class='step-message'>{html.escape(step_result.message)}</div>\n")
                        if step_result.screenshot_path and step_result.status == TestStatus.FAIL:
                            # Assuming screenshot_path is relative to the report or an accessible web path
                            f.write(f"                    <div class='step-screenshot'><a href='{html.escape(step_result.screenshot_path)}' target='_blank'>Screenshot on failure</a></div>\n")
                        if step_result.details:
                             f.write(f"                    <div class='step-details'>Details: <pre>{html.escape(json.dumps(step_result.details, indent=2))}</pre></div>\n")
                        f.write("                </li>\n")
                    else:
                         f.write(f"                <li class='step status-pending'><strong>Step {step_index + 1}:</strong> {html.escape(step.description)} - <strong>PENDING</strong></li>\n")
                f.write("            </ul>\n")
            f.write("        </div>\n") # close test-case

        f.write("    </div>\n") # close container
        f.write("</body>\n</html>\n")
    print(f"HTML report generated at {output_path}")

def _add_html_styles(f: IO[str]) -> None:
    f.write("""
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; color: #333; }
        .container { width: 80%; margin: 20px auto; background-color: #fff; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1, h2, h3, h4 { color: #333; }
        h1 { text-align: center; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        h2 { border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 30px; }
        table.summary-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        table.summary-table th, table.summary-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        table.summary-table th { background-color: #f0f0f0; }
        .test-case { border: 1px solid #ddd; margin-bottom: 15px; padding: 15px; border-radius: 5px; }
        .steps-list { list-style-type: none; padding-left: 0; }
        .step { padding: 8px; margin-bottom: 5px; border-left-width: 5px; border-left-style: solid; }
        .step-message { white-space: pre-wrap; background-color: #f9f9f9; border: 1px dashed #ccc; padding: 5px; margin-top: 5px; }
        .step-details pre { white-space: pre-wrap; word-wrap: break-word; background-color: #efefef; padding: 10px; border-radius: 3px;}
        .step-screenshot a { color: #007bff; }
        .status-pass { border-left-color: #28a745; background-color: #e6ffed; }
        .status-fail { border-left-color: #dc3545; background-color: #ffebee; }
        .summary-table .status-pass td { background-color: #d4edda; color: #155724; }
        .summary-table .status-fail td { background-color: #f8d7da; color: #721c24; }
        .summary-table .status-skip td { background-color: #fff3cd; color: #856404; }
        .test-case.status-pass { border-color: #28a745; }
        .test-case.status-fail { border-color: #dc3545; }
        .test-case.status-skip { border-color: #ffc107; }
        .status-pending { border-left-color: #6c757d; background-color: #f8f9fa; }
    </style>
""")

def generate_junit_xml_report(test_run_result: TestRunResult, output_path: str) -> None:
    """
    Generates a JUnit XML report from the TestRunResult.

    Args:
        test_run_result (TestRunResult): The test run result data.
        output_path (str): The path to save the JUnit XML report.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    root = Element("testsuites", name=test_run_result.suite_name)
    root.set("tests", str(test_run_result.total_tests))
    root.set("failures", str(test_run_result.failed_tests))
    root.set("skipped", str(test_run_result.skipped_tests))
    root.set("time", f"{test_run_result.duration:.3f}")
    # Add more attributes to root if needed, e.g., timestamp

    ts_attrs = {
        "name": test_run_result.suite_name,
        "tests": str(len(test_run_result.results)),
        "failures": str(sum(1 for tc in test_run_result.results if tc.status == TestStatus.FAIL)),
        "skipped": str(sum(1 for tc in test_run_result.results if tc.status == TestStatus.SKIP)),
        "time": f"{test_run_result.duration:.3f}",
        "timestamp": test_run_result.start_time  # Assuming start_time is ISO format
    }
    testsuite_elem = SubElement(root, "testsuite", attrib=ts_attrs)

    for test_case in test_run_result.results:
        # Calculate test case duration by summing step durations
        tc_duration = sum(step.result.duration for step in test_case.steps if step.result)

        tc_attrs = {
            "name": test_case.name,
            "classname": test_case.tags[0] if test_case.tags else test_run_result.suite_name, # Basic classname
            "time": f"{tc_duration:.3f}"
        }
        testcase_elem = SubElement(testsuite_elem, "testcase", attrib=tc_attrs)

        if test_case.status == TestStatus.FAIL:
            # Concatenate messages from failed steps
            failure_message = ""
            system_out_messages: List[str] = []
            for step in test_case.steps:
                if step.result:
                    system_out_messages.append(f"Step: {step.description} - Status: {step.result.status.value} ({step.result.duration:.2f}s)")
                    if step.result.message:
                         system_out_messages.append(f"  Message: {step.result.message}")
                    if step.result.status == TestStatus.FAIL and not failure_message: # Take first failure message
                        failure_message = step.result.message or "Step failed without specific message"

            failure_elem = SubElement(testcase_elem, "failure", message=failure_message)
            # Add more details to failure_elem.text if needed
            # failure_elem.text = "More detailed failure information..."

            if system_out_messages:
                system_out_elem = SubElement(testcase_elem, "system-out")
                system_out_elem.text = "\n".join(system_out_messages)

        elif test_case.status == TestStatus.SKIP:
            skipped_elem = SubElement(testcase_elem, "skipped")
            # Optionally add a message to skipped_elem if available
            # skipped_elem.text = "Test was skipped because..."

    tree = ElementTree(root)
    xml_indent(tree, space="  ", level=0) # For pretty printing
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"JUnit XML report generated at {output_path}")

# Example Usage (for direct testing of this module if needed)
if __name__ == "__main__":
    # Create dummy data
    step_res1_fail = TestStepResult(description="Click login", status=TestStatus.FAIL, message="Element not found: #login", duration=1.5, screenshot_path="screenshots/login_fail.png")
    step_res1_pass = TestStepResult(description="Click login", status=TestStatus.PASS, duration=1.2)

    step1_fail = TestStep(step_id="s1", description="Attempt login", action="click", target="#login", result=step_res1_fail)
    step1_pass = TestStep(step_id="s1", description="Navigate to home", action="navigate_url", value="/home", result=step_res1_pass)

    tc1 = TestCase(case_id="tc001", name="Login Test Failure", steps=[step1_fail], status=TestStatus.FAIL, priority=1, tags=["smoke", "login"])
    tc2 = TestCase(case_id="tc002", name="Homepage Navigation", steps=[step1_pass], status=TestStatus.PASS, priority=2, tags=["navigation"])
    tc3 = TestCase(case_id="tc003", name="Skipped Test", steps=[], status=TestStatus.SKIP, priority=3)


    run_result_data = TestRunResult(
        run_id="run_12345",
        suite_name="Main Suite",
        start_time="2023-10-26T10:00:00Z",
        end_time="2023-10-26T10:05:00Z",
        duration=300.0,
        total_tests=3,
        passed_tests=1,
        failed_tests=1,
        skipped_tests=1,
        status=TestStatus.FAIL, # Overall status based on outcomes
        results=[tc1, tc2, tc3]
    )

    reports_dir = "test_reports_output"

    generate_json_report(run_result_data, os.path.join(reports_dir, "report.json"))
    generate_html_report(run_result_data, os.path.join(reports_dir, "report.html"))
    generate_junit_xml_report(run_result_data, os.path.join(reports_dir, "report.xml"))

    print(f"Dummy reports generated in '{reports_dir}' directory.")
    print(f"Note: Screenshot paths in HTML are relative and may not resolve in this dummy example.")
