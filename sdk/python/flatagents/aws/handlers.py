"""
Example Lambda handlers for FlatAgents on AWS.

These are templates - copy and customize for your deployment.
"""

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


def api_gateway_handler(event, context):
    """
    API Gateway handler for user-submitted jobs.
    
    Expected request body:
        {
            "machine": "machine-name",
            "input": {...}
        }
    
    Environment variables:
        DYNAMODB_TABLE: DynamoDB table name
        LAUNCH_QUEUE_URL: SQS queue URL for peer launches
        MACHINE_CONFIG_BUCKET: S3 bucket for machine configs (optional)
    """
    from flatagents import FlatMachine
    from flatagents.aws import DynamoDBBackend, DynamoDBLock, SQSInvoker
    
    # Parse request
    body = json.loads(event.get("body", "{}"))
    machine_name = body.get("machine", "default")
    input_data = body.get("input", {})
    
    # Load config (from bundled files or S3)
    config = load_machine_config(machine_name)
    
    # Initialize backends
    table_name = os.environ.get("DYNAMODB_TABLE", "flatagents")
    queue_url = os.environ.get("LAUNCH_QUEUE_URL")
    
    backend = DynamoDBBackend(table_name=table_name)
    lock = DynamoDBLock(table_name=table_name)
    invoker = SQSInvoker(queue_url=queue_url) if queue_url else None
    
    machine = FlatMachine(
        config_dict=config,
        persistence=backend,
        result_backend=backend,
        lock=lock,
        invoker=invoker
    )
    
    # Execute
    try:
        result = asyncio.run(machine.execute(input=input_data))
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "success",
                "result": result,
                "execution_id": machine.execution_id
            })
        }
    except Exception as e:
        logger.exception("Machine execution failed")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "error": str(e)
            })
        }


def sqs_worker_handler(event, context):
    """
    SQS worker handler for peer machine launches.
    
    Triggered by messages from the launch queue.
    
    Environment variables:
        DYNAMODB_TABLE: DynamoDB table name
        LAUNCH_QUEUE_URL: SQS queue URL (for nested launches)
    """
    from flatagents.aws import DynamoDBBackend, DynamoDBLock, SQSInvoker, SQSWorkerHandler
    
    table_name = os.environ.get("DYNAMODB_TABLE", "flatagents")
    queue_url = os.environ.get("LAUNCH_QUEUE_URL")
    
    handler = SQSWorkerHandler(
        persistence=DynamoDBBackend(table_name=table_name),
        result_backend=DynamoDBBackend(table_name=table_name),
        lock=DynamoDBLock(table_name=table_name),
        invoker=SQSInvoker(queue_url=queue_url) if queue_url else None
    )
    
    return asyncio.run(handler.process(event))


def s3_processor_handler(event, context):
    """
    S3 event handler for processing uploaded files.
    
    Determines machine based on S3 key prefix:
        documents/* -> document-analyzer
        images/* -> image-processor
    
    Environment variables:
        DYNAMODB_TABLE: DynamoDB table name
        LAUNCH_QUEUE_URL: SQS queue URL (optional)
    """
    import boto3
    from flatagents import FlatMachine
    from flatagents.aws import DynamoDBBackend, DynamoDBLock, SQSInvoker
    
    s3 = boto3.client("s3")
    table_name = os.environ.get("DYNAMODB_TABLE", "flatagents")
    queue_url = os.environ.get("LAUNCH_QUEUE_URL")
    
    backend = DynamoDBBackend(table_name=table_name)
    
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        
        # Determine machine based on prefix
        if key.startswith("documents/"):
            machine_name = "document-analyzer"
        elif key.startswith("images/"):
            machine_name = "image-processor"
        else:
            logger.info(f"Skipping {key} - no matching machine")
            continue
        
        # Get file content
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read()
        
        # Load and run machine
        config = load_machine_config(machine_name)
        machine = FlatMachine(
            config_dict=config,
            persistence=backend,
            result_backend=backend,
            lock=DynamoDBLock(table_name=table_name),
            invoker=SQSInvoker(queue_url=queue_url) if queue_url else None
        )
        
        result = asyncio.run(machine.execute(input={
            "content": content.decode("utf-8"),
            "source_bucket": bucket,
            "source_key": key
        }))
        
        # Write result back to S3
        s3.put_object(
            Bucket=bucket,
            Key=f"results/{key}.json",
            Body=json.dumps(result),
            ContentType="application/json"
        )
        
        logger.info(f"Processed {key} -> results/{key}.json")


def load_machine_config(machine_name: str) -> dict:
    """
    Load machine config from bundled files or S3.
    
    Override this function in your deployment to load configs
    from your preferred location.
    """
    import yaml
    
    # Try bundled config first
    config_path = f"machines/{machine_name}.yml"
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        pass
    
    # Try S3
    bucket = os.environ.get("MACHINE_CONFIG_BUCKET")
    if bucket:
        import boto3
        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=f"{machine_name}.yml")
        return yaml.safe_load(response["Body"].read())
    
    raise ValueError(f"Machine config not found: {machine_name}")
