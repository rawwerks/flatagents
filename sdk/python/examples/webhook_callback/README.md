# Long-Running Job with Callback Example

A comprehensive example demonstrating **checkpoint-safe polling** for long-running jobs that take minutes or hours to complete.

## Overview

This example shows how to:
1. **Submit long-running jobs** without blocking
2. **Poll status in a state loop** with checkpoints between iterations
3. **Survive process restarts** via checkpointing
4. **Use pluggable backends** (mock, HTTP polling, webhook server)
5. **Correctly separate** quick hook actions from long polling loops

## The Problem: Blocking vs Checkpointing

### ❌ Anti-Pattern: Blocking Hook

```python
# BAD: Blocks for hours, can't checkpoint mid-execution
def on_action(self, action_name, context):
    if action_name == "submit_and_wait":
        job_id = submit_job(...)  # Fast

        while not_complete:  # Could run for hours!
            time.sleep(60)
            status = check_status(...)

        # If process crashes here, we start over and submit a NEW job!
        return context
```

**Problems:**
- No checkpoints during polling loop
- Process crash → restart submits duplicate job
- Can't resume from where we left off

### ✅ Solution: State-Based Polling Loop

```yaml
states:
  submit_job:
    action: submit_job  # Quick: just get job_id
    transitions:
      - to: poll_status

  poll_status:
    action: poll_once  # Quick: single status check
    transitions:
      - condition: "context.status == 'completed'"
        to: process_results
      - to: poll_status  # Loop - checkpoints each iteration!
```

**Benefits:**
- Checkpoint after each poll
- Process crash → resumes polling same job_id
- No duplicate submissions!

## Architecture

```
┌──────────────┐
│    start     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ submit_job   │  Hook: Quick submit, get job_id
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ poll_status  │◄─┐ Hook: Single status check
└──────┬───────┘  │ (CHECKPOINT here!)
       │          │
       ├─completed│
       │          │
       ├─failed   │
       │          │
       └─pending──┘ Loop with checkpoints
```

## Key Components

### 1. Backend Interface (`backends/base.py`)

Abstract interface supporting multiple strategies:

```python
class CallbackBackend(ABC):
    async def submit(self, endpoint, data) -> Dict:
        """Quick job submission - returns job_id"""

    async def check_status(self, status_url, job_id) -> Dict:
        """Quick status check - returns immediately"""
```

### 2. Backend Implementations

#### MockBackend (`backends/mock.py`)
- Simulates long jobs in-memory
- No external dependencies
- Configurable completion time
- Perfect for testing/demos

```python
backend = MockBackend(
    checks_until_complete=5,  # Completes after 5 polls
    simulate_progress=True
)
```

#### PollingBackend (`backends/polling.py`)
- Real HTTP polling
- Works with any REST API
- Submit via POST, check via GET

```python
backend = PollingBackend(timeout=30.0)
```

#### WebhookServerBackend (`backends/webhook.py`)
- Embedded aiohttp server
- Receives webhook callbacks
- Falls back to polling
- Hybrid approach

```python
backend = WebhookServerBackend(
    host="localhost",
    port=8765,
    fallback_polling=True
)
```

### 3. Hook Actions (`hooks.py`)

Two quick actions (both < 30 seconds):

**submit_job:**
```python
async def _submit_job(self, context):
    result = await self.backend.submit(endpoint, data)
    context["job_id"] = result["job_id"]
    context["status_url"] = result["status_url"]
    return context
```

**poll_once:**
```python
async def _poll_once(self, context):
    status = await self.backend.check_status(
        context["status_url"],
        context["job_id"]
    )
    context["status"] = status["status"]
    context["result"] = status.get("result")
    return context
```

### 4. State Machine (`config/machine.yml`)

Checkpoint-safe polling loop:

```yaml
poll_status:
  action: poll_once  # Quick check
  transitions:
    - condition: "context.status == 'completed'"
      to: process_results
    - condition: "context.status == 'failed'"
      to: job_failed
    - condition: "context.poll_count >= context.max_polls"
      to: polling_timeout
    - to: poll_delay  # Continue polling

poll_delay:
  output_to_context:
    poll_count: "{{ context.poll_count + 1 }}"
  transitions:
    - to: poll_status  # Checkpoint happens here!
```

