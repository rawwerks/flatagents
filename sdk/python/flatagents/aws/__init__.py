"""
AWS Backend implementations for FlatAgents.

Provides DynamoDB-based persistence, result storage, and locking,
plus SQS-based machine launching for distributed execution.

Usage:
    from flatagents.aws import DynamoDBBackend, DynamoDBLock, SQSInvoker
    
    backend = DynamoDBBackend(table_name="flatagents")
    machine = FlatMachine(
        config_file="machine.yml",
        persistence=backend,
        result_backend=backend,
        lock=DynamoDBLock(table_name="flatagents"),
        invoker=SQSInvoker(queue_url="https://sqs...")
    )

Requirements:
    pip install boto3
"""

from .dynamodb import DynamoDBBackend, DynamoDBLock
from .sqs import SQSInvoker, SQSWorkerHandler

__all__ = [
    "DynamoDBBackend",
    "DynamoDBLock",
    "SQSInvoker",
    "SQSWorkerHandler",
]
