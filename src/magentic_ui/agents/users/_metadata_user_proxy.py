from typing import AsyncGenerator, Sequence, List, Literal
from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    TextMessage,
)
from autogen_core.model_context import TokenLimitedChatCompletionContext
from autogen_core import CancellationToken
from autogen_core.models import (
    ChatCompletionClient,
    UserMessage,
    LLMMessage,
    SystemMessage,
    AssistantMessage,
)
from ...utils import thread_to_context


SYSTEM_MESSAGE_PLANNING_PHASE_STRICT = """
**Context:**
You are tasked with role playing as a human user who is interacting with an AI to solve a task for you. 

The task is: {task} 

The AI will provide a plan for the task in the past messages.

{helpful_task_hints}

{answer}

The AI has no knowledge of the answer to the task or the helpful hints. 

**INSTRUCTIONS:**

You need to provide a response to the AI's plan as the user.

Case 1: If you believe the plan is perfect and will enable the AI to solve the task, respond with the following  string only: accept. The word "accept" only should be your response.
It is often the case that the plan can be improved.

Case 2: If you have feedback that can improve the plan and the chance of success, then write a response with natural language feedback to improve the plan.

Your feedback should be based on the helpful hints and the answer to the task if they are available.

Remember that the AI has no knowledge of the answer to the task or the helpful hints so you can't reference them explicitly.

Phrase your response as if you are a user who is providing feedback to the AI. You are the user in this conversation.

**Constraints:**

Do not provide the answer to the task or any information that directly reveals the answer to the task.
We should help the AI in giving them the approach without the specific details that reveal the answer directly.
"""


SYSTEM_MESSAGE_PLANNING_PHASE_SOFT = """
**Context:**
You are tasked with role playing as a human user who is interacting with an AI to solve a task for you. 

The task is: {task} 

The AI will provide a plan for the task in the past messages.

{helpful_task_hints}

{answer}

The AI has no knowledge of the answer to the task or the helpful hints. 

**INSTRUCTIONS:**

You need to provide a response to the AI's plan as the user.

Provide them with the helpful hints without revealing the answer to the task through the helpful hints.
The helpful hints should not include the direct answer but should allow the AI to solve the task.
"""


SYSTEM_MESSAGE_EXECUTION_PHASE_SOFT = """
**Context:**

You are tasked with role playing as a human user who is interacting with an AI to solve a task for you.

The task is: {task} 

{helpful_task_hints}

{answer}

The AI has no knowledge of the answer to the task or the helpful hints. 

The above messages include steps the AI has taken to solve the task.

The last message is a question the AI is asking you for help.

**INSTRUCTIONS:**
Provide a response to the AI's question to help them solve the task.

Provide the answer to the task to the AI directly.

"""


SYSTEM_MESSAGE_EXECUTION_PHASE_STRICT = """
**Context:**

You are tasked with role playing as a human user who is interacting with an AI to solve a task for you.

The task is: {task} 

{helpful_task_hints}

{answer}

The AI has no knowledge of the answer to the task or the helpful hints. 

The above messages include steps the AI has taken to solve the task.

The last message is a question the AI is asking you for help.

**INSTRUCTIONS:**
Provide a response to the AI's question to help them solve the task.

Your feedback should be based on the helpful hints and the answer to the task if they are available.

Remember that the AI has no knowledge of the answer to the task or the helpful hints so you can't reference them explicitly.

You can help the AI by telling them a good approach to solve the task and by commenting on the correctness of their tentative answer.

**Constraints:**
Do not provide the answer to the task or any information that directly reveals the answer to the task.

You can guide the AI by telling them if the answer is not correct, but you cannot tell them that it is correct.
"""