## Usage

### Basic (Mock Backend)

No external dependencies:

```bash
cd sdk/python/examples/webhook_callback

# Run with default settings
./run.sh --local

# Custom text
./run.sh "Process this dataset" --backend mock --local
```

### HTTP Polling Backend

Requires a compatible job service:

```bash
python -m webhook_callback.main "Process data" \
    --backend polling \
    --endpoint http://localhost:8000/jobs/submit \
    --max-polls 100 \
    --poll-interval 10
```

### Webhook Server Backend

Runs embedded server for callbacks:

```bash
python -m webhook_callback.main "Process data" \
    --backend webhook \
    --endpoint http://localhost:8000/jobs/submit
```

The backend starts a server on `localhost:8765` to receive callbacks.

### With Checkpointing

Enable persistence to survive crashes:

```bash
python -m webhook_callback.main "Process data" \
    --backend mock \
    --checkpoint-dir ./checkpoints
```

**Test restart resilience:**
1. Start the job
2. Kill the process mid-polling (Ctrl+C)
3. Restart with same checkpoint-dir
4. → Resumes polling the same job!

## Expected Job API

Your job service should provide:

### Submit Endpoint

**POST /jobs/submit**

Request:
```json
{
  "text": "Data to process",
  "callback_url": "http://localhost:8765/callback/{job_id}"  // optional
}
```

Response:
```json
{
  "job_id": "abc-123",
  "status_url": "http://api.example.com/jobs/abc-123",
  "status": "pending"
}
```

### Status Endpoint

**GET /jobs/{job_id}**

Response (in progress):
```json
{
  "status": "running",
  "progress": 45
}
```

Response (completed):
```json
{
  "status": "completed",
  "result": {
    "output": "Processed data...",
    "metrics": {...}
  }
}
```

Response (failed):
```json
{
  "status": "failed",
  "error": "Processing error message"
}
```

### Callback Endpoint (Optional)

For webhook backend, your service can POST to callback URL when complete:

**POST {callback_url}**

```json
{
  "status": "completed",
  "result": {...}
}
```

## Design Patterns

### Pattern 1: Simple Polling

```yaml
states:
  submit:
    action: submit_job
  poll:
    action: poll_once
    transitions:
      - condition: "done"
        to: complete
      - to: poll  # Loop
```

### Pattern 2: Polling with Delay

```yaml
states:
  poll:
    action: poll_once
  delay:
    # Add delay between polls
    output_to_context:
      next_poll: "{{ now() + poll_interval }}"
    transitions:
      - to: poll
```

### Pattern 3: Exponential Backoff

```yaml
states:
  poll:
    action: poll_once
  backoff:
    output_to_context:
      poll_interval: "{{ context.poll_interval * 2 }}"
      poll_interval_capped: "{{ [context.poll_interval * 2, 300] | min }}"
```

### Pattern 4: Hybrid Callback/Polling

```python
async def check_status(self, status_url, job_id):
    # Check for callback first
    callback = await self.check_callback_received(job_id)
    if callback:
        return callback  # Fast path

    # Fall back to polling
    return await self._http_poll(status_url)
```

## Hook Actions vs State Loops

### Use Hook Actions For:
- ✅ Quick operations (< 30 seconds)
- ✅ Idempotent operations
- ✅ API calls that return immediately
- ✅ Single status checks

### Use State Loops For:
- ✅ Long operations (minutes/hours)
- ✅ Repeated polling
- ✅ Operations needing checkpoints
- ✅ Resume-safe workflows

### Examples

**Hook Action (Good):**
```python
def on_action(self, action, context):
    # Quick: Submit and return immediately
    result = await api.submit_job(data)
    context["job_id"] = result["id"]
    return context
```

**State Loop (Good):**
```yaml
poll_status:
  action: check_once  # Quick check
  transitions:
    - to: poll_status  # Loop with checkpoint
```

