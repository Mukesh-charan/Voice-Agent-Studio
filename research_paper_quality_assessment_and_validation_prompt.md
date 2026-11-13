# Research Paper Overall Quality Assessment & Evidence-Driven Validation Prompt

**Purpose:** Use this document as the master prompt for an AI
coding/research agent that has access to the actual Voice Agent Studio
repository, experiment scripts, datasets, configuration files, logs, and
the journal manuscript.

**Manuscript title to use:** *Low-latency, privacy-aware conversational
voice agent studio with QUBO-based prompt and task optimization*

**Important:** This is an investigation and validation task, not a
request to rewrite the paper immediately. The agent must run the real
implementation where feasible, inspect the original evidence, and report
what is verified, contradicted, missing, or not reproducible. It must
not manufacture results to make the paper look stronger.

------------------------------------------------------------------------

# PART A --- MASTER PROMPT

Copy everything between the prompt markers and give it to the agent
operating in the actual project/repository environment.

## PROMPT START

You are acting as a senior research engineer, experimental auditor,
systems researcher, and journal-paper reviewer.

Your task is to perform a **focused, evidence-driven quality
assessment** of the research project and its manuscript:

**"Low-latency, privacy-aware conversational voice agent studio with
QUBO-based prompt and task optimization."**

The research proposes and evaluates two principal optimisation
components:

1.  **QPO (Quantum Prompt Optimizer):** prompt-directive selection
    formulated as a QUBO problem, with an Ising representation and QAOA
    evaluation.
2.  **QTP (Quantum Task Parallelizer):** dependency-aware task-stage
    assignment formulated as a QUBO problem, with classical
    scheduling/solver execution used in the runtime workflow.

The wider system includes speech recognition, retrieval, LLM inference,
streaming TTS, barge-in handling, telephony integration, Google
Workspace synchronisation, role-based access control, privacy controls,
and Docker deployment.

## 1. Primary objective

Determine whether the manuscript's central claims are supported by the
**real implementation and original experimental evidence**.

Do not assume that a value in the manuscript is correct merely because
it appears in a table, figure, abstract, conclusion, or code comment.

Inspect the actual source code, configuration, test data, experiment
outputs, raw logs, and generated artefacts. Run the relevant experiments
when the environment and dependencies permit.

Your goal is to produce a concise but sufficiently detailed evidence
package that can be pasted back into a research-review conversation and
used to make accurate, meaningful improvements to the manuscript.

### The investigation must answer these questions

-   Does the implemented QPO match the mathematical formulation in the
    paper?
-   Can the reported QPO objective and selected prompt configuration be
    reproduced?
-   Can the QAOA results be independently checked against the same QUBO
    objective?
-   Does the QTP implementation preserve all task dependencies?
-   Does the measured QTP completion time include every task claimed to
    be part of the transaction?
-   Are the reported latency percentiles calculated from real, correctly
    bounded measurements?
-   Are the voice-rule adherence and detail-retention metrics
    reproducible from the underlying annotations?
-   Are the retrieval quality claims supported by labelled relevance
    data?
-   Are telephony, interruption, synchronisation, privacy, and
    deployment claims supported by appropriate measurements?
-   Which statements in the manuscript are verified, partially
    supported, contradicted, not reproducible, or unsupported?
-   What is the smallest set of additional experiments or corrections
    needed to make the paper scientifically defensible?

## 2. Strict evidence and integrity rules

Follow these rules throughout the investigation.

1.  **Never fabricate data, measurements, logs, datasets, participants,
    annotations, confidence intervals, hardware details, or experiment
    outputs.**
2.  Never infer that an experiment succeeded because a script exists. A
    script is evidence of implementation, not evidence that it was
    successfully executed.
3.  Never treat a code comment, README claim, screenshot, or manually
    entered table value as equivalent to a raw measurement.
4.  Distinguish clearly between:
    -   `VERIFIED`: directly reproduced from source data or a repeatable
        execution.
    -   `SUPPORTED`: evidence exists, but independent reproduction is
        incomplete.
    -   `PARTIALLY VERIFIED`: only some components or conditions were
        confirmed.
    -   `CONTRADICTED`: reliable evidence conflicts with the manuscript
        claim.
    -   `NOT REPRODUCIBLE`: required code, data, environment, or logs
        are unavailable or execution fails.
    -   `NOT TESTED`: the investigation did not attempt the check.
    -   `NOT APPLICABLE`: the check does not apply to the
        implementation.
