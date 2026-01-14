# FlatMachine Formal Verification Guide

This guide explains how to formally verify that your FlatMachine state machines are bug-free.

## Quick Comparison

| Approach | Rigor | Setup Time | What It Catches | When to Use |
|----------|-------|------------|-----------------|-------------|
| **Static Analysis** | Low | Minutes | Structural bugs, deadlocks | Every machine, during development |
| **Property Testing** | Medium | Hours | Runtime bugs, edge cases | Before production |
| **TLA+ Model Checking** | High | Days | All execution paths, liveness | Critical workflows |
| **ACL2 Theorem Proving** | Highest | Weeks | Mathematical guarantees | Safety-critical systems |

---

## Approach 1: Static Analysis ⚡ (Start Here)

**Time to setup:** 5 minutes
**Skill required:** Basic Python
**Files:** `example_verifier.py`

### What It Catches

- ❌ Missing initial/final states
- ❌ Unreachable states (dead code)
- ❌ Deadlocks (states with no transitions)
- ❌ Invalid agent/machine references
- ❌ Missing error handler targets
- ❌ Cycles without `max_steps` protection
- ⚠️ Non-exhaustive transitions (missing fallback)

### How to Use

```bash
# Verify a single machine
python example_verifier.py sdk/python/examples/writer_critic/machine.yml

# Add to CI/CD
python example_verifier.py *.yml || exit 1
```

### Example Output

```
Verification Results for machine.yml:

ERRORS:
  ❌ State 'review' references undefined agent 'critic'
  ❌ Unreachable states: {'error_handler'}

WARNINGS:
  ⚠️  Machine has cycles but no max_steps limit - infinite loops are possible
  ⚠️  State 'process' has no unconditional fallback transition
```

### Limitations

- Only checks structure, not actual execution behavior
- Cannot verify complex conditions
- No liveness properties (e.g., "eventually reaches done")

### Recommendation

**Run on every machine before deploying.** Add to your pre-commit hooks.

---

## Approach 2: Property-Based Testing 🎲

**Time to setup:** 1-2 hours
**Skill required:** Python + pytest
**Files:** `test_machine_properties.py`

### What It Catches

- ✅ Step count never exceeds `max_steps`
- ✅ Context invariants preserved across transitions
- ✅ Termination in all scenarios
- ✅ Edge cases you didn't think of (Hypothesis generates them)

### How to Use

```bash
# Install dependencies
pip install pytest hypothesis pytest-asyncio

# Run property tests
pytest test_machine_properties.py -v

# Run with more examples (exhaustive)
pytest test_machine_properties.py --hypothesis-seed=42 --hypothesis-verbosity=verbose
```

### Example Properties

```python
@given(score=st.integers(min_value=0, max_value=10))
def test_score_in_valid_range(score):
    """Property: Score always remains in [0, 10]"""
    context = execute_with_score(score)
    assert 0 <= context['score'] <= 10

@given(max_steps=st.integers(min_value=1, max_value=100))
def test_terminates_within_max_steps(max_steps):
    """Property: Execution completes within max_steps"""
    steps = execute_machine(max_steps)
    assert steps <= max_steps
```

### Limitations

- Tests observed behavior, doesn't prove correctness
- May miss rare bugs (depends on random generation)
- Requires actual SDK execution (slower than static analysis)

### Recommendation

**Use for critical machines with complex logic.** Run in CI on PRs.

---

## Approach 3: TLA+ Model Checking 🔬

**Time to setup:** 2-4 days (learning curve)
**Skill required:** TLA+ knowledge
**Files:** `example_machine.tla`, `flatmachine_to_tla.py`

### What It Proves

- ✅ **Safety:** Bad states are never reached
- ✅ **Liveness:** Good states are eventually reached
- ✅ **Deadlock-freedom:** Machine can always progress
- ✅ **Termination:** Machine always finishes (or hits max_steps)
- ✅ **Invariants:** Properties hold in ALL execution paths

### How to Use

```bash
# Convert FlatMachine YAML to TLA+
python flatmachine_to_tla.py machine.yml machine.tla

# Open in TLA+ Toolbox
# 1. Install: https://lamport.azurewebsites.net/tla/toolbox.html
# 2. File → Open Spec → machine.tla
# 3. TLC Model Checker → New Model
# 4. Set constants (e.g., MaxScore=10, MaxRounds=5)
# 5. Run → TLC will exhaustively check all paths
```

### Example Properties

```tla
\* Property: Machine eventually terminates
Termination == <>(terminated = TRUE)

\* Property: If done, score >= 8
CorrectTermination == (state = "done") => (context.score >= 8)

\* Property: Never exceed max_steps
BoundedExecution == context.round <= MaxRounds
```

### TLC Output

```
TLC ran successfully:
- States checked: 1,247
- Distinct states: 156
- No errors found
- All properties satisfied
✓ Termination: PROVED
✓ CorrectTermination: PROVED
✓ BoundedExecution: PROVED
```

### Limitations

- **State explosion:** Large machines may have too many states to check
- **Learning curve:** TLA+ is a different paradigm
- **Manual conversion:** Auto-generation is simplified (conditions need manual modeling)

### Recommendation

**Use for critical workflows (financial, healthcare, safety).** Worth the investment for high-stakes machines.

---

## Approach 4: ACL2 Theorem Proving 🎓

**Time to setup:** 2-4 weeks (steep learning curve)
**Skill required:** ACL2 + formal logic
**Files:** `flatmachine_semantics.lisp`

