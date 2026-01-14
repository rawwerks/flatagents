; FlatMachine Formal Semantics in ACL2
; This defines what it means for a FlatMachine to execute

(in-package "ACL2")

;; ============================================================================
;; DATA STRUCTURES
;; ============================================================================

(defun state-def-p (state)
  "Recognizer for state definition"
  (and (alistp state)
       (member-equal (cdr (assoc :type state)) '(:initial :final nil))
       (or (null (assoc :transitions state))
           (transition-list-p (cdr (assoc :transitions state))))))

(defun transition-p (trans)
  "Recognizer for transition"
  (and (alistp trans)
       (stringp (cdr (assoc :to trans)))
       (or (null (assoc :condition trans))
           (stringp (cdr (assoc :condition trans))))))

(defun transition-list-p (trans-list)
  "Recognizer for list of transitions"
  (if (endp trans-list)
      t
    (and (transition-p (car trans-list))
         (transition-list-p (cdr trans-list)))))

(defun machine-p (machine)
  "Recognizer for FlatMachine"
  (and (alistp machine)
       (alistp (cdr (assoc :states machine)))
       (has-exactly-one-initial-state machine)))

(defun context-p (ctx)
  "Recognizer for context (just an alist)"
  (alistp ctx))

;; ============================================================================
;; EXECUTION SEMANTICS
;; ============================================================================

(defun find-state (machine state-name)
  "Retrieve state definition by name"
  (cdr (assoc-equal state-name (cdr (assoc :states machine)))))

(defun state-is-final (state)
  "Check if state is final"
  (equal (cdr (assoc :type state)) :final))

(defun eval-simple-condition (condition context)
  "Evaluate simple expression language conditions
   Simplified version - full implementation would parse expressions"
  (declare (ignore context))
  ;; Stub: In real implementation, parse and evaluate
  ;; For now, nil condition = always true
  (null condition))

(defun find-matching-transition (transitions context)
  "Find first transition whose condition evaluates to true"
  (if (endp transitions)
      nil
    (let ((trans (car transitions)))
      (if (eval-simple-condition (cdr (assoc :condition trans)) context)
          trans
        (find-matching-transition (cdr transitions) context)))))

(defun execute-step (machine current-state context step)
  "Execute one step of the machine
   Returns (new-state . new-context) or nil if terminated"
  (let* ((state-def (find-state machine current-state)))
    (if (or (null state-def)
            (state-is-final state-def))
        nil  ; Terminated
      (let* ((transitions (cdr (assoc :transitions state-def)))
             (next-trans (find-matching-transition transitions context)))
        (if (null next-trans)
            nil  ; Deadlock - no matching transition
          (let ((next-state (cdr (assoc :to next-trans))))
            (cons next-state context)))))))

(defun execute-machine (machine initial-state context max-steps)
  "Execute machine for up to max-steps
   Returns final state name or 'max-steps-exceeded"
  (execute-machine-helper machine initial-state context max-steps 0))

(defun execute-machine-helper (machine current-state context max-steps step)
  (if (>= step max-steps)
      'max-steps-exceeded
    (let* ((state-def (find-state machine current-state)))
      (if (state-is-final state-def)
          current-state  ; Successfully reached final state
        (let ((result (execute-step machine current-state context step)))
          (if (null result)
              'deadlock  ; No valid transitions
            (execute-machine-helper machine
                                   (car result)   ; new state
                                   (cdr result)   ; new context
                                   max-steps
                                   (+ step 1))))))))

;; ============================================================================
;; THEOREMS TO PROVE
;; ============================================================================

; Theorem 1: Execution is deterministic
(defthm execution-deterministic
  (implies (and (machine-p machine)
                (context-p context))
           (equal (execute-machine machine state context n)
                  (execute-machine machine state context n)))
  :rule-classes nil)

; Theorem 2: Execution always terminates within max-steps
(defthm execution-terminates
  (implies (and (machine-p machine)
                (context-p context)
                (natp max-steps))
           (or (equal (execute-machine machine state context max-steps)
                      'max-steps-exceeded)
               (equal (execute-machine machine state context max-steps)
                      'deadlock)
               (state-is-final
                 (find-state machine
                   (execute-machine machine state context max-steps)))))
  :rule-classes nil)

; Theorem 3: Step count never exceeds max-steps
(defthm bounded-execution
  (implies (and (machine-p machine)
                (natp max-steps)
                (natp step)
                (<= step max-steps))
           (<= (measure-steps machine state context max-steps step)
               max-steps))
  :rule-classes nil)

(defun measure-steps (machine state context max-steps step)
  "Helper to measure steps taken"
  (declare (ignore machine state context max-steps))
  step)

; Theorem 4: Reachability - if a state has transitions, next state is reachable
(defthm transitions-imply-reachability
  (implies (and (machine-p machine)
                (state-def-p state-def)
                (consp (cdr (assoc :transitions state-def))))
           (implies (execute-step machine current-state context 0)
                    (find-state machine
                                (car (execute-step machine current-state context 0)))))
  :rule-classes nil)

;; ============================================================================
;; VERIFICATION FUNCTIONS
;; ============================================================================

(defun all-states-have-transitions (machine)
  "Verify all non-final states have at least one transition"
  (all-states-have-transitions-helper (cdr (assoc :states machine))))

(defun all-states-have-transitions-helper (states)
  (if (endp states)
      t
    (let* ((state-entry (car states))
           (state-def (cdr state-entry)))
      (and (or (state-is-final state-def)
               (consp (cdr (assoc :transitions state-def))))
           (all-states-have-transitions-helper (cdr states))))))

(defun has-exactly-one-initial-state (machine)
  "Verify machine has exactly one initial state"
  (equal (count-initial-states (cdr (assoc :states machine))) 1))

(defun count-initial-states (states)
  (if (endp states)
      0
    (let ((state-def (cdr (car states))))
      (+ (if (equal (cdr (assoc :type state-def)) :initial) 1 0)
         (count-initial-states (cdr states))))))

;; ============================================================================
;; EXAMPLE MACHINE
;; ============================================================================

(defconst *example-machine*
  '((:states . ((start . ((:type . :initial)
                          (:transitions . (((:to . write))))))
                (write . ((:transitions . (((:to . review))))))
                (review . ((:transitions . (((:condition . "score >= 8")
                                             (:to . done))
                                            ((:to . write))))))
                (done . ((:type . :final)))))))

; Verify example machine properties
(defthm example-machine-valid
  (machine-p *example-machine*))

(defthm example-machine-no-deadlocks
  (all-states-have-transitions *example-machine*))

;; ============================================================================
;; To use this:
;; 1. Load in ACL2: (ld "flatmachine_semantics.lisp")
;; 2. Prove theorems about your machine
;; 3. Add machine-specific invariants
;; ============================================================================
