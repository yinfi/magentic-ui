import pandas as pd
from autogen_ext.models.openai import OpenAIChatCompletionClient

from magentic_ui.eval.benchmarks import (
    WebVoyagerBenchmark,
    AssistantBenchBenchmark,
    GaiaBenchmark,
    CustomBenchmark,
    BearcubsBenchmark,
    WebGamesBenchmark,
)

from magentic_ui.eval.evaluators import llm_evaluate_candidate_answer
from magentic_ui.eval.core import run_evaluate_benchmark_func
from magentic_ui.eval.basesystem import BaseSystem
from magentic_ui.eval.models import BaseCandidate, BaseTask


def test_assistantbench():
    data_dir = "./data/AssistantBench"  # or any other local path
    benchmark = AssistantBenchBenchmark(data_dir=data_dir)

    # Download the dataset (only needed once)
    benchmark.download_dataset()

    # Load it into memory
    benchmark.load_dataset()

    # Get first task using next(iter()) instead of numeric index
    first_task = next(iter(benchmark.tasks.values()))
    print(
        benchmark.evaluator(
            first_task,
            {"answer": "Paris"},
        )
    )


def test_gaia():
    data_dir = "./data/GAIA"  # or any other local path
    benchmark = GaiaBenchmark(data_dir=data_dir)

    # Download the dataset (only needed once)
    benchmark.download_dataset()

    # Load it into memory
    benchmark.load_dataset()

    # Get first task
    first_task = next(iter(benchmark.tasks.values()))
    print(
        benchmark.evaluator(
            first_task,
            {"answer": "14"},
        )
    )


def test_webvoyager():
    data_dir = "./data/webvoyager"  # or any other local path
    client = OpenAIChatCompletionClient(model="gpt-4o-2024-08-06")
    benchmark = WebVoyagerBenchmark(
        data_dir=data_dir, eval_method="gpt_eval", model_client=client
    )
    # Download the dataset (only needed once)
    benchmark.download_dataset()
    # Load it into memory
    benchmark.load_dataset()

    first_task = next(iter(benchmark.tasks.values()))
    print(first_task)
    print(
        benchmark.evaluator(
            first_task,
            {
                "answer": "Vegetarian Four Cheese Lasagna', 4.6-star, 181 reviews, Servings 8",
                "screenshots": [""],
            },
        )
    )


def test_bearcubs():
    data_dir = "./data/bearcubs"  # or any other local path
    benchmark = BearcubsBenchmark(data_dir=data_dir)

    # Download the dataset (only needed once)
    benchmark.download_dataset()

    # Load it into memory
    benchmark.load_dataset()

    first_task = next(iter(benchmark.tasks.values()))
    print(first_task)


def test_webgames():
    data_dir = "./data/webgames"  # or any other local path
    benchmark = WebGamesBenchmark(data_dir=data_dir)

    # Download the dataset (only needed once)
    benchmark.download_dataset()

    # Load it into memory
    benchmark.load_dataset()

    first_task = next(iter(benchmark.tasks.values()))
    print(first_task)
    print(benchmark.evaluator(first_task, {"answer": "aaaaDATE_MASTER_2024aaa"}))


def test_custom_benchmark():
    # Create a sample DataFrame
    data = {
        "id": [1, 2, 3],
        "question": ["What is AI?", "What is ML?", "What is DL?"],
        "answer": ["Artificial Intelligence", "Machine Learning", "Deep Learning"],
        "url": [
            "http://example.com/ai",
            "http://example.com/ml",
            "http://example.com/dl",
        ],
        "metadata": [
            '{"source": "example1"}',
            '{"source": "example2"}',
            '{"source": "example3"}',
        ],
    }

    df = pd.DataFrame(data)
    # Example instantiation of the CustomBenchmark class
    data_dir = "/path/to/your/csvfile.csv"  # This can be ignored if df is provided
    custom_benchmark = CustomBenchmark(name="Custom", data_dir=data_dir, df=df)
    custom_benchmark.load_dataset()
    first_task = next(iter(custom_benchmark.tasks.values()))
    print(first_task)
    from magentic_ui.eval.models import CustomCandidate

    candidate_answer = CustomCandidate(
        answer="Artificial Intelligence"
    )  # your model's answer
    score = custom_benchmark.evaluator(first_task, candidate_answer)
    print("Single-example score:", score)


class ExampleSystem(BaseSystem):
    """
    A toy system that returns a stub answer.
    """

    def __init__(self, system_name: str):
        super().__init__(system_name)
        self.candidate_class = BaseCandidate

    def get_answer(
        self, task_id: str, task: BaseTask, output_dir: str
    ) -> BaseCandidate:
        # For demonstration, produce a trivial answer
        answer = BaseCandidate(
            answer=f"CrossFit East River Avea Pilates {task.question}"
        )
        self.save_answer_to_disk(task_id, answer, output_dir)
        return answer


# Move the constructor functions outside the test function
def create_test_system():
    # Return the system instance instead of just the class
    return ExampleSystem(system_name="Example")


def create_test_benchmark(name, data_dir, df):
    return CustomBenchmark(name=name, data_dir=data_dir, df=df)


def test_run_evaluate_custom():
    # Create a sample DataFrame
    data = {
        "id": [1, 2, 3],
        "question": ["What is AI?", "What is ML?", "What is DL?"],
        "answer": ["Artificial Intelligence", "Machine Learning", "Deep Learning"],
        "url": [
            "http://example.com/ai",
            "http://example.com/ml",
            "http://example.com/dl",
        ],
        "metadata": [
            '{"source": "example1"}',
            '{"source": "example2"}',
            '{"source": "example3"}',
        ],
    }

    df = pd.DataFrame(data)
    current_dir = ""

    # Create benchmark constructor that captures df
    def create_benchmark_with_df(name, data_dir):
        return create_test_benchmark(name=name, data_dir=data_dir, df=df)

    run_evaluate_benchmark_func(
        benchmark_name="Custom",
        system_name="Example",
        parallel=1,  # Changed to 1 for easier debugging
        benchmark_dir=current_dir,
        runs_dir=current_dir,
        split="all",
        subsample=1,
        run_id=5,
        benchmark_constructor=create_benchmark_with_df,
        system_constructor=create_test_system,  # This will now be called to create system instances
        reload_system_per_task=True,  # Add this to ensure new system instance for each task
    )


def test_evaluator_gpt():
    client = OpenAIChatCompletionClient(model="gpt-4o-2024-08-06")
    eval_answer = llm_evaluate_candidate_answer(
        task_question="What is the price of the iPhone 14?",
        candidate_answer="The price of the iPhone 14 is $799.",
        model_client=client,
        gold_truth_answer=None,
        candidate_reasoning="I went to apple.com, then I searched for 'iPhone 14' and found the price on the product page.",
        candidate_screenshots=None,
    )
    print(eval_answer)
    eval_answer = llm_evaluate_candidate_answer(
        task_question="What is the price of the iPhone 14?",
        candidate_answer="The price of the iPhone 14 is $799.",
        model_client=client,
        gold_truth_answer="$899",
        candidate_reasoning="I went to apple.com, then I searched for 'iPhone 14' and found the price on the product page.",
        candidate_screenshots=None,
    )
    print(eval_answer)


if __name__ == "__main__":
    print("Running tests...")
    print("Add calls to test functions and run this file.")
    test_bearcubs()
    test_assistantbench()
    test_gaia()
    test_webvoyager()
    test_custom_benchmark()
    test_evaluator_gpt()
    test_run_evaluate_custom()
    test_webgames()