5.  For every important result, provide the evidence location: file
    path, function/class, command, log, dataset, test name, or output
    artefact. Include line numbers or record identifiers when available.
6.  Record the exact command used, relevant environment details,
    execution date, exit code, and whether the run completed.
7.  If a dependency, API credential, GPU, model, external service,
    dataset, or permission is unavailable, state that limitation. Do not
    silently substitute a different system.
8.  Do not send real customer data or secrets to external services. Do
    not expose API keys, tokens, passwords, personal data, or private
    records in the report.
9.  Do not make production calls, send real emails, create real calendar
    events, mutate customer databases, or trigger paid services without
    explicit authorisation.
10. Prefer deterministic, local, read-only tests. Use synthetic or
    anonymised fixtures where suitable.
11. Do not edit manuscript files, source code, datasets, or experiment
    records during this audit. If a temporary test or patch is needed,
    use a separate temporary copy and clearly identify it.
12. Do not add experiments merely to increase the number of results.
    Test only what is needed to verify the paper's claims.
13. If the evidence is insufficient, report the missing evidence and the
    minimum next action. Do not fill the gap with a plausible-looking
    number.
14. Separate source-derived facts from your own interpretation and
    recommendations.
15. Do not claim quantum advantage, production-grade reliability, zero
    network egress, or guaranteed transaction consistency unless the
    corresponding evidence directly supports the claim.

## 3. Repository and artefact discovery

Start by identifying the project structure. Do not assume filenames or
folder names.

Inspect, where present:

-   QPO implementation and prompt-directive definitions.
-   QUBO matrix construction and objective evaluation.
-   QAOA circuit, simulator, optimiser, measurement and decoding code.
-   Exact solver, brute-force solver, greedy solver and simulated
    annealing implementation.
-   QTP task definitions, dependency graph, stage assignment, dispatch
    and timing code.
-   Voice pipeline: ASR, retrieval, LLM, streaming, TTS and audio
    conversion.
-   Barge-in/VAD state machine and interruption handling.
-   Telephony bridge and media-stream handling.
-   Google Calendar/Gmail integration, retry logic, idempotency and
    transaction state.
-   RBAC, tenant isolation, PII masking and guardrails.
-   Dockerfiles, Compose files, runtime configuration and deployment
    scripts.
-   Test suites, benchmark scripts, datasets, annotations, CSV/JSON
    outputs and raw logs.
-   Manuscript source, figures, tables, bibliography and supplementary
    material, if available.

Produce a short artefact inventory containing:

  ------------------------------------------------------------------------
  Area               Relevant files    What they         Evidence
                                       implement         available?
  ------------------ ----------------- ----------------- -----------------
  QPO                Actual paths      Prompt            Yes/No/Partial
                                       optimisation      

  QUBO/Ising         Actual paths      Mathematical      Yes/No/Partial
                                       mapping           

  QAOA               Actual paths      Quantum           Yes/No/Partial
                                       optimisation      
                                       simulation        

  QTP                Actual paths      Task scheduling   Yes/No/Partial

  Voice pipeline     Actual paths      ASR/RAG/LLM/TTS   Yes/No/Partial

  Evaluation         Actual paths      Metrics and       Yes/No/Partial
                                       benchmarks        

  Privacy/security   Actual paths      Controls and      Yes/No/Partial
                                       evidence          

  Deployment         Actual paths      Docker/runtime    Yes/No/Partial
  ------------------------------------------------------------------------

Do not spend time documenting unrelated project files.

## 4. Validation workstream 1 --- QPO and QUBO correctness

### 4.1 Verify the implementation

Inspect the actual QPO objective and confirm how the code represents:

-   Binary selection variables (x_i).
-   Per-directive utility (v_i).
-   Pairwise conflict penalties (C\_{ij}).
-   Pairwise synergy rewards (S\_{ij}).
-   Directive token costs (t_i).
-   Target token budget (T).
-   Penalty coefficient (`\mu`{=tex}).

Compare the code with the manuscript's stated maximisation objective:

\[ `\max`{=tex}\_x `\left[
\sum_i v_i x_i
-\sum_{i<j}C_{ij}x_ix_j
+\sum_{i<j}S_{ij}x_ix_j
-\mu\left(\sum_i t_i x_i-T\right)^2
\right]`{=tex}\]

