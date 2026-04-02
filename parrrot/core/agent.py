"""
Parrrot — Main agent reasoning loop (think → tool calls → respond)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

from typing import Callable, Awaitable, Optional

from parrrot import config as cfg
from parrrot.core import memory
from parrrot.core.context import build_system_prompt
from parrrot.core.router import Router
from parrrot.models.base import CompletionRequest, Message
from parrrot.tools.registry import (
    load_all_tools,
    parse_tool_calls,
    registry,
    strip_tool_calls,
)

MAX_TOOL_ROUNDS = 25       # steps per continuation block
MAX_AUTO_CONTINUES = 5    # how many blocks before requiring user input
TOOL_ERROR_ESCALATION_THRESHOLD = 3
MAX_TOOL_ROUNDS_ADVANCED = 60
MAX_AUTO_CONTINUES_ADVANCED = 12


class Agent:
    """
    The main reasoning loop.

    Each call to `think_and_act` follows this flow:
    1. Build system prompt (with memory context)
    2. Call LLM
    3. Parse tool calls from response
    4. Execute tools, inject results back as messages
    5. Loop until no more tool calls OR auto-continue if still mid-task
    6. Return final response text
    """

    def __init__(
        self,
        on_tool_call: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_tool_result: Optional[Callable[[str, str], Awaitable[None]]] = None,
        confirm_callback: Optional[Callable[[str], Awaitable[bool]]] = None,
    ) -> None:
        self._router = Router()
        self._conversation: list[Message] = []
        self._on_tool_call = on_tool_call
        self._on_tool_result = on_tool_result
        self._confirm_callback = confirm_callback
        self._conf = cfg.load()

        # Load all tool modules
        load_all_tools()

    @staticmethod
    def _needs_advanced_planning(user_message: str) -> bool:
        """
        Heuristic gate for pre-planning complex tasks.
        This keeps simple requests fast while giving larger tasks
        a clearer execution structure.
        """
        text = user_message.lower()
        complexity_signals = [
            " and ",
            " then ",
            "after that",
            "step by step",
            "plan",
            "automate",
            "workflow",
            "multiple",
            "every day",
            "daily",
            "advanced",
            "research",
            "compare",
            "summarize and",
        ]
        signal_hits = sum(1 for signal in complexity_signals if signal in text)
        return len(user_message) > 120 or signal_hits >= 2

    async def _generate_execution_plan(self, system: str, task: str) -> str | None:
        """
        Ask the model for a concise internal plan before executing a complex task.
        Plan is stored in the conversation so the next reasoning loop can follow it.
        """
        planning_request = CompletionRequest(
            messages=[
                Message(
                    role="user",
                    content=(
                        "Create a concise execution plan for this task.\n"
                        "Return only plain text with 4-8 numbered steps.\n"
                        "Do not call any tools in this planning response.\n\n"
                        f"Task: {task}"
                    ),
                )
            ],
            system=system,
            temperature=0.2,
            max_tokens=500,
            stream=False,
        )
        response = await self._router.complete(planning_request)
        plan_text = strip_tool_calls(response.content).strip()
        if not plan_text:
            return None
        return plan_text

    @property
    def model_name(self) -> str:
        return self._router.active_model

    def clear_history(self) -> None:
        self._conversation = []

    async def think_and_act(
        self,
        user_message: str,
        stream_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """
        Process a user message and return the final response.
        Executes tool calls as needed in a loop with automatic continuation
        so long tasks never get cut off mid-way.
        """
        # Add user message to conversation
        self._conversation.append(Message(role="user", content=user_message))
        system = build_system_prompt(registry.tool_list_string())
        self._maybe_extract_facts(user_message)

        advanced = self._needs_advanced_planning(user_message)
        if advanced:
            plan_text = await self._generate_execution_plan(system, user_message)
            if plan_text:
                self._conversation.append(
                    Message(
                        role="assistant",
                        content=(
                            "Execution plan:\n"
                            f"{plan_text}\n\n"
                            "I will now execute this plan step by step."
                        ),
                    )
                )
                self._conversation.append(
                    Message(
                        role="user",
                        content=(
                            "Proceed with the plan now. Execute all required steps, "
                            "use tools as needed, and report final outcomes."
                        ),
                    )
                )

        max_auto_continues = MAX_AUTO_CONTINUES_ADVANCED if advanced else MAX_AUTO_CONTINUES
        max_tool_rounds = MAX_TOOL_ROUNDS_ADVANCED if advanced else MAX_TOOL_ROUNDS

        for _auto_continue in range(max_auto_continues):
            result = await self._run_tool_loop(
                system,
                stream_callback,
                force_cloud=False,
                max_tool_rounds=max_tool_rounds,
            )

            if result is not None:
                # Task finished cleanly
                if len(self._conversation) >= 20:
                    self._maybe_save_summary()
                return result

            # _run_tool_loop returned None → hit MAX_TOOL_ROUNDS mid-task.
            # Auto-continue: inject a nudge and keep going.
            self._conversation.append(
                Message(
                    role="user",
                    content=(
                        "You were mid-task and hit the step limit. "
                        "Continue exactly where you left off — keep going until fully done. "
                        "Do NOT restart from the beginning."
                    ),
                )
            )

        # Exhausted all auto-continues
        final = (
            "I completed as many steps as I could. "
            "Say 'continue' if you'd like me to keep going from where I left off."
        )
        self._conversation.append(Message(role="assistant", content=final))
        return final

    async def _run_tool_loop(
        self,
        system: str,
        stream_callback: Optional[Callable[[str], Awaitable[None]]],
        force_cloud: bool,
        max_tool_rounds: int,
    ) -> str | None:
        """
        Run up to MAX_TOOL_ROUNDS steps.
        Returns the final response string when done, or None if rounds ran out mid-task.
        """
        consecutive_tool_errors = 0
        use_cloud = force_cloud

        for _round in range(max_tool_rounds):
            request = CompletionRequest(
                messages=list(self._conversation),
                system=system,
                temperature=0.7,
                max_tokens=4096,
                stream=stream_callback is not None,
            )

            if stream_callback:
                full_response = ""
                async for token in await self._router.stream(request, force_cloud=use_cloud):
                    full_response += token
                    await stream_callback(token)
                response_text = full_response
            else:
                response = await self._router.complete(request, force_cloud=use_cloud)
                response_text = response.content

            tool_calls = parse_tool_calls(response_text)

            if not tool_calls:
                # No tool calls → task is done, this is the final answer
                clean = strip_tool_calls(response_text)
                self._conversation.append(Message(role="assistant", content=clean))
                return clean

            # Execute tool calls
            self._conversation.append(Message(role="assistant", content=response_text))

            tool_results: list[str] = []
            for tool_name, tool_args in tool_calls:
                if self._on_tool_call:
                    await self._on_tool_call(tool_name, tool_args)

                result = await registry.dispatch(
                    tool_name,
                    tool_args,
                    confirm_callback=self._confirm_callback,
                )

                if self._on_tool_result:
                    await self._on_tool_result(tool_name, result)

                tool_results.append(f"[Tool: {tool_name}]\nResult: {result}")
                if result.startswith("Error"):
                    consecutive_tool_errors += 1
                else:
                    consecutive_tool_errors = 0

            if (
                self._conf["model"].get("mode") == "hybrid"
                and not use_cloud
                and consecutive_tool_errors >= TOOL_ERROR_ESCALATION_THRESHOLD
            ):
                use_cloud = True
                tool_results.append(
                    "System: Multiple tool errors detected. Escalating reasoning to cloud "
                    "model for recovery while continuing execution."
                )
                consecutive_tool_errors = 0

            combined = "\n\n".join(tool_results)
            self._conversation.append(
                Message(role="user", content=f"Tool results:\n\n{combined}\n\nContinue.")
            )

        # Ran out of rounds — signal auto-continue needed
        return None

    def _maybe_extract_facts(self, text: str) -> None:
        """Simple heuristics to auto-remember facts from user messages."""
        lower = text.lower()
        if "my name is" in lower:
            parts = lower.split("my name is")
            if len(parts) > 1:
                name = parts[1].strip().split()[0].strip(".,!?")
                memory.remember("user_name", name)
                cfg.set_value("identity.user_name", name)
        if "i'm " in lower or "i am " in lower:
            pass  # Could extract occupation, location, etc.

    def _maybe_save_summary(self) -> None:
        """Summarize and compress conversation history when it gets long."""
        # Keep last 10 messages, summarize the rest
        old = self._conversation[:-10]
        self._conversation = self._conversation[-10:]
        summary_text = f"[Previous {len(old)} messages summarized and saved to memory]"
        memory.save_conversation_summary(old, summary_text)

    async def run_task(self, task: str) -> str:
        """Run a one-off autonomous task and return the result."""
        return await self.think_and_act(task)

    async def health_check(self) -> dict[str, bool]:
        return await self._router.health_check()