### What It Proves

- ✅ **Mathematical certainty:** Properties hold for ALL inputs
- ✅ **Compositional:** Prove properties of components, compose them
- ✅ **Reusable:** Once proven, guaranteed forever
- ✅ **Exhaustive:** No edge cases missed

### Example Theorems

```lisp
; Theorem: Execution always terminates within max-steps
(defthm execution-terminates
  (implies (and (machine-p machine)
                (natp max-steps))
           (or (equal (execute-machine machine state ctx max-steps)
                      'max-steps-exceeded)
               (final-state-p (execute-machine machine state ctx max-steps)))))

; Theorem: No deadlocks if all non-final states have transitions
(defthm no-deadlocks
  (implies (and (machine-p machine)
                (all-states-have-transitions machine))
           (not (equal (execute-machine machine state ctx max-steps)
                       'deadlock))))
```

### How to Use

```bash
# Install ACL2
# Download from: https://www.cs.utexas.edu/users/moore/acl2/

# Load semantics
acl2
ACL2> (ld "flatmachine_semantics.lisp")

# Prove theorems
ACL2> (thm execution-terminates)
```

### Example Proof Session

```
ACL2 !> (defthm execution-terminates ...)

[Proof attempt]
Subgoal *1/2
  (implies (and (machine-p machine) ...)
           ...)
  [Induction on max-steps]

Subgoal *1/1
  [Base case: max-steps = 0]
  Q.E.D.

Theorem EXECUTION-TERMINATES proved!
```

### Limitations

- **Highest learning curve:** Months to become proficient
- **Time-intensive:** Proofs can take hours/days
- **Requires formalization:** Must model all semantics in ACL2
- **Not executable Python:** Proves properties of abstract model, not SDK directly

### Recommendation

**Only for safety-critical systems** (medical devices, aerospace, financial infrastructure). Overkill for most applications.

---

## Recommended Workflow

### For All Projects
1. ✅ **Static analysis** on every machine (5 min)
2. ✅ **Property tests** for complex machines (2 hr)

### For Critical Systems
3. ✅ **TLA+ model checking** for core workflows (2-4 days)

### For Safety-Critical Systems
4. ✅ **ACL2 theorem proving** for kernel logic (weeks)

---

## Bugs Each Approach Catches

| Bug Type | Static | Property Test | TLA+ | ACL2 |
|----------|--------|---------------|------|------|
| Missing initial state | ✅ | ❌ | ✅ | ✅ |
| Unreachable states | ✅ | ❌ | ✅ | ✅ |
| Deadlock | ✅ | ⚠️ | ✅ | ✅ |
| Infinite loop | ⚠️ | ✅ | ✅ | ✅ |
| Invalid transitions | ✅ | ✅ | ✅ | ✅ |
| Context corruption | ❌ | ✅ | ✅ | ✅ |
| Liveness bugs | ❌ | ⚠️ | ✅ | ✅ |
| Concurrency bugs | ❌ | ⚠️ | ✅ | ✅ |
| Edge cases | ❌ | ⚠️ | ✅ | ✅ |

✅ = Always catches
⚠️ = Sometimes catches (depends on test coverage)
❌ = Cannot catch

---

## Real-World Example

**Scenario:** Approve/reject workflow with retry logic

```yaml
states:
  start:
    type: initial
    transitions: [{to: review}]

  review:
    agent: reviewer
    execution:
      type: retry
      backoffs: [2, 8, 16]
    on_error: retry_exceeded
    transitions:
      - condition: "context.approved"
        to: done
      - to: reject

  reject:
    type: final
    output: {status: "rejected"}

  done:
    type: final
    output: {status: "approved"}

  retry_exceeded:
    type: final
    output: {status: "error"}
```

### What to Verify

**Static Analysis:**
- ✅ All states reachable
- ✅ No deadlocks
- ✅ Agent 'reviewer' exists

**Property Testing:**
- ✅ Retry never exceeds 3 attempts
- ✅ Always reaches final state (done/reject/retry_exceeded)
- ✅ Context.approved is boolean

**TLA+:**
- ✅ Eventually terminates (liveness)
- ✅ If approved, reaches 'done' (correctness)
- ✅ Retry backoff timing is correct

**ACL2:**
- ✅ Formal proof: ∀ inputs, machine terminates
- ✅ Formal proof: approved ⇒ status="approved"

---

## Quick Start Checklist

- [ ] Run `python example_verifier.py machine.yml` on all machines
- [ ] Add verification to CI/CD pipeline
- [ ] Write property tests for critical machines
- [ ] Consider TLA+ for high-stakes workflows
- [ ] Reserve ACL2 for safety-critical components only

---

## Resources

- **TLA+:** https://lamport.azurewebsites.net/tla/tla.html
- **ACL2:** https://www.cs.utexas.edu/users/moore/acl2/
- **Property Testing:** https://hypothesis.readthedocs.io/
- **FlatMachine Spec:** `flatmachine.d.ts` in this repo

---

## Next Steps

1. **Try the static verifier** on your machines right now
2. **Identify critical workflows** that need deeper verification
3. **Learn TLA+ basics** (interactive tutorial: learntla.com)
4. **Start small:** Verify one critical machine with TLA+
5. **Iterate:** Add more properties as you gain confidence

**Remember:** Perfect is the enemy of good. Start with static analysis, add rigor where it matters most.