Check the conversion to the minimisation form:

\[ `\min`{=tex}\_{x`\in`{=tex}{0,1}^n}x^TQx \]

Verify diagonal and pairwise coefficients, matrix symmetry/convention,
indexing, and whether the implementation uses an upper-triangular or
symmetric matrix consistently.

### 4.2 Independent objective check

If the actual QUBO coefficients and solution bitstrings are available:

-   Recalculate the objective independently.
-   Confirm the selected directives correspond to the reported
    bitstring.
-   Confirm token cost and constraint satisfaction.
-   Compare the objective from the implementation with an independent
    calculation.
-   Check whether the same objective convention is used for every
    solver.

For a small instance, enumerate all feasible binary configurations if
computationally reasonable. Record the number of configurations examined
and the exact optimum.

### 4.3 Utility, conflict and synergy provenance

Find out where (v_i), (C\_{ij}), and (S\_{ij}) originate.

Classify each as:

-   Human-assigned.
-   Empirically measured.
-   Derived from annotations.
-   Learned/optimised.
-   Manually configured.
-   Unknown/not documented.

Do not invent a scoring methodology. Identify the exact source file or
experiment record that establishes the values.

### 4.4 Solver comparison

Where original experiment code and settings exist, validate:

-   Greedy Local Ascent.
-   Simulated Annealing.
-   Exact solver.
-   Brute-force enumeration.
-   QAOA at the reported depths.

For stochastic solvers, use the original number of trials if available.
Report mean, standard deviation, median, best/worst objective, runtime
distribution, and success rate only when the raw trial results exist.

Do not compare runtimes from different machines or incompatible timing
boundaries as if they were directly comparable.

### 4.5 Specific p=4 discrepancy

The manuscript reports:

-   Exact objective: 76.10.
-   Brute-force objective: 76.10.
-   QAOA p=2: 76.10.
-   QAOA p=4: 76.40, marked unvalidated.

Investigate the p=4 result.

-   Recover the bitstring or measured candidate.
-   Evaluate it using the same original QUBO objective.
-   Check feasibility and all constraints.
-   Check whether the exact and brute-force solvers use the same matrix
    and sign convention.
-   Check rounding, offsets, and whether an Ising energy is being
    compared with a QUBO score.
-   Determine whether 76.40 is a genuine feasible objective, a decoding
    error, an offset/sign error, a reporting error, or unresolved.

Do not replace 76.40 with 76.10 unless the original evidence establishes
that correction.

## 5. Validation workstream 2 --- Ising mapping and QAOA

Verify the binary-to-spin transformation:

\[ z_i=1-2x_i,`\qquad `{=tex}x_i=`\frac{1-z_i}{2}`{=tex} \]

Inspect the implementation of:

-   Local fields (h_i).
-   Couplings (J\_{ij}).
-   Constant energy offset.
-   Cost Hamiltonian.
-   Mixer Hamiltonian.
-   QAOA depth (p).
-   Parameter optimisation.
-   Measurement and bitstring decoding.

Check that the manuscript does not use the same symbol for the Ising
constant offset and the ground-state eigenvalue without distinction.

Record the actual simulator/backend, package versions, qubit count,
optimiser, initial parameters/seeds, stopping conditions, iteration
count, shots, and execution time, if available.

Clearly distinguish:

-   Classical statevector simulation.
-   Shot-based simulation.
-   Quantum hardware execution.

Do not describe a simulated experiment as physical quantum hardware
execution. Do not claim quantum speedup or advantage from matching a
small classical optimum.

## 6. Validation workstream 3 --- QTP formulation and real scheduling

### 6.1 Inspect the task model

Recover the actual task list, task durations, dependency edges, resource
constraints, stage count, and solver output for each benchmark size.

Verify:

-   Exactly one stage is assigned to each task.
-   Every predecessor executes before its dependent task.
-   No task is omitted.
-   No task is duplicated.
-   Concurrent tasks are actually allowed to overlap.
-   The dispatcher implements the schedule produced by the optimiser.
-   Retry and failure behaviour does not invalidate the timing result.

### 6.2 Verify the objective

Inspect the one-hot, precedence, stage-cost and synergy terms.

Determine whether the objective directly minimises actual makespan or is
a stage-assignment surrogate.

