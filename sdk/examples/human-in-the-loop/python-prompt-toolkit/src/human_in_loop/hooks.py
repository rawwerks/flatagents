"""
Human-in-the-Loop Hooks using prompt_toolkit.

Provides the human_review action that pauses execution
for human approval or feedback using prompt_toolkit
for multiline input and control code support.
"""

from typing import Any, Dict

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from flatagents import MachineHooks


# Define a simple style for the prompt
STYLE = Style.from_dict({
    'prompt': 'bold cyan',
    'info': 'italic gray',
})


class HumanInLoopHooks(MachineHooks):
    """
    Hooks for human-in-the-loop workflow using prompt_toolkit.
    
    The human_review action pauses execution and prompts the user
    for approval or feedback with full multiline editing support,
    control code handling, and a better terminal experience.
    """
    
    def __init__(self):
        # Create a reusable session for history support across revisions
        self.session = PromptSession(style=STYLE)
    
    async def on_action(self, action_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle custom actions."""
        if action_name == "human_review":
            return await self._human_review(context)
        return context
    
    async def _human_review(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pause for human review of the current draft.
        
        Uses prompt_toolkit for better input handling:
        - Multiline support (use Meta+Enter or Esc+Enter to submit)
        - Control code support (Ctrl+C to cancel, arrow keys, etc.)
        - History and editing capabilities
        
        Input:
        - 'y' or 'yes' (or empty) to approve
        - Any other input becomes feedback for revision
        """
        context["revision_count"] = int(context.get("revision_count", 0) or 0) + 1

        print("\n" + "=" * 60)
        print("HUMAN REVIEW REQUIRED")
        print("=" * 60)
        print(f"\nRevision #{context.get('revision_count', 1)}")
        print("\nCurrent Draft:")
        print("-" * 40)
        print(context.get("draft", "(No draft yet)"))
        print("-" * 40)
        print("\nEnter 'y' or 'yes' to approve, or provide multiline feedback.")
        print("(Press Meta+Enter or Esc+Enter to submit)")
        print()
        
        try:
            # Use prompt_async for proper async event loop integration
            response = await self.session.prompt_async(
                HTML('<prompt>Your response: </prompt>'),
                multiline=True,  # Enable multiline input; submit with Meta+Enter or Esc+Enter
            )
            response = response.strip()
        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C or Ctrl+D gracefully
            print("\n✗ Review cancelled. Approving by default.")
            context["human_approved"] = True
            context["human_feedback"] = None
            return context
        
        if response.lower() in ("y", "yes", ""):
            context["human_approved"] = True
            context["human_feedback"] = None
            print("✓ Draft approved!")
        else:
            context["human_approved"] = False
            context["human_feedback"] = response
            print("→ Feedback recorded. Requesting revision...")
        
        print("=" * 60 + "\n")
        return context
