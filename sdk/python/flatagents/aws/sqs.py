"""
SQS-based machine invoker for distributed FlatAgents execution.

Enqueues machine launches to SQS, where worker Lambdas pick them up.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from ..actions import QueueInvoker

logger = logging.getLogger(__name__)

# Lazy import boto3
_boto3 = None

def _get_boto3():
    global _boto3
    if _boto3 is None:
        try:
            import boto3
            _boto3 = boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for AWS backends. "
                "Install with: pip install boto3"
            )
    return _boto3


class SQSInvoker(QueueInvoker):
    """
    SQS-based invoker for distributed machine launches.
    
    When a machine uses `launch:` or `machine:`, this invoker
    enqueues the launch to SQS. A worker Lambda picks up the
    message and executes the target machine.
    
    Args:
        queue_url: SQS queue URL for launch messages
        region: AWS region (optional, uses default if not specified)
        message_group_id: For FIFO queues (optional)
    
    Usage:
        invoker = SQSInvoker(queue_url="https://sqs.us-east-1.amazonaws.com/123/launches")
        machine = FlatMachine(
            config_file="machine.yml",
            invoker=invoker
        )
    
    Message Format:
        {
            "execution_id": "child-uuid",
            "config": {...machine config...},
            "input": {...input data...},
            "parent_execution_id": "parent-uuid"  # optional
        }
    """
    
    def __init__(
        self,
        queue_url: str,
        region: Optional[str] = None,
        message_group_id: Optional[str] = None
    ):
        self.queue_url = queue_url
        self.message_group_id = message_group_id
        
        boto3 = _get_boto3()
        if region:
            self._client = boto3.client("sqs", region_name=region)
        else:
            self._client = boto3.client("sqs")
    
    async def _enqueue(
        self,
        execution_id: str,
        config: Dict[str, Any],
        input_data: Dict[str, Any]
    ) -> None:
        """Enqueue a machine launch to SQS."""
        
        message_body = json.dumps({
            "execution_id": execution_id,
            "config": config,
            "input": input_data,
        })
        
        # Build send_message kwargs
        kwargs = {
            "QueueUrl": self.queue_url,
            "MessageBody": message_body,
        }
        
        # For FIFO queues
        if self.message_group_id:
            kwargs["MessageGroupId"] = self.message_group_id
            # Use execution_id as deduplication ID for exactly-once
            kwargs["MessageDeduplicationId"] = execution_id
        
        await asyncio.to_thread(
            self._client.send_message,
            **kwargs
        )
        
        logger.info(f"SQS: enqueued launch {execution_id} to {self.queue_url}")


class SQSWorkerHandler:
    """
    Helper for Lambda worker that processes SQS launch messages.
    
    Usage in Lambda handler:
        from flatagents.aws import SQSWorkerHandler, DynamoDBBackend, DynamoDBLock
        
        handler = SQSWorkerHandler(
            persistence=DynamoDBBackend(),
            result_backend=DynamoDBBackend(),
            lock=DynamoDBLock()
        )
        
        def lambda_handler(event, context):
            return asyncio.run(handler.process(event))
    """
    
    def __init__(
        self,
        persistence,
        result_backend,
        lock,
        invoker: Optional[SQSInvoker] = None
    ):
        self.persistence = persistence
        self.result_backend = result_backend
        self.lock = lock
        self.invoker = invoker
    
    async def process(self, sqs_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process SQS event containing machine launch messages.
        
        Args:
            sqs_event: Lambda event from SQS trigger
        
        Returns:
            Dict with processing results for each message
        """
        from ..flatmachine import FlatMachine
        
        results = []
        
        for record in sqs_event.get("Records", []):
            message_id = record.get("messageId", "unknown")
            
            try:
                body = json.loads(record["body"])
                
                execution_id = body["execution_id"]
                config = body["config"]
                input_data = body["input"]
                
                logger.info(f"Processing launch: {execution_id}")
                
                machine = FlatMachine(
                    config_dict=config,
                    persistence=self.persistence,
                    result_backend=self.result_backend,
                    lock=self.lock,
                    invoker=self.invoker,
                    _execution_id=execution_id,
                )
                
                # Resume if this is a retry (visibility timeout expired)
                result = await machine.execute(
                    input=input_data,
                    resume_from=execution_id
                )
                
                results.append({
                    "messageId": message_id,
                    "executionId": execution_id,
                    "status": "success",
                    "result": result
                })
                
            except Exception as e:
                logger.error(f"Failed to process message {message_id}: {e}")
                results.append({
                    "messageId": message_id,
                    "status": "error",
                    "error": str(e)
                })
                # Re-raise to trigger SQS retry / DLQ
                raise
        
        return {"processed": len(results), "results": results}