If it is a surrogate, describe it as such. Do not claim that the QUBO
objective is identical to wall-clock makespan.

### 6.3 Critical 420 ms versus 670 ms check

The manuscript's illustrative six task durations are:

  Task                Duration
  ----------------- ----------
  Database checks        25 ms
  SQLite commit          35 ms
  Voice synthesis       240 ms
  Google Calendar       450 ms
  Google Sheets         380 ms
  Webhook               670 ms

The serial total is 1,800 ms. The paper reports a QTP result of 420 ms.

If the 670 ms webhook is included in the same transaction and the timer
ends only after all tasks finish, a 420 ms full-completion makespan is
impossible for that workload.

Investigate the actual measurement boundary:

-   Timer start event.
-   Timer stop event.
-   Whether the webhook is included.
-   Whether 420 ms means user-facing response, local commit, first
    audio, or all-task completion.
-   Whether the 670 ms duration is a fixed task duration, a measured
    latency, or an illustrative value.
-   Whether all six tasks belong to the same benchmark instance.
-   Whether the N=10 benchmark contains additional tasks not listed in
    the example.

Use actual execution traces to determine the result. Do not infer a
corrected makespan.

### 6.4 Recompute speedup

If the original timings support it, calculate:

\[
`\text{Speedup}`{=tex}=`\frac{T_{\text{serial}}}{T_{\text{parallel}}}`{=tex}
\]

\[ `\text{Reduction}`{=tex}=
`\frac{T_{\text{serial}}-T_{\text{parallel}}}`{=tex}
{T\_{`\text{serial}`{=tex}}}`\times100`{=tex} \]

State exactly what each timer measures. Distinguish user-visible latency
from complete transaction makespan.

## 7. Validation workstream 4 --- voice quality, latency and retrieval

### 7.1 Voice-rule adherence

The manuscript reports 120 dialogue turns and four rule-level rates:

-   No Markdown: 95.8%.
-   No preambles: 92.5%.
-   At most one question: 96.7%.
-   At most three sentences: 93.3%.

The abstract reports 94.6% aggregate adherence.

Check whether 94.6% is the unweighted arithmetic mean of the four rates,
or whether a different aggregation was used.

The arithmetic mean of the displayed values is approximately 94.6%, but
this does not prove that the raw annotations support it.

Recover, if available:

-   Dialogue/test case IDs.
-   Expected rules.
-   Actual response.
-   Pass/fail annotation per rule.
-   Annotator instructions.
-   Human or automated evaluation method.
-   Disagreement resolution.
-   Denominators and missing cases.

Report exact counts alongside percentages. Do not invent confidence
intervals without counts.

### 7.2 Detail retention

The manuscript reports 74.9% detail retention.

Find the actual metric definition and calculation.

Determine whether it is fact recall, fact accuracy, reference-detail
retention, evaluator score, or another measure.

Recover the reference facts, response annotations, denominators, and
aggregation method.

If the underlying evidence is absent, classify the 74.9% result as not
independently reproducible and specify the minimum data required.

Do not rename the metric or substitute a plausible formula.

### 7.3 Latency

The manuscript reports these P50 component values:

-   ASR: 94.1 ms.
-   BM25: 0.05 ms.
-   LLM TTFT: 185.3 ms.
-   TTS first chunk: 68.0 ms.
-   Total V2V: 347.5 ms.

It also reports total V2V P90 430.1 ms and P99 523.3 ms.

Inspect the raw timing records and verify:

-   Start and end events for each metric.
-   Units and clock source.
-   Warm-up handling.
-   Sample count.
-   Percentile calculation method.
-   Whether failures/timeouts are included.
-   Whether component measurements overlap.
-   Whether total latency is measured independently.

Do not add component medians and present the sum as the total median. Do
not assume the total percentile is derivable from component percentiles.

### 7.4 Retrieval

The manuscript reports BM25 median latency of 0.05 ms, dense-vector
median latency of 95 ms, and BM25 P@1 of 98.4%.

Verify:

-   Corpus size and source.
-   Number of queries.
-   Query construction.
-   Relevance labels and annotator process.
-   Definition of P@1.
-   Retrieval implementation and index state.
-   Warm/cold timing.
-   Hardware and measurement method.
-   Whether BM25 and dense retrieval use comparable data and conditions.

