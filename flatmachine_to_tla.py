"""
Convert FlatMachine YAML to TLA+ specification for formal verification.
"""

import yaml
from typing import Dict, Set, List

class FlatMachineToTLA:
    """Converts FlatMachine configs to TLA+ specifications."""

    def __init__(self, config: dict):
        self.config = config
        self.data = config.get('data', {})
        self.states = self.data.get('states', {})
        self.machine_name = self.data.get('name', 'Machine')

    def generate_tla(self) -> str:
        """Generate complete TLA+ module."""
        lines = [
            f"---- MODULE {self._sanitize_name(self.machine_name)} ----",
            "EXTENDS Integers, Sequences, TLC",
            "",
            "CONSTANTS MaxSteps",
            "",
            "VARIABLES",
            "    currentState,",
            "    context,",
            "    step,",
            "    terminated",
            "",
            "vars == <<currentState, context, step, terminated>>",
            "",
        ]

        # Type invariant
        lines.extend(self._generate_type_invariant())
        lines.append("")

        # Initial state
        lines.extend(self._generate_init())
        lines.append("")

        # Transitions
        lines.extend(self._generate_transitions())
        lines.append("")

        # Next relation
        lines.extend(self._generate_next())
        lines.append("")

        # Specification
        lines.append("Spec == Init /\ [][Next]_vars /\ WF_vars(Next)")
        lines.append("")

        # Properties
        lines.extend(self._generate_properties())
        lines.append("")

        lines.append("====")
        return "\n".join(lines)

    def _sanitize_name(self, name: str) -> str:
        """Convert name to valid TLA+ identifier."""
        return ''.join(c if c.isalnum() else '_' for c in name)

    def _generate_type_invariant(self) -> List[str]:
        """Generate TypeOK invariant."""
        state_names = set(self.states.keys())
        state_set = "{" + ", ".join(f'"{s}"' for s in state_names) + "}"

        return [
            "TypeOK ==",
            f"    /\\ currentState \\in {state_set}",
            "    /\\ step \\in 0..MaxSteps",
            "    /\\ terminated \\in BOOLEAN",
        ]

    def _generate_init(self) -> List[str]:
        """Generate Init predicate."""
        initial_state = self._find_initial_state()

        return [
            "Init ==",
            f'    /\\ currentState = "{initial_state}"',
            "    /\\ context = [score |-> 0]",  # Simplified - would extract from config
            "    /\\ step = 0",
            "    /\\ terminated = FALSE",
        ]

    def _find_initial_state(self) -> str:
        """Find the initial state."""
        for name, state in self.states.items():
            if state.get('type') == 'initial':
                return name
        return list(self.states.keys())[0]  # Fallback

    def _generate_transitions(self) -> List[str]:
        """Generate transition predicates for each state."""
        lines = []

        for state_name, state_def in self.states.items():
            if state_def.get('type') == 'final':
                continue

            transitions = state_def.get('transitions', [])

            for i, trans in enumerate(transitions):
                target = trans.get('to')
                condition = trans.get('condition')

                trans_name = f"Transition_{self._sanitize_name(state_name)}_{i}"

                lines.append(f"{trans_name} ==")
                lines.append(f'    /\\ currentState = "{state_name}"')

                if condition:
                    # Simplified - would parse condition properly
                    lines.append(f"    /\\ TRUE  \\* Condition: {condition}")

                lines.append(f'    /\\ currentState\' = "{target}"')

                # Check if target is final
                if self.states.get(target, {}).get('type') == 'final':
                    lines.append("    /\\ terminated' = TRUE")
                else:
                    lines.append("    /\\ UNCHANGED terminated")

                lines.append("    /\\ step' = step + 1")
                lines.append("    /\\ UNCHANGED context")
                lines.append("")

        # Max steps check
        lines.append("MaxStepsReached ==")
        lines.append("    /\\ step >= MaxSteps")
        lines.append("    /\\ terminated' = TRUE")
        lines.append("    /\\ UNCHANGED <<currentState, context, step>>")

        return lines

    def _generate_next(self) -> List[str]:
        """Generate Next state relation."""
        lines = ["Next =="]

        # All transitions
        for state_name, state_def in self.states.items():
            if state_def.get('type') == 'final':
                continue

            transitions = state_def.get('transitions', [])
            for i in range(len(transitions)):
                trans_name = f"Transition_{self._sanitize_name(state_name)}_{i}"
                lines.append(f"    \\/ {trans_name}")

        lines.append("    \\/ MaxStepsReached")
        lines.append("    \\/ (terminated /\\ UNCHANGED vars)")

        return lines

    def _generate_properties(self) -> List[str]:
        """Generate properties to verify."""
        final_states = [name for name, state in self.states.items()
                       if state.get('type') == 'final']

        lines = [
            "\\* PROPERTIES TO VERIFY",
            "",
            "\\* Safety: Type correctness maintained",
            "Safety == TypeOK",
            "",
            "\\* Liveness: Machine eventually terminates",
            "Termination == <>(terminated = TRUE)",
            "",
            "\\* Bounded: Never exceed MaxSteps",
            "BoundedExecution == step <= MaxSteps",
            "",
            "\\* No Deadlock: Non-final states can progress",
            "NoDeadlock ==",
            "    /\\ ~terminated",
        ]

        non_final = [name for name in self.states.keys()
                    if self.states[name].get('type') != 'final']
        if non_final:
            state_check = " \\/ ".join(f'currentState = "{s}"' for s in non_final)
            lines.append(f"    /\\ ({state_check})")

        lines.append("    => ENABLED Next")

        if final_states:
            lines.append("")
            lines.append("\\* Reachability: Final states are reachable")
            final_check = " \\/ ".join(f'currentState = "{s}"' for s in final_states)
            lines.append(f"FinalStateReachable == <>({final_check})")

        return lines


def convert_machine_to_tla(yaml_path: str, output_path: str):
    """Convert FlatMachine YAML to TLA+ spec."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    converter = FlatMachineToTLA(config)
    tla_spec = converter.generate_tla()

    with open(output_path, 'w') as f:
        f.write(tla_spec)

    print(f"Generated TLA+ spec: {output_path}")
    print("\nTo verify:")
    print("1. Install TLA+ Toolbox")
    print("2. Open the .tla file")
    print("3. Create a model with MaxSteps constant")
    print("4. Run TLC model checker")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python flatmachine_to_tla.py <machine.yml> <output.tla>")
        sys.exit(1)

    convert_machine_to_tla(sys.argv[1], sys.argv[2])
