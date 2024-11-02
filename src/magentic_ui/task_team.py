from typing import Optional, Union, Any, Dict, Literal
from autogen_core.models import ChatCompletionClient
from autogen_core import ComponentModel
from autogen_agentchat.agents import UserProxyAgent

from .tools.playwright.browser import get_browser_resource_config
from .utils import get_internal_urls
from .teams import GroupChat, RoundRobinGroupChat
from .orchestrator_config import OrchestratorConfig
from .agents import WebSurfer, CoderAgent, USER_PROXY_DESCRIPTION, FileSurfer
from .types import SimplifiedConfig, RunPaths
from .agents.web_surfer import WebSurferConfig
from .agents.users import DummyUserProxy, MetadataUserProxy
from .approval_guard import (
    ApprovalGuard,
    ApprovalGuardContext,
    ApprovalConfig,
    BaseApprovalGuard,
)
from .input_func import InputFuncType, make_agentchat_input_func
from .learning.memory_provider import MemoryControllerProvider


# TODO: Convert all usages of allowed website to use a Dict[str, UrlStatus]
async def get_task_team(
    orchestrator_config: OrchestratorConfig | None = None,
    websurfer_config: WebSurferConfig | None = None,
    input_func: Optional[InputFuncType] = None,
    endpoint_config_orch: Optional[Union[ComponentModel, Dict[str, Any]]] = None,
    endpoint_config_websurfer: Optional[Union[ComponentModel, Dict[str, Any]]] = None,
    endpoint_config_coder: Optional[Union[ComponentModel, Dict[str, Any]]] = None,
    endpoint_config_file_surfer: Optional[Union[ComponentModel, Dict[str, Any]]] = None,
    endpoint_config_action_guard: Optional[
        Union[ComponentModel, Dict[str, Any]]
    ] = None,
    simplified_config: SimplifiedConfig | None = None,
    playwright_port: int = -1,
    novnc_port: int = -1,
    user_proxy_type: Optional[str] = None,
    task: Optional[str] = None,
    hints: Optional[str] = None,
    answer: Optional[str] = None,
    *,
    paths: RunPaths,
    inside_docker: bool = True,
    model_context_token_limit: int = 110000,
    approval_policy: Optional[
        Literal[
            "always",
            "never",
            "auto-conservative",
            "auto-permissive",
        ]
    ] = None,
) -> GroupChat | RoundRobinGroupChat:
    """
    Creates and returns a GroupChat team with specified configuration.

    Args:
        orchestrator_config (OrchestratorConfig, optional): Configuration for the team. Default: None.
        websurfer_config (WebSurferConfig, optional): Configuration for the web surfer agent. Default: None.
        input_func (callable, optional): Function to handle user input. Default: None
        endpoint_config_orch (Dict[str. Any], optional): Configuration for the orchestrator client. Default: None.
        endpoint_config_websurfer (Dict[str. Any], optional): Configuration for the web surfer client. Default: None.
        endpoint_config_coder (Dict[str. Any], optional): Configuration for the coder client. Default: None.
        endpoint_config_file_surfer (Dict[str. Any], optional): Configuration for the file surfer client. Default: None.
        endpoint_config_action_guard (Dict[str. Any], optional): Configuration for the action guard client. Default: None.
        simplified_config (SimplifiedConfig, optional): Simplified configuration for team. Default: None.
        playwright_port (int, optional): Port for the Playwright browser. Default: -1 (auto-assign).
        novnc_port (int, optional): Port for the noVNC server. Default: -1 (auto-assign).
        user_proxy_type (str, optional): Type of user proxy agent to use ("dummy", "metadata", or None for default). Default: None.
        task (str, optional): Task to be performed by the agents. Default: None.
        hints (str, optional): Helpful hints for the task. Default: None.
        answer (str, optional): Answer to the task. Default: None.
        inside_docker (bool, optional): Whether to run inside a docker container. Default: True.
        model_context_token_limit (int, optional): The maximum number of tokens the model can use. Default: 110000.
        approval_policy (str, optional): Policy for action approval. Default: "auto-conservative".

    Returns:
        GroupChat | RoundRobinGroupChat: An instance of GroupChat or RoundRobinGroupChat with the specified agents and configuration.
    """
    default_client_config = {
        "provider": "OpenAIChatCompletionClient",
        "config": {
            "model": "gpt-4o-2024-08-06",
        },
        "max_retries": 5,
    }

    def get_model_client(
        endpoint_config: Union[ComponentModel, Dict[str, Any], None],
    ) -> ChatCompletionClient:
        if endpoint_config is None:
            return ChatCompletionClient.load_component(default_client_config)
        return ChatCompletionClient.load_component(endpoint_config)

    if not inside_docker:
        assert (
            paths.external_run_dir == paths.internal_run_dir
        ), "External and internal run dirs must be the same in non-docker mode"

    model_client_orch = get_model_client(endpoint_config_orch)
    approval_guard: BaseApprovalGuard | None = None

    if approval_policy is None:
        if simplified_config is not None and simplified_config.approval_policy:
            approval_policy = simplified_config.approval_policy
        else:
            approval_policy = "never"

    websurfer_loop_team: bool = (
        simplified_config.websurfer_loop if simplified_config else False
    )

    model_client_coder = get_model_client(endpoint_config_coder)
    model_client_file_surfer = get_model_client(endpoint_config_file_surfer)
    browser_resource_config, _novnc_port, _playwright_port = (
        get_browser_resource_config(
            paths.external_run_dir, novnc_port, playwright_port, inside_docker
        )
    )

    if endpoint_config_websurfer is None:
        endpoint_config_websurfer = default_client_config

    if simplified_config is not None and (
        orchestrator_config is not None or websurfer_config is not None
    ):
        raise ValueError(
            "Cannot provide both orchestrator_config and simplified_config or websurfer_config"
        )

    if simplified_config is not None:
        orchestrator_config = OrchestratorConfig(
            cooperative_planning=simplified_config.cooperative_planning,
            autonomous_execution=simplified_config.autonomous_execution,
            allowed_websites=simplified_config.allowed_websites,
            plan=simplified_config.plan,
            model_context_token_limit=model_context_token_limit,
            do_bing_search=simplified_config.do_bing_search,
            retrieve_relevant_plans=simplified_config.retrieve_relevant_plans,
            memory_controller_key=simplified_config.memory_controller_key,
        )
        websurfer_config = WebSurferConfig(
            name="web_surfer",
            model_client=endpoint_config_websurfer,
            browser=browser_resource_config,
            single_tab_mode=False,
            max_actions_per_step=simplified_config.max_actions_per_step,
            url_statuses={
                key: "allowed" for key in orchestrator_config.allowed_websites
            }
            if orchestrator_config.allowed_websites
            else None,
            url_block_list=get_internal_urls(inside_docker, paths),
            multiple_tools_per_call=simplified_config.multiple_tools_per_call,
            downloads_folder=str(paths.internal_run_dir),
            debug_dir=str(paths.internal_run_dir),
            animate_actions=True,
            start_page=None,
            use_action_guard=True,
            to_save_screenshots=False,
        )
    else:
        if orchestrator_config is None:
            orchestrator_config = OrchestratorConfig(
                cooperative_planning=True,
                autonomous_execution=False,
                allow_for_replans=True,
                do_bing_search=False,
                model_context_token_limit=model_context_token_limit,
            )
        if websurfer_config is None:
            websurfer_config = WebSurferConfig(
                name="web_surfer",
                model_client=endpoint_config_websurfer,
                model_context_token_limit=model_context_token_limit,
                browser=browser_resource_config,
                animate_actions=True,
                url_statuses={
                    key: "allowed" for key in orchestrator_config.allowed_websites
                }
                if orchestrator_config.allowed_websites
                else None,
                url_block_list=get_internal_urls(inside_docker, paths),
                start_page=None,
                downloads_folder=str(paths.internal_run_dir),
                debug_dir=str(paths.internal_run_dir),
                use_action_guard=True,
                to_save_screenshots=False,
                single_tab_mode=False,
            )

    user_proxy: DummyUserProxy | MetadataUserProxy | UserProxyAgent

    if user_proxy_type == "dummy":
        user_proxy = DummyUserProxy(name="user_proxy")
    elif user_proxy_type == "metadata":
        assert task is not None, "Task must be provided for metadata user proxy"
        assert hints is not None, "Hints must be provided for metadata user proxy"
        assert answer is not None, "Answer must be provided for metadata user proxy"
        user_proxy = MetadataUserProxy(
            name="user_proxy",
            description="Metadata User Proxy Agent",
            task=task,
            helpful_task_hints=hints,
            task_answer=answer,
            model_client=model_client_orch,
        )
    else:
        user_proxy_input_func = make_agentchat_input_func(input_func)
        user_proxy = UserProxyAgent(
            description=USER_PROXY_DESCRIPTION,
            name="user_proxy",
            input_func=user_proxy_input_func,
        )

    if user_proxy_type in ["dummy", "metadata"]:
        model_client_action_guard = get_model_client(endpoint_config_action_guard)

        # Simple approval function that always returns yes
        def always_yes_input(prompt: str, input_type: str = "text_input") -> str:
            return "yes"

        approval_guard = ApprovalGuard(
            input_func=always_yes_input,
            default_approval=False,
            model_client=model_client_action_guard,
            config=ApprovalConfig(
                approval_policy=approval_policy,
            ),
        )
    elif input_func is not None:
        model_client_action_guard = get_model_client(endpoint_config_action_guard)
        approval_guard = ApprovalGuard(
            input_func=input_func,
            default_approval=False,
            model_client=model_client_action_guard,
            config=ApprovalConfig(
                approval_policy=approval_policy,
            ),
        )
    with ApprovalGuardContext.populate_context(approval_guard):
        web_surfer = WebSurfer.from_config(websurfer_config)
    if websurfer_loop_team:
        # simplified team of only the web surfer
        team = RoundRobinGroupChat(
            participants=[web_surfer, user_proxy],
            max_turns=10000,
        )
        await team.lazy_init()
        return team

    coder_agent = CoderAgent(
        name="coder_agent",
        model_client=model_client_coder,
        work_dir=paths.internal_run_dir,
        bind_dir=paths.external_run_dir,
        model_context_token_limit=model_context_token_limit,
        approval_guard=approval_guard,
    )

    file_surfer = FileSurfer(
        name="file_surfer",
        model_client=model_client_file_surfer,
        work_dir=paths.internal_run_dir,
        bind_dir=paths.external_run_dir,
        model_context_token_limit=model_context_token_limit,
        approval_guard=approval_guard,
    )

    if (
        orchestrator_config.memory_controller_key is not None
        and orchestrator_config.retrieve_relevant_plans in ["reuse", "hint"]
    ):
        memory_provider = MemoryControllerProvider(
            internal_workspace_root=paths.internal_root_dir,
            external_workspace_root=paths.external_root_dir,
            inside_docker=inside_docker,
        )
    else:
        memory_provider = None

    team = GroupChat(
        participants=[web_surfer, user_proxy, coder_agent, file_surfer],
        orchestrator_config=orchestrator_config,
        model_client=model_client_orch,
        memory_provider=memory_provider,
    )

    await team.lazy_init()
    return team
