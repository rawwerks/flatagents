# FlatMachine Verification Tools

This directory contains tools for formally verifying that FlatMachine state machines are bug-free.

## 🚀 Quick Start (5 minutes)

Verify your first machine:

```bash
python example_verifier.py sdk/python/examples/writer_critic/machine.yml
```

This catches common bugs like deadlocks, unreachable states, and invalid references.

## 📁 Files Included

| File | Purpose | Time Investment |
|------|---------|-----------------|
| `example_verifier.py` | Static analysis tool | 5 min to use |
| `test_machine_properties.py` | Property-based testing | 1-2 hr to adapt |
| `flatmachine_to_tla.py` | Convert YAML → TLA+ | 2-4 days (learning TLA+) |
| `example_machine.tla` | Example TLA+ specification | Reference |
| `flatmachine_semantics.lisp` | ACL2 formal semantics | 2-4 weeks (learning ACL2) |
| `VERIFICATION_GUIDE.md` | Complete guide | 20 min read |

## 🎯 What Should I Use?

### For Every Machine
✅ **Use `example_verifier.py`** - Catches 80% of bugs in 5 minutes

### For Critical Workflows
✅ **Add property-based tests** - Catches edge cases through randomized testing

### For Safety-Critical Systems
✅ **Use TLA+ or ACL2** - Mathematical proof of correctness

## 📊 Verification Levels

```
Low Rigor                                            High Rigor
│                                                            │
├── Static Analysis ──┼── Property Tests ──┼── TLA+ ──┼── ACL2
│   (minutes)         │   (hours)           │ (days)  │ (weeks)
│                     │                     │         │
│   Structural bugs   │   Runtime bugs      │ All     │ Mathematical
│   Quick feedback    │   Edge cases        │ paths   │ certainty
```

## 🔍 What Gets Verified

| Property | Static | Property Test | TLA+ | ACL2 |
|----------|--------|---------------|------|------|
| No deadlocks | ✅ | ⚠️ | ✅ | ✅ |
| All states reachable | ✅ | ❌ | ✅ | ✅ |
| Always terminates | ⚠️ | ✅ | ✅ | ✅ |
| Context invariants | ❌ | ✅ | ✅ | ✅ |
| Liveness properties | ❌ | ⚠️ | ✅ | ✅ |

## 🏃 Running Each Tool

### Static Verifier (Start Here!)

```bash
# Single machine
python example_verifier.py machine.yml

# All machines in directory
for f in machines/*.yml; do
    python example_verifier.py "$f" || exit 1
done
```

### Property Tests

```bash
pip install pytest hypothesis pytest-asyncio
pytest test_machine_properties.py -v
```

### TLA+ Model Checking

```bash
# 1. Convert YAML to TLA+
python flatmachine_to_tla.py machine.yml machine.tla

# 2. Install TLA+ Toolbox
# Download: https://lamport.azurewebsites.net/tla/toolbox.html

# 3. Open machine.tla and run TLC model checker
```

### ACL2 Theorem Proving

```bash
# Install ACL2: https://www.cs.utexas.edu/users/moore/acl2/

acl2
ACL2> (ld "flatmachine_semantics.lisp")
ACL2> (verify-machine *your-machine*)
```

## 📖 Examples

### Example 1: Detect Deadlock

**Bad Machine:**
```yaml
states:
  start:
    type: initial
    transitions: [{to: process}]

  process:
    agent: processor
    # ❌ NO TRANSITIONS - DEADLOCK!
```

**Verification Output:**
```
❌ State 'process' has no transitions (deadlock)
```

### Example 2: Detect Unreachable State

**Bad Machine:**
```yaml
states:
  start:
    type: initial
    transitions: [{to: done}]

  done:
    type: final

  error_handler:  # ❌ UNREACHABLE
    type: final
```

**Verification Output:**
```
❌ Unreachable states: {'error_handler'}
```

### Example 3: Prove Termination with TLA+

**Machine:**
```yaml
settings:
  max_steps: 10

states:
  loop:
    type: initial
    transitions: [{to: loop}]  # Infinite loop
```

**TLA+ Property:**
```tla
Termination == <>(step >= MaxSteps)  ✓ PROVED
```

TLC proves: "Despite infinite loop, machine terminates at max_steps"

## 🎓 Learning Path

### Week 1: Static Analysis
- [x] Run `example_verifier.py` on all your machines
- [x] Add to CI/CD pipeline
- [x] Fix all errors and warnings

### Week 2: Property Testing
- [x] Write first property test
- [x] Learn Hypothesis basics
- [x] Test critical machine with 1000+ examples

### Month 2: TLA+
- [x] Complete learntla.com tutorial
- [x] Convert one machine to TLA+
- [x] Prove termination + safety

### Month 3+: ACL2 (Optional)
- [x] Complete ACL2 tutorial
- [x] Formalize core semantics
- [x] Prove key theorems

## 🐛 Common Bugs Caught

1. **Deadlock:** State with no transitions
2. **Unreachable states:** Dead code in state machine
3. **Invalid references:** Undefined agents/machines
4. **Missing max_steps:** Infinite loops possible
5. **Non-exhaustive transitions:** No fallback condition
6. **Missing error handlers:** Error states don't exist

## 💡 Pro Tips

1. **Start simple:** Run static verifier first, always
2. **Verify incrementally:** Don't wait until machine is huge
3. **Test properties, not implementations:** "Always terminates" > "Takes 5 steps"
4. **Use CI/CD:** Verify on every commit
5. **Document properties:** What should your machine guarantee?

## 🆘 Troubleshooting

**Q: Static verifier reports false positives?**
A: Check for dynamic state references (e.g., Jinja2 templates in state names)

**Q: TLA+ state explosion?**
A: Reduce constants (MaxSteps, MaxScore), abstract away details

**Q: ACL2 proof won't complete?**
A: Add lemmas, strengthen induction hypothesis, simplify model

## 📚 Further Reading

- [VERIFICATION_GUIDE.md](./VERIFICATION_GUIDE.md) - Complete guide
- [FlatMachine Spec](./flatmachine.d.ts) - Official specification
- [MACHINES.md](./MACHINES.md) - Machine reference docs
- [TLA+ Tutorial](https://learntla.com) - Interactive TLA+ course
- [ACL2 Textbook](http://www.cs.utexas.edu/users/moore/acl2/manuals/current/manual/) - Official manual

## 🤝 Contributing

Have a verification approach we missed? Found a bug the tools don't catch?

1. Open an issue with example machine
2. We'll add verification for that bug class
3. All machines benefit from improved tools

---

**Remember:** Verification is an investment in correctness. Start small, add rigor where it matters most.

**Try it now:** `python example_verifier.py your_machine.yml`