A latency advantage does not establish retrieval-quality equivalence.
Report speed and quality separately.

## 8. Validation workstream 5 --- telephony, interruption and integrations

### 8.1 Barge-in

Inspect the actual VAD threshold, frame size, frame rate,
consecutive-frame condition, state transitions, audio cancellation and
queue-clearing logic.

The manuscript describes 512-sample frames at 16 kHz and three
consecutive frames, equivalent to 96 ms of frame data.

Verify this calculation and inspect actual measured interruption
latency.

Keep separate:

-   Detection delay.
-   Client playback cancellation.
-   Twilio clear-event buffer clearing.
-   Full interruption-to-listening delay.

The manuscript reports 108 ms for Twilio buffer clearing and 114 ms
median client-side interruption. Do not merge them into a single metric.

If labelled speech/noise data exist, calculate detection precision,
recall, false-trigger rate and missed-interruption rate. Otherwise state
that these metrics are unavailable.

### 8.2 Telephony

Verify the actual audio formats, sample rates, conversion code,
WebSocket handling, buffering, error handling and call-level timing
logs.

The manuscript reports 100 calls, 432.5 ms median end-to-end voice
latency, 518.2 ms P90, 45.0 ms PSTN transit latency, 18.4 ms jitter and
4.2 ms transcoding CPU time.

Confirm the source and measurement boundary for each value. Do not call
the system carrier-grade solely because it integrates with a telephony
provider.

### 8.3 Google Workspace and retry reliability

Inspect the actual implementation of:

-   Local transaction commit.
-   Outbox/saga state.
-   Idempotency keys.
-   Retry policy and backoff.
-   Timeout handling.
-   Duplicate prevention.
-   Partial failure recovery.
-   Calendar and Gmail response handling.

The manuscript reports 200 booking operations and no duplicate
bookings/conflicts.

Verify the raw operation outcomes, failures, retries, timeouts and test
conditions. Distinguish simulated packet loss from real network fault
injection.

Do not claim exactly-once delivery unless the implementation and
evidence establish it. Prefer precise wording such as idempotent retry
handling or duplicate suppression when that is what the system actually
provides.

## 9. Validation workstream 6 --- privacy, RBAC and deployment

### 9.1 Privacy and PII masking

Inspect the actual masking rules and test coverage for credit-card
numbers, phone numbers and passport identifiers.

Verify whether masking happens before logging, storage, model
transmission and external API calls.

If labelled test data exist, report precision, recall and
false-positive/false-negative examples using synthetic data.

Do not claim complete PII protection from a few regular expressions or a
Luhn check.

### 9.2 Network egress

The manuscript acknowledges that network egress was not monitored.

Determine whether any original network traces, firewall logs, proxy
logs, container network policies or packet captures exist.

Identify every external connection used by:

-   Cloud LLM mode.
-   Local LLM mode.
-   Telephony.
-   Google Workspace.
-   Logging/telemetry.
-   Model and package downloads.

Do not claim zero egress unless network-level evidence supports it. If
the system intentionally contacts external services, state the
destinations and purpose accurately.

### 9.3 RBAC and tenant isolation

Inspect role permissions and tests for Owner, Manager, Receptionist and
Viewer.

Test, using local synthetic fixtures, whether unauthorised actions are
rejected and whether one tenant can access another tenant's data.

Report actual test coverage, not just the existence of role definitions.

### 9.4 GPU and container resources

The manuscript describes an RTX 3060 Laptop GPU with 6 GB VRAM, mentions
a 2.5 GB VRAM limit, and reports 5,640 MB local inference GPU memory.

Investigate whether these refer to different limits, measurement scopes,
modes or configurations.

Recover actual peak VRAM, GPU utilisation, host RAM, CPU, container
limits, model quantisation and workload conditions.

Do not reconcile the values by assumption.

Also verify the reported 2.14 GB image size, 3.82-second cold start,
120-minute run, and 22.4% mean host CPU usage if logs exist.

## 10. Statistical and reporting quality

For every reported percentage or timing result, identify:

-   Sample size.
-   Number of independent runs.
-   Unit of analysis.
-   Mean/median and spread as appropriate.
-   Confidence interval, only if it can be calculated from real counts
    or raw measurements.
-   Exclusion criteria.
-   Missing or failed trials.
-   Hardware/software environment.

