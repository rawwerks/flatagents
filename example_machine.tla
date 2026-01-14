---- MODULE FlatMachineExample ----
EXTENDS Integers, Sequences, TLC

\* This TLA+ spec models a FlatMachine to verify properties
\* Based on a writer-critic loop example

CONSTANTS
    MaxScore,     \* Maximum score (e.g., 10)
    MaxRounds     \* Maximum iterations (max_steps)

VARIABLES
    state,        \* Current state: "start", "write", "review", "done", "error"
    context,      \* Context variables: [score, round, tagline]
    terminated    \* Has machine terminated?

vars == <<state, context, terminated>>

\* Type invariants
TypeOK ==
    /\ state \in {"start", "write", "review", "done", "error"}
    /\ context.score \in 0..MaxScore
    /\ context.round \in 0..MaxRounds
    /\ terminated \in BOOLEAN

\* Initial state
Init ==
    /\ state = "start"
    /\ context = [score |-> 0, round |-> 0, tagline |-> ""]
    /\ terminated = FALSE

\* Transitions (modeling FlatMachine state transitions)

TransitionToWrite ==
    /\ state = "start"
    /\ state' = "write"
    /\ UNCHANGED <<context, terminated>>

ExecuteWrite ==
    /\ state = "write"
    /\ state' = "review"
    /\ context' = [context EXCEPT !.tagline = "generated_tagline"]
    /\ UNCHANGED terminated

ExecuteReview ==
    /\ state = "review"
    /\ \E score \in 0..MaxScore:  \* Non-deterministic score (models LLM)
        /\ context' = [context EXCEPT
            !.score = score,
            !.round = context.round + 1]
        /\ IF score >= 8
           THEN state' = "done" /\ terminated' = TRUE
           ELSE state' = "write" /\ UNCHANGED terminated

ReachMaxSteps ==
    /\ context.round >= MaxRounds
    /\ state' = "error"
    /\ terminated' = TRUE
    /\ UNCHANGED context

\* Next state relation
Next ==
    \/ TransitionToWrite
    \/ ExecuteWrite
    \/ ExecuteReview
    \/ ReachMaxSteps
    \/ (terminated /\ UNCHANGED vars)  \* Stuttering step

\* Specification
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

\* PROPERTIES TO VERIFY

\* Safety: Machine never reaches invalid state
Safety == state \in {"start", "write", "review", "done", "error"}

\* Liveness: Machine eventually terminates
Termination == <>(terminated = TRUE)

\* Correctness: If done, score is >= 8
CorrectTermination ==
    (state = "done") => (context.score >= 8)

\* Bounded: Never exceed max_steps
BoundedExecution ==
    context.round <= MaxRounds

\* No Deadlock: Non-final states always have next transition
NoDeadlock ==
    (state \in {"start", "write", "review"}) => ENABLED Next

\* Reachability: Done state is reachable
DoneReachable == <>(state = "done")

====
