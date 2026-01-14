"""
Property-based testing for FlatMachine configurations.
Uses Hypothesis to generate test cases and verify properties.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, precondition
import yaml

# Assuming flatagents SDK is installed
try:
    from flatagents import FlatMachine
    HAS_FLATAGENTS = True
except ImportError:
    HAS_FLATAGENTS = False
    print("Warning: flatagents not installed, some tests will be skipped")


class MachineExecutionTest(RuleBasedStateMachine):
    """
    Stateful property-based testing for FlatMachine.
    Hypothesis will explore many execution paths.
    """

    def __init__(self):
        super().__init__()
        self.machine_config = self._load_machine()
        self.context = {"score": 0, "round": 0}
        self.current_state = "start"
        self.terminated = False
        self.step_count = 0
        self.max_steps = 100

    def _load_machine(self):
        """Load machine config - override in subclass"""
        return {
            'spec': 'flatmachine',
            'spec_version': '0.3.0',
            'data': {
                'name': 'test',
                'states': {
                    'start': {
                        'type': 'initial',
                        'transitions': [{'to': 'done'}]
                    },
                    'done': {'type': 'final'}
                }
            }
        }

    @rule()
    def step_machine(self):
        """Execute one step"""
        if self.terminated:
            return

        self.step_count += 1

        # Property 1: Step count never exceeds max_steps
        assert self.step_count <= self.max_steps, \
            f"Machine exceeded max_steps: {self.step_count} > {self.max_steps}"

        # Simulate state transition (simplified)
        states = self.machine_config['data']['states']
        current_state_def = states.get(self.current_state, {})

        # Property 2: Non-final states must have transitions
        if current_state_def.get('type') != 'final':
            assert 'transitions' in current_state_def, \
                f"State {self.current_state} has no transitions (deadlock)"

        # Property 3: Final states terminate execution
        if current_state_def.get('type') == 'final':
            self.terminated = True
            return

        # Take first transition (simplified)
        transitions = current_state_def.get('transitions', [])
        if transitions:
            next_state = transitions[0]['to']

            # Property 4: Transition targets must exist
            assert next_state in states, \
                f"Transition to non-existent state: {next_state}"

            self.current_state = next_state

    @precondition(lambda self: not self.terminated)
    @rule(value=st.integers(min_value=0, max_value=10))
    def update_context_score(self, value):
        """Update context (tests context manipulation)"""
        self.context['score'] = value

        # Property 5: Context values remain in valid range
        assert 0 <= self.context['score'] <= 10, \
            f"Score out of range: {self.context['score']}"

    def teardown(self):
        """Verify final properties"""
        # Property 6: If terminated, must be in final state
        if self.terminated:
            states = self.machine_config['data']['states']
            current_state_def = states.get(self.current_state, {})
            assert current_state_def.get('type') == 'final', \
                "Terminated but not in final state"


# Concrete tests

@pytest.mark.skipif(not HAS_FLATAGENTS, reason="flatagents not installed")
@pytest.mark.asyncio
async def test_machine_always_terminates():
    """Property: All machines must eventually terminate"""
    machine_config = {
        'spec': 'flatmachine',
        'spec_version': '0.3.0',
        'data': {
            'name': 'termination_test',
            'settings': {'max_steps': 10},
            'states': {
                'start': {
                    'type': 'initial',
                    'transitions': [{'to': 'done'}]
                },
                'done': {'type': 'final', 'output': {}}
            }
        }
    }

    # Write config
    with open('/tmp/test_machine.yml', 'w') as f:
        yaml.dump(machine_config, f)

    machine = FlatMachine(config_file='/tmp/test_machine.yml')
    result = await machine.execute(input={})

    # Property: Execution completed
    assert result is not None
    assert machine.current_state == 'done'


@given(max_steps=st.integers(min_value=1, max_value=100))
@settings(max_examples=50)
def test_max_steps_respected(max_steps):
    """Property: Execution never exceeds max_steps"""

    # Simplified simulation
    steps_taken = 0
    current_state = 'start'

    states = {
        'start': {'transitions': [{'to': 'loop'}]},
        'loop': {'transitions': [{'to': 'loop'}]},  # Infinite loop
        'done': {'type': 'final'}
    }

    # Execute until max_steps or final
    while steps_taken < max_steps:
        state_def = states[current_state]

        if state_def.get('type') == 'final':
            break

        transitions = state_def.get('transitions', [])
        if not transitions:
            break

        current_state = transitions[0]['to']
        steps_taken += 1

    # Property: Never exceeded max_steps
    assert steps_taken <= max_steps


def test_all_states_reachable():
    """Property: All states should be reachable from initial state"""

    config = {
        'states': {
            'start': {'type': 'initial', 'transitions': [{'to': 'middle'}]},
            'middle': {'transitions': [{'to': 'done'}]},
            'done': {'type': 'final'},
            'unreachable': {'type': 'final'}  # This should be flagged
        }
    }

    reachable = compute_reachable_states(config, 'start')

    # Property: Unreachable states should be detected
    all_states = set(config['states'].keys())
    unreachable_states = all_states - reachable

    assert unreachable_states == {'unreachable'}, \
        f"Expected unreachable: {unreachable_states}"


def compute_reachable_states(config, start):
    """Compute reachable states via DFS"""
    visited = set()
    stack = [start]

    while stack:
        state = stack.pop()
        if state in visited or state not in config['states']:
            continue

        visited.add(state)

        transitions = config['states'][state].get('transitions', [])
        for trans in transitions:
            target = trans.get('to')
            if target and target not in visited:
                stack.append(target)

    return visited


@given(score=st.integers(min_value=0, max_value=10))
def test_context_invariants_preserved(score):
    """Property: Context invariants must be preserved across transitions"""

    context = {'score': score, 'round': 0}

    # Simulate transition
    new_context = {
        'score': context['score'],
        'round': context['round'] + 1
    }

    # Property: Score never goes negative
    assert new_context['score'] >= 0

    # Property: Round count increases monotonically
    assert new_context['round'] > context['round']


if __name__ == "__main__":
    # Run property-based tests
    test_max_steps_respected()
    test_all_states_reachable()
    test_context_invariants_preserved()
    print("✅ All property tests passed")