For stochastic optimisation, report run-to-run variability.

For latency, report percentiles and sample counts, not just a single
best result.

For binary compliance metrics, report numerator/denominator and a
suitable confidence interval when raw counts are available.

Do not add significance tests unless the data and experimental design
support them.

## 11. Manuscript claim audit

Create a claim-to-evidence matrix for the manuscript's central
statements.

At minimum include:

  --------------------------------------------------------------------------------------
  Manuscript   Reported          Implementation   Raw            Status      Required
  claim        value/statement   evidence         experimental               action
                                                  evidence                   
  ------------ ----------------- ---------------- -------------- ----------- -----------

  --------------------------------------------------------------------------------------

Include these claims where applicable:

-   QPO objective 76.10.
-   QAOA p=2 matches the exact optimum.
-   QAOA p=4 objective 76.40.
-   94.6% aggregate voice-rule adherence.
-   74.9% detail retention.
-   BM25 0.05 ms median and 98.4% P@1.
-   347.5 ms Cloud-Hybrid median V2V.
-   482.0 ms local GPU median V2V.
-   825.4 ms local CPU median V2V.
-   QTP 4.29× speedup and 420 ms result.
-   100% precedence validity across 300 trials.
-   100 telephony calls and reported latency.
-   200 booking operations and duplicate/conflict claims.
-   5,640 MB GPU memory and 2.5 GB limit.
-   120-minute Docker operation and 3.82-second cold start.
-   Privacy-aware/local deployment and any zero-egress implication.

If a claim is absent from the implementation or data, say so. Do not
assume that the manuscript's reported value is reproducible.

## 12. Overall quality assessment

Give a balanced assessment across these dimensions:

1.  Research problem and motivation.
2.  Novelty and contribution clarity.
3.  QPO mathematical correctness.
4.  QAOA implementation and experimental validity.
5.  QTP mathematical correctness.
6.  Scheduling and makespan validity.
7.  Voice-system engineering quality.
8.  Experimental design and dataset quality.
9.  Metric validity and statistical reporting.
10. Privacy/security evidence.
11. Reproducibility and artefact availability.
12. Manuscript clarity and claim discipline.

Use the following qualitative scale:

-   **Strong:** clear, appropriate, and supported by sufficient
    evidence.
-   **Good:** sound overall, with limited gaps that do not undermine the
    central result.
-   **Moderate:** meaningful contribution, but important validation or
    reporting gaps remain.
-   **Weak:** major methodological or evidential problems undermine the
    claim.
-   **Not assessable:** insufficient artefacts or data to make a fair
    judgement.

Do not invent a numerical quality score or acceptance probability. If a
numerical score is requested by the user later, define a transparent
rubric first and distinguish it from an official journal decision.

## 13. Minimal additional experiments

After inspecting the artefacts, recommend only the experiments needed to
resolve material uncertainties.

For each proposed experiment, state:

-   The claim it validates.
-   Why the existing evidence is insufficient.
-   Minimum required input.
-   Exact procedure.
-   Output metric.
-   Acceptance/interpretation rule.
-   Estimated effort: Low / Medium / High.
-   Whether it requires GPU, API credentials, paid services, or human
    annotation.

Prioritise experiments that can resolve the critical QTP, QAOA p=4,
VRAM, adherence, detail-retention and privacy questions.

Do not recommend a large new benchmark suite unless the existing
evidence shows it is necessary.

## 14. Required final output

Produce the report in the following structure. Keep it detailed enough
to be useful, but avoid unnecessary background explanations.

### Output 1 --- Executive quality assessment

-   Overall qualitative assessment.
-   Strongest contribution.
-   Most important weakness.
-   Whether the central research story is supported.
-   What can safely be claimed now.
-   What must not be claimed yet.

### Output 2 --- Artefact and execution summary

-   Repository/artefact paths inspected.
-   Commands executed.
-   Environment and hardware.
-   Tests completed.
-   Tests not run and why.
-   Any errors or unavailable dependencies.

### Output 3 --- Verified results table

  --------------------------------------------------------------------------
  Metric/claim   Manuscript value    Independently Status       Evidence
                                    observed value              
  -------------- ---------------- ---------------- ------------ ------------

  --------------------------------------------------------------------------

Use `Not available` rather than filling gaps.

### Output 4 --- Critical anomalies