class MetadataUserProxy(BaseChatAgent):
    def __init__(
        self,
        name: str,
        description: str,
        model_client: ChatCompletionClient,
        task: str = "",
        helpful_task_hints: str = "",
        task_answer: str = "",
        simulated_user_type: Literal[
            "co-planning", "co-execution", "co-planning-and-execution", "none"
        ] = "none",
        max_co_planning_rounds: int = 1,
        max_co_execution_rounds: int = 1,
        model_context_token_limit: int = 110000,
        how_helpful: Literal["strict", "soft"] = "soft",
    ):
        """
        Initialize a MetadataUserProxy agent that simulates a human user with access to task metadata.

        Args:
            name (str): Name of the agent
            description (str): Description of the agent's role
            model_client (ChatCompletionClient): Client for interacting with the language model
            task (str, optional): The task to be solved. Default: empty string.
            helpful_task_hints (str, optional): Additional hints to help solve the task. Default: empty string.
            task_answer (str, optional): The known answer to the task. Default: empty string.
            simulated_user_type (Literal["co-planning", "co-execution", "co-planning-and-execution", "none"], optional):
                Type of user simulation. Default: "none".
            max_co_planning_rounds (int, optional): Maximum number of planning rounds. Default: 1.
            max_co_execution_rounds (int, optional): Maximum number of execution rounds. Default: 1.
            model_context_token_limit (int, optional): Token limit for model context. Default: 128000.
            how_helpful (Literal["strict", "soft"], optional): How helpful the user is. Default: "soft".
        """

        super().__init__(name, description)
        self.task = task
        self.helpful_task_hints = (
            (
                "We have access to helpful hints that helps in solving the task: "
                + helpful_task_hints
            )
            if helpful_task_hints
            else "Helpful hints are not available for this task."
        )
        self.task_answer = (
            ("We know the answer to the task and it is: " + task_answer)
            if task_answer
            else "We don't know the answer to the task."
        )
        self._model_client = model_client
        self._model_context = TokenLimitedChatCompletionContext(
            model_client,
            token_limit=model_context_token_limit,
        )
        self.simulated_user_type = simulated_user_type
        self.in_planning_phase = True
        self.max_co_planning_rounds = max_co_planning_rounds
        self.current_co_planning_round = 0
        self.max_co_execution_rounds = max_co_execution_rounds
        self.current_co_execution_round = 0
        self._chat_history: List[LLMMessage] = []
        self.how_helpful = how_helpful

    def _get_system_message(self) -> str:
        """
        Generate the appropriate system message based on the current phase and helpfulness level.

        Returns:
            str: The system message for the current phase and helpfulness level.
        """
        if self.in_planning_phase:
            if self.how_helpful == "strict":
                return SYSTEM_MESSAGE_PLANNING_PHASE_STRICT.format(
                    task=self.task,
                    helpful_task_hints=self.helpful_task_hints,
                    answer=self.task_answer,
                )
            else:
                return SYSTEM_MESSAGE_PLANNING_PHASE_SOFT.format(
                    task=self.task,
                    helpful_task_hints=self.helpful_task_hints,
                    answer=self.task_answer,
                )
        else:
            if self.how_helpful == "strict":
                return SYSTEM_MESSAGE_EXECUTION_PHASE_STRICT.format(
                    task=self.task,
                    helpful_task_hints=self.helpful_task_hints,
                    answer=self.task_answer,
                )
            else:
                return SYSTEM_MESSAGE_EXECUTION_PHASE_SOFT.format(
                    task=self.task,
                    helpful_task_hints=self.helpful_task_hints,
                    answer=self.task_answer,
                )

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        """Get the types of messages produced by the agent."""
        return (TextMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        response: Response | None = None
        async for message in self.on_messages_stream(messages, cancellation_token):
            if isinstance(message, Response):
                response = message
        assert response is not None
        return response

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        chat_messages = thread_to_context(
            list(messages),
            agent_name=self.name,
            is_multimodal=self._model_client.model_info["vision"],
        )
        self._chat_history.extend(chat_messages)
        if (
            "type" in messages[-1].metadata
            and messages[-1].metadata["type"] == "plan_message"
        ):
            self.in_planning_phase = True
        else:
            self.in_planning_phase = False

        # Re-initialize model context to meet token limit quota
        await self._model_context.clear()

        # Create system message
        system_message = SystemMessage(content=self._get_system_message())

        # Add system message at start
        await self._model_context.add_message(system_message)

        # Add all chat history
        for msg in self._chat_history:
            await self._model_context.add_message(msg)

        # Add system message again at end
        user_system_message = UserMessage(
            content=self._get_system_message(), source="user"
        )
        await self._model_context.add_message(user_system_message)

        # Get token limited history
        token_limited_history = await self._model_context.get_messages()

        if self.in_planning_phase:
            if self.simulated_user_type in ["co-planning", "co-planning-and-execution"]:
                if self.current_co_planning_round < self.max_co_planning_rounds:
                    result = await self._model_client.create(
                        messages=token_limited_history,
                        cancellation_token=cancellation_token,
                    )
                    assert isinstance(result.content, str)

                    yield Response(
                        chat_message=TextMessage(
                            content=result.content,
                            source=self.name,
                            metadata={
                                "co_planning_round": str(
                                    self.current_co_planning_round
                                ),
                                "user_plan_reply": "llm",
                            },
                        ),
                        inner_messages=[],
                    )
                    self._chat_history.append(
                        AssistantMessage(
                            content=result.content,
                            source=self.name,
                        )
                    )
                    if "accept" in result.content:
                        self.in_planning_phase = False
                    self.current_co_planning_round += 1
                else:
                    yield Response(
                        chat_message=TextMessage(
                            content="accept",
                            source=self.name,
                            metadata={
                                "co_planning_round": str(
                                    self.current_co_planning_round
                                ),
                                "user_plan_reply": "accept",
                            },
                        ),
                        inner_messages=[],
                    )
                    self._chat_history.append(
                        AssistantMessage(
                            content="accept",
                            source=self.name,
                        )
                    )
                    self.in_planning_phase = False
            else:
                yield Response(
                    chat_message=TextMessage(
                        content="accept",
                        source=self.name,
                        metadata={
                            "co_planning_round": str(self.current_co_planning_round),
                            "user_plan_reply": "accept",
                        },
                    ),
                    inner_messages=[],
                )

                self.in_planning_phase = False
        else:
            if self.simulated_user_type in [
                "co-execution",
                "co-planning-and-execution",
            ]:
                if self.current_co_execution_round < self.max_co_execution_rounds:
                    result = await self._model_client.create(
                        messages=token_limited_history,
                        cancellation_token=cancellation_token,
                    )

                    assert isinstance(result.content, str)

                    yield Response(
                        chat_message=TextMessage(
                            content=result.content,
                            source=self.name,
                            metadata={
                                "user_execution_reply": "llm",
                            },
                        ),
                        inner_messages=[],
                    )
                    self._chat_history.append(
                        AssistantMessage(
                            content=result.content,
                            source=self.name,
                        )
                    )
                    self.current_co_execution_round += 1
                else:
                    yield Response(
                        chat_message=TextMessage(
                            content="I don't know, you figure it out, don't ask me again.",
                            source=self.name,
                        ),
                    )
            else:
                yield Response(
                    chat_message=TextMessage(
                        content="I don't know, you figure it out, don't ask me again.",
                        source=self.name,
                        metadata={
                            "user_execution_reply": "idk",
                        },
                    ),
                )

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """
        Reset the model context.
        """
        self._chat_history = []

    async def close(self) -> None:
        await self._model_client.close()