**Blocking Hook (Bad):**
```python
def on_action(self, action, context):
    # BAD: Blocks for hours!
    job = await api.submit_job(data)
    while not job.complete:  # NO CHECKPOINTS!
        await sleep(60)
        job.refresh()
    return context
```

## Testing

### Test Mock Backend

```bash
python -m webhook_callback.main "Test data" --backend mock
```

### Test Checkpointing

```bash
# Start job
python -m webhook_callback.main "Test" \
    --backend mock \
    --checkpoint-dir ./test-checkpoints &

# Wait a few seconds, then kill it
sleep 5
kill %1

# Restart - should resume!
python -m webhook_callback.main "Test" \
    --backend mock \
    --checkpoint-dir ./test-checkpoints
```

### Create Test Server

Simple Flask server for testing:

```python
# test_server.py
from flask import Flask, request, jsonify
import uuid
import time

app = Flask(__name__)
jobs = {}

@app.route('/jobs/submit', methods=['POST'])
def submit():
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "submitted_at": time.time(),
        "data": request.json
    }
    return jsonify({
        "job_id": job_id,
        "status_url": f"http://localhost:8000/jobs/{job_id}"
    })

@app.route('/jobs/<job_id>')
def status(job_id):
    job = jobs.get(job_id, {})

    # Simulate processing time
    elapsed = time.time() - job.get("submitted_at", 0)

    if elapsed < 10:
        return jsonify({"status": "pending", "progress": 0})
    elif elapsed < 30:
        progress = int((elapsed - 10) / 20 * 100)
        return jsonify({"status": "running", "progress": progress})
    else:
        return jsonify({
            "status": "completed",
            "result": {"output": f"Processed: {job['data']}"}
        })

if __name__ == '__main__':
    app.run(port=8000)
```

Run it:
```bash
python test_server.py
```

Then test with real polling:
```bash
python -m webhook_callback.main "Test data" \
    --backend polling \
    --endpoint http://localhost:8000/jobs/submit
```

## Troubleshooting

**Job never completes:**
- Check max_polls setting
- Verify job endpoint returns correct status
- Check logs for polling errors

**Duplicate job submissions:**
- Using blocking hook instead of state loop?
- Checkpointing disabled?
- Check machine.yml structure

**Checkpoint restore fails:**
- Ensure same checkpoint-dir used
- Check directory permissions
- Verify checkpoint files not corrupted

**Webhook callbacks not received:**
- Check firewall/NAT settings
- Verify callback URL accessible
- Check webhook server logs
- Try fallback_polling=True

## Advanced Usage

### Custom Backend

Implement your own backend:

```python
from webhook_callback.backends import CallbackBackend

class MyCustomBackend(CallbackBackend):
    async def submit(self, endpoint, data):
        # Your submission logic
        return {"job_id": "...", "status_url": "..."}

    async def check_status(self, status_url, job_id):
        # Your status check logic
        return {"status": "completed", "result": {...}}
```

### Multiple Backends

Switch backends based on conditions:

```python
if config.use_webhooks:
    backend = WebhookServerBackend(...)
else:
    backend = PollingBackend(...)

machine = FlatMachine(
    config_file="machine.yml",
    hooks=LongRunningJobHooks(backend=backend)
)
```

### Monitoring

Add metrics to hooks:

```python
class MonitoredHooks(LongRunningJobHooks):
    def on_state_exit(self, state, context, output):
        if state == "poll_status":
            self.metrics.record("poll_count", context["poll_count"])
        return super().on_state_exit(state, context, output)
```

## See Also

- **webhook_action** example - Simple webhook integration
- **human_in_loop** example - Blocking hook actions (different pattern)
- FlatMachine checkpointing documentation
- Backend interface specification

## Key Takeaways

1. **Hook actions should be fast** (< 30 seconds)
2. **State loops handle long operations** with checkpoints
3. **Pluggable backends** enable different strategies
4. **Checkpointing enables resilience** across restarts
5. **Separation of concerns** improves testability
