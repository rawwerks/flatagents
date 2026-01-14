"""
FlatMachine Static Verifier
Checks common bugs in state machine configurations without executing them.
"""

from typing import Dict, Set, List, Optional
import yaml

class MachineVerificationError(Exception):
    """Raised when verification finds a bug."""
    pass

class FlatMachineVerifier:
    """Verifies FlatMachine configurations for common bugs."""

    def __init__(self, config: dict):
        self.config = config
        self.data = config.get('data', {})
        self.states = self.data.get('states', {})
        self.agents = self.data.get('agents', {})
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def verify_all(self) -> bool:
        """Run all verification checks. Returns True if no errors found."""
        self.verify_initial_state_exists()
        self.verify_final_states_exist()
        self.verify_all_states_reachable()
        self.verify_no_deadlocks()
        self.verify_agent_references()
        self.verify_transitions_exhaustive()
        self.verify_error_handlers()
        self.verify_no_infinite_loops_without_maxsteps()

        return len(self.errors) == 0

    def verify_initial_state_exists(self):
        """Ensure exactly one initial state exists."""
        initial_states = [name for name, state in self.states.items()
                         if state.get('type') == 'initial']

        if len(initial_states) == 0:
            self.errors.append("No initial state defined")
        elif len(initial_states) > 1:
            self.errors.append(f"Multiple initial states: {initial_states}")

    def verify_final_states_exist(self):
        """Ensure at least one final state exists."""
        final_states = [name for name, state in self.states.items()
                       if state.get('type') == 'final']

        if len(final_states) == 0:
            self.warnings.append("No final states defined - machine may run forever")

    def verify_all_states_reachable(self):
        """Check that all states are reachable from initial state."""
        initial_states = [name for name, state in self.states.items()
                         if state.get('type') == 'initial']

        if not initial_states:
            return  # Already reported error

        reachable = self._compute_reachable_states(initial_states[0])
        unreachable = set(self.states.keys()) - reachable

        if unreachable:
            self.errors.append(f"Unreachable states: {unreachable}")

    def _compute_reachable_states(self, start: str) -> Set[str]:
        """DFS to find all reachable states from start."""
        visited = set()
        stack = [start]

        while stack:
            state = stack.pop()
            if state in visited or state not in self.states:
                continue

            visited.add(state)

            # Add all transition targets
            transitions = self.states[state].get('transitions', [])
            for trans in transitions:
                target = trans.get('to')
                if target and target not in visited:
                    stack.append(target)

            # Add error handler targets
            on_error = self.states[state].get('on_error')
            if isinstance(on_error, str):
                stack.append(on_error)
            elif isinstance(on_error, dict):
                for error_state in on_error.values():
                    if error_state and error_state not in visited:
                        stack.append(error_state)

        return visited

    def verify_no_deadlocks(self):
        """Ensure non-final states have at least one transition."""
        for name, state in self.states.items():
            if state.get('type') == 'final':
                continue

            transitions = state.get('transitions', [])
            if not transitions:
                self.errors.append(
                    f"State '{name}' has no transitions (deadlock)"
                )

    def verify_agent_references(self):
        """Ensure all referenced agents exist."""
        for name, state in self.states.items():
            agent_ref = state.get('agent')
            if agent_ref and agent_ref not in self.agents:
                self.errors.append(
                    f"State '{name}' references undefined agent '{agent_ref}'"
                )

    def verify_transitions_exhaustive(self):
        """Check if transitions cover all cases (have unconditional fallback)."""
        for name, state in self.states.items():
            if state.get('type') == 'final':
                continue

            transitions = state.get('transitions', [])
            if not transitions:
                continue

            # Check if last transition has no condition (catch-all)
            last_trans = transitions[-1]
            if last_trans.get('condition'):
                self.warnings.append(
                    f"State '{name}' has no unconditional fallback transition "
                    f"(all transitions have conditions)"
                )

    def verify_error_handlers(self):
        """Check that error handler states exist."""
        for name, state in self.states.items():
            on_error = state.get('on_error')

            if isinstance(on_error, str):
                if on_error not in self.states:
                    self.errors.append(
                        f"State '{name}' error handler references "
                        f"non-existent state '{on_error}'"
                    )
            elif isinstance(on_error, dict):
                for error_type, error_state in on_error.items():
                    if error_state and error_state not in self.states:
                        self.errors.append(
                            f"State '{name}' error handler for '{error_type}' "
                            f"references non-existent state '{error_state}'"
                        )

    def verify_no_infinite_loops_without_maxsteps(self):
        """Warn if machine has cycles but no max_steps protection."""
        if self._has_cycles() and not self.data.get('settings', {}).get('max_steps'):
            self.warnings.append(
                "Machine has cycles but no max_steps limit - "
                "infinite loops are possible"
            )

    def _has_cycles(self) -> bool:
        """Check if state graph has cycles using DFS."""
        visited = set()
        rec_stack = set()

        def has_cycle_from(state: str) -> bool:
            visited.add(state)
            rec_stack.add(state)

            if state not in self.states:
                return False

            transitions = self.states[state].get('transitions', [])
            for trans in transitions:
                target = trans.get('to')
                if not target:
                    continue

                if target not in visited:
                    if has_cycle_from(target):
                        return True
                elif target in rec_stack:
                    return True  # Back edge = cycle

            rec_stack.remove(state)
            return False

        for state_name in self.states:
            if state_name not in visited:
                if has_cycle_from(state_name):
                    return True

        return False

    def report(self) -> str:
        """Generate verification report."""
        lines = []

        if self.errors:
            lines.append("ERRORS:")
            for error in self.errors:
                lines.append(f"  ❌ {error}")

        if self.warnings:
            lines.append("\nWARNINGS:")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")

        if not self.errors and not self.warnings:
            lines.append("✅ No issues found")

        return "\n".join(lines)


def verify_machine_file(filepath: str) -> bool:
    """Load and verify a FlatMachine YAML file."""
    with open(filepath) as f:
        config = yaml.safe_load(f)

    verifier = FlatMachineVerifier(config)
    success = verifier.verify_all()

    print(f"\nVerification Results for {filepath}:")
    print(verifier.report())

    return success


# Example usage
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python example_verifier.py <machine.yml>")
        sys.exit(1)

    success = verify_machine_file(sys.argv[1])
    sys.exit(0 if success else 1)
