"""Prompt Manager for handling agent prompt versions and canary releases."""

import random
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from bindu.server.storage.base import Storage
from bindu.utils.logging import get_logger

logger = get_logger("bindu.server.prompt_manager")

@dataclass
class PromptManager:
    """Manages prompt versions and canary routing."""

    storage: Storage
    canary_ratio: float = 0.1  # 10% traffic to candidate prompts

    async def get_active_prompt(self, agent_id: str) -> Optional[dict[str, Any]]:
        """Get the active prompt for an agent, applying canary routing logic.

        Logic:
        1. Fetch 'active' and 'candidate' prompts.
        2. If 'candidate' exists, randomly select it based on canary_ratio.
        3. Otherwise return 'active'.
        4. Fallback to None if neither exist.
        """
        if not hasattr(self.storage, "get_agent_prompts"):
            # If storage doesn't support prompts (e.g. MemoryStorage), return None
            return None

        prompts = await self.storage.get_agent_prompts(agent_id) # type: ignore

        active_prompt = next((p for p in prompts if p["state"] == "active"), None)
        candidate_prompt = next((p for p in prompts if p["state"] == "candidate"), None)

        # Traffic routing
        if candidate_prompt:
            if random.random() < self.canary_ratio:
                logger.info(f"Routing to candidate prompt for agent {agent_id} (version: {candidate_prompt['version']})")
                return candidate_prompt

        if active_prompt:
            logger.debug(f"Using active prompt for agent {agent_id} (version: {active_prompt['version']})")
            return active_prompt

        return None

    async def promote_candidate(self, prompt_id: UUID, agent_id: str) -> None:
        """Promote a candidate prompt to active and archive the previous active one."""
        if not hasattr(self.storage, "get_agent_prompts") or not hasattr(self.storage, "update_agent_prompt_state"):
             return

        prompts = await self.storage.get_agent_prompts(agent_id) # type: ignore
        active_prompt = next((p for p in prompts if p["state"] == "active"), None)

        # 1. Archive current active
        if active_prompt:
             await self.storage.update_agent_prompt_state(active_prompt["id"], "archived") # type: ignore

        # 2. Activate candidate
        await self.storage.update_agent_prompt_state(prompt_id, "active") # type: ignore
        logger.info(f"Promoted prompt {prompt_id} to active for agent {agent_id}")

    async def rollback_candidate(self, prompt_id: UUID) -> None:
        """Rollback a candidate prompt (archive it)."""
        if not hasattr(self.storage, "update_agent_prompt_state"):
            return

        await self.storage.update_agent_prompt_state(prompt_id, "archived") # type: ignore
        logger.info(f"Rolled back prompt {prompt_id}")
