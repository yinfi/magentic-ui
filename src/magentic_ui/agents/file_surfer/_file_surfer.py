import json
from pathlib import Path
import traceback
from typing import List, Sequence, Tuple, AsyncGenerator, Optional, Dict, Any
from datetime import datetime
from loguru import logger
import asyncio

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import (
    BaseChatMessage,
    TextMessage,
    MultiModalMessage,
    BaseAgentEvent,
)
from autogen_core import Image as AGImage

from autogen_core import CancellationToken, Component, ComponentModel, FunctionCall
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_core.model_context import TokenLimitedChatCompletionContext
from pydantic import BaseModel
from typing_extensions import Self
from autogen_core.code_executor import CodeExecutor
from autogen_ext.code_executors.docker import DockerCommandLineCodeExecutor
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from ._tool_definitions import (
    TOOL_OPEN_PATH,
    TOOL_LIST_CURRENT_DIRECTORY,
    TOOL_PAGE_DOWN,
    TOOL_PAGE_UP,
    TOOL_FIND_NEXT,
    TOOL_FIND_ON_PAGE_CTRL_F,
    TOOL_FIND_FILE,
)
from ._code_markdown_file_browser import CodeExecutorMarkdownFileBrowser
from ...approval_guard import BaseApprovalGuard
from ...guarded_action import GuardedAction, ApprovalDeniedError
from ...utils import thread_to_context
import uuid


from .._utils import exec_command_umask_patched

DockerCommandLineCodeExecutor._execute_command = exec_command_umask_patched  # type: ignore


class FileSurferConfig(BaseModel):
    """Configuration for FileSurfer agent

    Attributes:
        name (str): The agent's name
        model_client (str): The model configuration to use
        description (str, optional): Optional description of the agent
        code_executor (ComponentModel, optional): Optional code executor configuration
        use_local_executor (bool, optional): Whether to use local code execution Default: False
    """

    name: str
    model_client: ComponentModel
    description: str | None = None
    code_executor: ComponentModel | None = None
    use_local_executor: bool = False