For each anomaly:

-   ID.
-   Manuscript location.
-   Conflicting values or logic.
-   Actual evidence found.
-   Severity: Critical / High / Medium / Low.
-   Resolution: Resolved / Unresolved.
-   Exact next action.

### Output 5 --- Methodology and missing-evidence table

  Missing item   Why it matters   Existing evidence   Minimum action
  -------------- ---------------- ------------------- ----------------

### Output 6 --- Overall quality by dimension

Use the qualitative scale defined above and give one evidence-based
explanation per dimension.

### Output 7 --- Minimum experiment plan

List only the experiments required to resolve the most consequential
gaps.

### Output 8 --- Paste-ready research update

Finish with a compact, self-contained block in this exact style:

``` text
RESEARCH VALIDATION UPDATE

Project/manuscript:
Audit date:
Repository/commit:
Environment:

VERIFIED:
- ...

PARTIALLY VERIFIED:
- ...

CONTRADICTED:
- ...

NOT REPRODUCIBLE / NOT TESTED:
- ...

CRITICAL ANOMALIES:
1. ...
2. ...
3. ...

CONFIRMED METRICS:
- Metric:
  Manuscript value:
  Observed value:
  Sample size:
  Evidence:

MISSING EVIDENCE:
- ...

MINIMUM NEXT EXPERIMENTS:
1. ...
2. ...
3. ...

SAFE CLAIMS FOR THE PAPER:
- ...

CLAIMS TO WITHHOLD:
- ...

OVERALL QUALITY:
- Research contribution:
- Mathematical validity:
- Experimental validity:
- Systems implementation:
- Privacy/security evidence:
- Reproducibility:
- Manuscript readiness:

RECOMMENDED NEXT ACTION:
...
```

The paste-ready block must contain actual findings from the
investigation, not generic recommendations. It should be concise enough
to paste into another ChatGPT conversation without losing essential
context.

## 15. Final operating instruction

Work in stages, but do not stop after merely inspecting the README or
source code.

First discover the artefacts. Then trace the important claims to
implementation and original evidence. Run the safe, relevant checks.
Independently recompute the critical numerical results. Finally produce
the required report.

If a check cannot be completed, identify exactly what is missing and
stop short of inventing a result.

**Do not rewrite the journal paper in this task. Do not make cosmetic
changes to improve its apparent quality. The purpose is to establish
what is genuinely supported by the real system and what must be
corrected, qualified, measured, or removed.**

## PROMPT END

------------------------------------------------------------------------

# PART B --- HOW TO USE THIS PROMPT

1.  Open the actual Voice Agent Studio project in the coding agent or
    environment that can access its source files.
2.  Make sure the agent can access the experiment scripts, original
    outputs, logs and datasets---not just the README.
3.  Paste **Part A** as the task prompt.
4.  Allow read-only inspection and safe local tests first. Approve
    external API calls, paid services, or any data mutation separately.
5.  Ask the agent to return the complete report, especially the
    **Paste-ready research update**.
6.  Bring that update back into this conversation.

**Important:** The prompt is designed to audit the real implementation.
It does not assume that the previously reported manuscript figures have
already been reproduced.

# PART C --- HOW WE WILL TURN THE RESULTS INTO A BETTER PAPER

When you paste the validation update back here, the next review should
use this sequence:

  -----------------------------------------------------------------------
  Step                    What we will do         Expected outcome
  ----------------------- ----------------------- -----------------------
  1                       Compare actual results  Verified claim
                          with manuscript values  inventory

  2                       Resolve critical        Correct numerical
                          contradictions using    results
                          original evidence       

  3                       Identify unsupported or Claims to qualify or
                          unreproducible claims   remove

  4                       Identify the smallest   Focused validation plan
                          missing experiments     

  5                       Improve equations,      Reproducible research
                          methodology and metric  methods
                          definitions             

  6                       Improve result          Evidence-aligned
                          interpretation and      discussion
                          limitations             

  7                       Update the manuscript   Scientifically stronger
                          without changing its    paper
                          intended structure      
                          unnecessarily           
  -----------------------------------------------------------------------

## Final principle

**The real system and its original experimental records must determine
what the paper says---not the other way around.**

We should preserve valid contributions, correct only demonstrated
errors, add only meaningful missing evidence, and avoid making the
manuscript unnecessarily complicated.