class FileSurfer(BaseChatAgent, Component[FileSurferConfig]):
    """
    An agent that can handle files using Markitdown and a code executor.


    Args:
        name (str): The agent's name
        model_client (str): The model to use (must support tool use)
        description (str, optional): The agent's description used by the team Default: DEFAULT_DESCRIPTION
        work_dir (str, optional): The working directory for the code executor Default: `/workspace`
        bind_dir (str, optional): The directory to bind to the code executor Default: None
        code_executor (CodeExecutor, optional): Optional custom code executor to use
        use_local_executor (bool, optional): Whether to use local code execution instead of Docker Default: False

    """

    component_config_schema = FileSurferConfig
    component_provider_override = "autogen_ext.agents.file_surfer.FileSurfer"

    DEFAULT_DESCRIPTION = """
    An agent that can read local files.

    In a single step when you asked to do something, it can do one action among the following:
    - open a file: it will convert the file to text if it is not already text. For instance for audio files, it will transcribe the audio and provide the text.
    - list the current directory: it will list the files in the current directory
    - scroll down in an open file that it has already opened
    - scroll up in an open file that it has already opened
    - find text on the page of an open file
    - find a file: will return a list of files that match the query, if the file is found exactly it will be opened
    It can briefly answer questions about the text contents of the open file using an LLM call. 

    It cannot manipulate or create files, use the coder agent if that is needed.
     """

    system_prompt_file_surfer_template = """
    You are a helpful AI Assistant.
    When given a user query, use available functions to help the user with their request.
    The date today is: {date_today}
    """

    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient,
        model_context_token_limit: int = 128000,
        description: str = DEFAULT_DESCRIPTION,
        work_dir: Path | str = "/workspace",
        bind_dir: Path | str | None = None,
        code_executor: Optional[CodeExecutor] = None,
        use_local_executor: bool = False,
        approval_guard: BaseApprovalGuard | None = None,
        save_converted_files: bool = False,
    ) -> None:
        super().__init__(name, description)
        self._model_client = model_client
        self._approved_files: set[str] = set()

        tools_schema = [
            TOOL_OPEN_PATH,
            TOOL_LIST_CURRENT_DIRECTORY,
            TOOL_PAGE_DOWN,
            TOOL_PAGE_UP,
            TOOL_FIND_NEXT,
            TOOL_FIND_ON_PAGE_CTRL_F,
            TOOL_FIND_FILE,
        ]
        self._model_context = TokenLimitedChatCompletionContext(
            model_client,
            token_limit=model_context_token_limit,
            tool_schema=tools_schema,
        )
        self._chat_history: List[LLMMessage] = []

        self._approval_guard = approval_guard
        self._save_converted_files = save_converted_files
        if code_executor:
            self._code_executor = code_executor
        elif use_local_executor:
            self._code_executor = LocalCommandLineCodeExecutor(work_dir=work_dir)
        else:
            name = f"{name}-{uuid.uuid4()}"
            self._code_executor = DockerCommandLineCodeExecutor(
                container_name=name,
                image="magentic-ui-python-env",
                work_dir=work_dir,
                bind_dir=bind_dir,
                delete_tmp_files=True,
            )
        self._browser = CodeExecutorMarkdownFileBrowser(
            self._code_executor,
            viewport_size=1024 * 5,
            save_converted_files=save_converted_files,
        )
        self.did_lazy_init = False
        self.is_paused = False
        self._pause_event = asyncio.Event()

    async def lazy_init(self) -> None:
        """Initialize code executor and browser on first use."""
        if not self.did_lazy_init:
            if self._code_executor:
                # check if the code executor has a start method
                if hasattr(self._code_executor, "start"):
                    await self._code_executor.start()  # type: ignore
            await self._browser.lazy_init()
            self.did_lazy_init = True

    async def pause(self) -> None:
        """Pause the FileSurfer agent."""
        self.is_paused = True
        self._pause_event.set()

    async def resume(self) -> None:
        """Resume the FileSurfer agent."""
        self.is_paused = False
        self._pause_event.clear()

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        """Get the types of messages produced by the FileSurfer agent."""
        return (TextMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        """Process incoming messages and return a response.

        Args:
            messages (Sequence[BaseChatMessage]): Sequence of chat messages to process
            cancellation_token (CancellationToken): Token for cancelling operation

        Returns:
            Response: Response containing the agent's reply
        """
        response: Response | None = None
        async for message in self.on_messages_stream(messages, cancellation_token):
            if isinstance(message, Response):
                response = message
        assert response is not None
        return response

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """Process messages and yield responses as a stream.

        Args:
            messages (Sequence[BaseChatMessage]): Sequence of chat messages to process
            cancellation_token (CancellationToken): Token for cancelling operation

        Yields:
            BaseAgentEvent: Agent events
            BaseChatMessage: Agent chat messages
            Response: Agent responses
        """
        await self.lazy_init()
        chat_messages = thread_to_context(
            list(messages),
            agent_name=self.name,
            is_multimodal=self._model_client.model_info["vision"],
        )
        self._chat_history.extend(chat_messages)

        # Set up the cancellation token for the code execution.
        llm_cancellation_token = CancellationToken()

        # Cancel the code execution if the handler's cancellation token is set.
        cancellation_token.add_callback(lambda: llm_cancellation_token.cancel())

        # Set up background task to monitor the pause event and cancel the code execution if paused.
        async def monitor_pause() -> None:
            await self._pause_event.wait()
            llm_cancellation_token.cancel()

        monitor_pause_task = asyncio.create_task(monitor_pause())

        try:
            content_action: str = ""
            history = self._chat_history[0:-1]
            last_message = self._chat_history[-1]
            assert isinstance(last_message, UserMessage)

            task_content = (
                last_message.content
            )  # the last message from the sender is the task

            assert self._browser is not None

            context_message = UserMessage(
                source="user",
                content=f"Your file viewer is currently open to the file or directory '{self._browser.page_title}' with path '{self._browser.path}'.",
            )

            task_message = UserMessage(
                source="user",
                content=task_content,
            )

            system_prompt_file_surfer = self.system_prompt_file_surfer_template.format(
                date_today=datetime.now().strftime("%Y-%m-%d")
            )

            default_system_messages = [
                SystemMessage(content=system_prompt_file_surfer),
            ]

            # Re-initialize model context to meet token limit quota
            try:
                await self._model_context.clear()
                for msg in (
                    history + default_system_messages + [context_message, task_message]
                ):
                    await self._model_context.add_message(msg)
                token_limited_history = await self._model_context.get_messages()
            except Exception:
                token_limited_history = list(
                    history + default_system_messages + [context_message, task_message]
                )

            create_result = await self._model_client.create(
                messages=token_limited_history,
                tools=[
                    TOOL_OPEN_PATH,
                    TOOL_LIST_CURRENT_DIRECTORY,
                    TOOL_PAGE_DOWN,
                    TOOL_PAGE_UP,
                    TOOL_FIND_NEXT,
                    TOOL_FIND_ON_PAGE_CTRL_F,
                    TOOL_FIND_FILE,
                ],
                cancellation_token=llm_cancellation_token,
            )

            response = create_result.content
            tool_explanation = ""
            if isinstance(response, str):
                # Answer directly.
                content_action = response
                yield Response(
                    chat_message=TextMessage(
                        content=content_action,
                        source=self.name,
                        metadata={"internal": "no", "type": "file_surfer_response"},
                    )
                )

            elif isinstance(response, list) and all(
                isinstance(item, FunctionCall) for item in response
            ):
                function_calls = response
                for function_call in function_calls:
                    tool_name = function_call.name
                    try:
                        arguments: Dict[str, str] = json.loads(function_call.arguments)
                    except json.JSONDecodeError as e:
                        error_str = f"File surfer encountered an error decoding JSON arguments: {e}"
                        yield Response(
                            chat_message=TextMessage(
                                content=error_str, source=self.name
                            )
                        )
                        return

                    tool_call_msg = f"{function_call.name}( {json.dumps(json.loads(function_call.arguments))} )"

                    self._chat_history.append(
                        AssistantMessage(
                            content=f"In '{self._browser.path}', we propose the following action: {tool_call_msg}",
                            source=self.name,
                        )
                    )

                    tool_explanation = arguments.get("explanation", "")

                    assert isinstance(arguments, dict)

                    yield Response(
                        chat_message=TextMessage(
                            content=tool_explanation,
                            source=self.name,
                            metadata={"internal": "no", "type": "file_surfer_action"},
                        )
                    )

                    def _extract_browser_result() -> str:
                        header, content = self._get_browser_state()
                        # if content is empty, return the header
                        if content.strip() == "":
                            return header
                        return f"{header}\n```md\n{content}```"

                    action_request: TextMessage | None = None
                    guarded_action: GuardedAction[str] | None = None

                    match tool_name:
                        case "open_path":
                            assert "path" in arguments

                            async def _open_path_callable(
                                *args: Any, **kwargs: Any
                            ) -> str:
                                path = str(arguments["path"])
                                await self._browser.open_path(path)
                                return _extract_browser_result()

                            guarded_action = GuardedAction[str].from_schema(
                                TOOL_OPEN_PATH,
                                _open_path_callable,
                            )

                            seen_state = (
                                "previously unseen"
                                if arguments["path"] not in self._approved_files
                                else "previously opened"
                            )
                            action_request = TextMessage(
                                content=f"Opening {seen_state} file '{arguments['path']}'",
                                source=self.name,
                            )

                        case "list_current_directory":

                            async def _list_current_directory_callable(
                                *args: Any, **kwargs: Any
                            ) -> str:
                                path = "."
                                await self._browser.open_path(path)
                                return _extract_browser_result()

                            guarded_action = GuardedAction[str].from_schema(
                                TOOL_LIST_CURRENT_DIRECTORY,
                                _list_current_directory_callable,
                            )

                            action_request = TextMessage(
                                content="Listing current directory",
                                source=self.name,
                            )

                        case "page_up":
                            self._browser.page_up()

                        case "page_down":
                            self._browser.page_down()

                        case "find_on_page_ctrl_f":
                            search_string = arguments["search_string"]
                            self._browser.find_on_page(search_string)

                        case "find_next":
                            self._browser.find_next()

                        case "find_file":
                            query = arguments["query"]

                            async def _find_file_callable(
                                *args: Any, **kwargs: Any
                            ) -> str:
                                json_result = await self._browser.find_files(query)
                                result = json.loads(json_result)

                                # Format matches as a table regardless of perfect match
                                matches = result["matches"]
                                table_response = ""
                                if matches:
                                    table = "| File | Match Score |\n| ---- | ----------- |\n"
                                    for path, score in matches:
                                        table += f"| {path} | {score} |\n"
                                    table_response = (
                                        f"Found matches:\n```md\n{table}\n```\n"
                                    )
                                else:
                                    table_response = "No matching files found.\n"

                                # If we found a perfect match, open it after showing the table
                                if result["perfect_match"]:
                                    await self._browser.open_path(
                                        result["perfect_match"]
                                    )
                                    header, content = self._get_browser_state()
                                    return f"{table_response}Found perfect match! Opening file: {header}\n```md\n{content}```"

                                return table_response.strip()

                            guarded_action = GuardedAction[str].from_schema(
                                TOOL_FIND_FILE,
                                _find_file_callable,
                            )

                            action_request = TextMessage(
                                content=f"Searching files for '{query}'",
                                source=self.name,
                            )
                        case _:
                            # raise ValueError(f"Unknown tool name: {tool_name}")
                            pass

                    if action_request is None:
                        action_request = TextMessage(
                            content=f"{tool_explanation}",
                            source=self.name,
                        )

                    if guarded_action is not None:
                        result = await guarded_action.invoke_with_approval(
                            arguments,
                            action_request,
                            action_context=self._chat_history,
                            action_guard=self._approval_guard,
                        )
                        content_action = (
                            await result if asyncio.iscoroutine(result) else result
                        )
                    else:
                        content_action = _extract_browser_result()

                if self._browser.image_path:
                    yield Response(
                        chat_message=MultiModalMessage(
                            content=[
                                f"{content_action}\nHere is the image: {self._browser.page_title}",
                                AGImage.from_file(Path(self._browser.image_path)),
                            ],
                            source=self.name,
                            metadata={"internal": "no", "type": "file_surfer_response"},
                        )
                    )
                    self._chat_history.append(
                        AssistantMessage(
                            content=tool_explanation + "\n[image]",
                            source=self.name,
                        )
                    )
                    self._browser.image_path = None
                else:
                    yield Response(
                        chat_message=TextMessage(
                            content=content_action,
                            source=self.name,
                            metadata={"internal": "no", "type": "file_surfer_response"},
                        )
                    )
                    self._chat_history.append(
                        AssistantMessage(
                            content=tool_explanation + "\n" + content_action,
                            source=self.name,
                        )
                    )

        except ApprovalDeniedError:
            yield Response(
                chat_message=TextMessage(
                    content="Action not approved.",
                    source=self.name,
                    metadata={
                        "internal": "no",
                        "type": "file_surfer_response",
                    },
                )
            )
            self._chat_history.append(
                AssistantMessage(
                    content="Action not approved.",
                    source=self.name,
                )
            )

        except asyncio.CancelledError:
            # If the task is cancelled, we respond with a message.
            yield Response(
                chat_message=TextMessage(
                    content="The task was cancelled by the user.",
                    source=self.name,
                    metadata={"internal": "yes"},
                ),
            )
        except BaseException:
            content = f" File surfing error \n{traceback.format_exc()}"
            self._chat_history.append(
                AssistantMessage(content=content, source=self.name)
            )
            yield Response(
                chat_message=TextMessage(
                    content=content,
                    source=self.name,
                    metadata={"internal": "no", "type": "file_surfer_response"},
                )
            )
        finally:
            # Cancel the monitor task.
            monitor_pause_task.cancel()
            try:
                await monitor_pause_task
            except asyncio.CancelledError:
                pass

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """Reset the FileSurfer agent's state."""
        self._chat_history.clear()
        # Also reset approved files if necessary, or handle through a new session
        self._approved_files.clear()


    async def _execute_code_for_file_op(self, script_content: str, file_path: str) -> str:
        """
        Helper to execute a script using the agent's code executor.
        The script is expected to print its result as a JSON string to stdout.
        """
        # Ensure the file path is absolute for the executor context, usually within its work_dir
        # The code_executor's work_dir is the base for relative paths in scripts.
        # If file_path is already absolute and within the bind_dir, it might work directly.
        # For simplicity, assuming file_path is relative to the work_dir or an accessible absolute path.

        code_block = f"""
import json
import csv
import os

file_to_read = r'''{file_path}''' # Use raw string for paths

try:
    # Ensure the path is treated as relative to the executor's working directory
    # if not os.path.isabs(file_to_read):
    #     # This part might be complex depending on how code_executor resolves paths
    #     # For DockerCommandLineCodeExecutor, work_dir is the cwd inside container
    #     # Assuming file_path is either absolute (and mounted) or relative to work_dir
    #     pass

{script_content}

except FileNotFoundError:
    print(json.dumps({{"error": "File not found.", "path": file_to_read}}))
except Exception as e:
    print(json.dumps({{"error": str(e), "path": file_to_read}}))
        """

        # Using a unique filename for the temporary script
        script_filename = f"temp_file_op_{uuid.uuid4()}.py"

        # For Docker, paths in code_block need to be paths *inside* the container.
        # FileSurfer's work_dir is typically /workspace.
        # If 'path' arg to tools is host path, it needs to be mapped to container path.
        # This is complex. For now, assume 'path' is a path the executor can directly access.

        code_result = await self._code_executor.execute_code_blocks(
            code_blocks=[{"code": code_block, "language": "python", "filename": script_filename}],
            cancellation_token=CancellationToken() # Use a new token for this specific execution
        )

        if code_result.exit_code != 0:
            return json.dumps({"error": f"Script execution failed with exit code {code_result.exit_code}", "details": code_result.output})

        # The script prints JSON, so the output should be that JSON string.
        # No further JSON parsing needed here if script directly prints JSON.
        return code_result.output.strip()


    async def _execute_tool_read_csv_file(self, args: Dict[str, Any]) -> str:
        path = str(args["path"])
        self._approved_files.add(path) # Mark as approved if execution proceeds

        script_content = f"""
    data = []
    with open(file_to_read, mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data.append(row)
    print(json.dumps(data))
        """
        return await self._execute_code_for_file_op(script_content, path)

    async def _execute_tool_read_json_file(self, args: Dict[str, Any]) -> str:
        path = str(args["path"])
        self._approved_files.add(path)

        script_content = f"""
    with open(file_to_read, mode='r', encoding='utf-8') as jsonfile:
        data = json.load(jsonfile)
    print(json.dumps(data))
        """
        return await self._execute_code_for_file_op(script_content, path)

    def _get_browser_state(self) -> Tuple[str, str]:
        """Get the current state of the browser.

        Returns:
            Tuple containing:
                - str: Header string with path, title and viewport position
                - str: Current viewport content
        """
        # Add > to prevent markdown from interpreting as headers
        header = f" Path {self._browser.path}\n"

        if self._browser.page_title is not None:
            header += f" Title {self._browser.page_title}\n"

        current_page = self._browser.viewport_current_page
        total_pages = len(self._browser.viewport_pages)
        header += (
            f" Viewport position: Showing page {current_page+1} of {total_pages}.\n"
        )

        return (header, self._browser.viewport)

    async def close(self) -> None:
        """Close the FileSurfer agent."""
        logger.info("Closing FileSurfer...")
        if hasattr(self, "_code_executor"):
            await self._code_executor.stop()
        await self._model_client.close()

    def _to_config(self) -> FileSurferConfig:
        """
        Convert the FileSurfer instance to a configuration object.

        Returns:
            FileSurferConfig: An object representing the current configuration.
        """
        config = FileSurferConfig(
            name=self.name,
            model_client=self._model_client.dump_component(),
            description=self.description,
        )
        if hasattr(self._code_executor, "dump_component"):
            config.code_executor = self._code_executor.dump_component()  # type: ignore
        return config

    @classmethod
    def _from_config(cls, config: FileSurferConfig) -> Self:
        """
        Create a FileSurfer instance from a configuration object.

        Args:
            config (FileSurferConfig): A `FileSurferConfig` object containing the configuration.

        Returns:
            FileSurfer: A new instance of the FileSurfer class.
        """
        code_executor = None
        if config.code_executor:
            code_executor = CodeExecutor.load_component(config.code_executor)

        return cls(
            name=config.name,
            model_client=ChatCompletionClient.load_component(config.model_client),
            description=config.description or cls.DEFAULT_DESCRIPTION,
            code_executor=code_executor,
            use_local_executor=config.use_local_executor,
        )
