"""
DynamoDB backends for FlatAgents persistence, results, and locking.

Single-table design:
    PK: execution_id
    SK: checkpoint/{step}_{event} | result | lock | latest

Requires boto3 and a DynamoDB table with the above key schema.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import boto3 to avoid hard dependency
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


class DynamoDBBackend:
    """
    Combined Persistence and Result backend using DynamoDB.
    
    Implements both PersistenceBackend and ResultBackend interfaces
    using a single-table design for simplicity.
    
    Table Schema:
        PK (String): execution_id
        SK (String): type (checkpoint/{step}_{event}, result, latest)
        data (Binary/String): JSON-encoded payload
        ttl (Number): Unix timestamp for TTL expiration
    
    Args:
        table_name: DynamoDB table name
        region: AWS region (optional, uses default if not specified)
        ttl_days: Days until items expire (default: 7, 0 = no TTL)
    """
    
    def __init__(
        self,
        table_name: str = "flatagents",
        region: Optional[str] = None,
        ttl_days: int = 7
    ):
        self.table_name = table_name
        self.ttl_days = ttl_days
        
        boto3 = _get_boto3()
        if region:
            self._resource = boto3.resource("dynamodb", region_name=region)
        else:
            self._resource = boto3.resource("dynamodb")
        
        self._table = self._resource.Table(table_name)
    
    def _ttl_timestamp(self) -> Optional[int]:
        """Calculate TTL timestamp if TTL is enabled."""
        if self.ttl_days <= 0:
            return None
        return int(datetime.now(timezone.utc).timestamp()) + (self.ttl_days * 86400)
    
    # =========================================================================
    # PersistenceBackend Interface
    # =========================================================================
    
    async def save(self, key: str, value: bytes) -> None:
        """Save checkpoint data."""
        # Key format: {execution_id}/step_{step}_{event}
        parts = key.split("/", 1)
        pk = parts[0]
        sk = f"checkpoint/{parts[1]}" if len(parts) > 1 else "checkpoint/latest"
        
        item = {
            "pk": pk,
            "sk": sk,
            "data": value.decode("utf-8"),  # Store as string for readability
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        ttl = self._ttl_timestamp()
        if ttl:
            item["ttl"] = ttl
        
        await asyncio.to_thread(self._table.put_item, Item=item)
        logger.debug(f"DynamoDB: saved checkpoint {pk}/{sk}")
    
    async def load(self, key: str) -> Optional[bytes]:
        """Load checkpoint data."""
        parts = key.split("/", 1)
        pk = parts[0]
        sk = f"checkpoint/{parts[1]}" if len(parts) > 1 else "checkpoint/latest"
        
        response = await asyncio.to_thread(
            self._table.get_item,
            Key={"pk": pk, "sk": sk}
        )
        
        item = response.get("Item")
        if not item:
            return None
        
        return item["data"].encode("utf-8")
    
    async def delete(self, key: str) -> None:
        """Delete checkpoint data."""
        parts = key.split("/", 1)
        pk = parts[0]
        sk = f"checkpoint/{parts[1]}" if len(parts) > 1 else "checkpoint/latest"
        
        await asyncio.to_thread(
            self._table.delete_item,
            Key={"pk": pk, "sk": sk}
        )
    
    async def list(self, prefix: str) -> List[str]:
        """List all keys matching prefix."""
        # prefix format: {execution_id}/
        pk = prefix.rstrip("/")
        
        response = await asyncio.to_thread(
            self._table.query,
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": pk,
                ":prefix": "checkpoint/"
            }
        )
        
        # Convert back to original key format
        keys = []
        for item in response.get("Items", []):
            sk = item["sk"]
            if sk.startswith("checkpoint/"):
                keys.append(f"{pk}/{sk[11:]}")  # Remove "checkpoint/" prefix
        
        return sorted(keys)
    
    # =========================================================================
    # ResultBackend Interface
    # =========================================================================
    
    async def write(self, uri: str, data: Any) -> None:
        """Write result to a URI."""
        from ..backends import parse_uri
        
        execution_id, path = parse_uri(uri)
        
        item = {
            "pk": execution_id,
            "sk": path,  # Usually "result"
            "data": json.dumps(data),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        ttl = self._ttl_timestamp()
        if ttl:
            item["ttl"] = ttl
        
        await asyncio.to_thread(self._table.put_item, Item=item)
        logger.debug(f"DynamoDB: wrote result {execution_id}/{path}")
    
    async def read(
        self,
        uri: str,
        block: bool = True,
        timeout: Optional[float] = None
    ) -> Any:
        """Read result from a URI, optionally blocking until available."""
        from ..backends import parse_uri
        
        execution_id, path = parse_uri(uri)
        
        start_time = datetime.now(timezone.utc).timestamp()
        poll_interval = 0.5  # seconds
        
        while True:
            response = await asyncio.to_thread(
                self._table.get_item,
                Key={"pk": execution_id, "sk": path}
            )
            
            item = response.get("Item")
            if item:
                return json.loads(item["data"])
            
            if not block:
                return None
            
            # Check timeout
            if timeout:
                elapsed = datetime.now(timezone.utc).timestamp() - start_time
                if elapsed >= timeout:
                    raise TimeoutError(f"Timeout waiting for result at {uri}")
            
            # Poll with exponential backoff (capped at 5s)
            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 5.0)
    
    async def exists(self, uri: str) -> bool:
        """Check if result exists at URI."""
        from ..backends import parse_uri
        
        execution_id, path = parse_uri(uri)
        
        response = await asyncio.to_thread(
            self._table.get_item,
            Key={"pk": execution_id, "sk": path},
            ProjectionExpression="pk"  # Only fetch key to minimize data
        )
        
        return "Item" in response
    
    async def delete(self, uri: str) -> None:
        """Delete result at URI."""
        from ..backends import parse_uri
        
        execution_id, path = parse_uri(uri)
        
        await asyncio.to_thread(
            self._table.delete_item,
            Key={"pk": execution_id, "sk": path}
        )


class DynamoDBLock:
    """
    Distributed execution lock using DynamoDB conditional writes.
    
    Uses conditional PutItem to atomically acquire locks and TTL
    for automatic lease expiration (prevents deadlocks from crashed processes).
    
    Lock Schema (in same table as DynamoDBBackend):
        PK: execution_id
        SK: "lock"
        holder: Unique identifier for lock holder
        ttl: Unix timestamp for lease expiration
    
    Args:
        table_name: DynamoDB table name
        region: AWS region (optional)
        lease_seconds: Lock lease duration (default: 300 = 5 min)
    """
    
    def __init__(
        self,
        table_name: str = "flatagents",
        region: Optional[str] = None,
        lease_seconds: int = 300
    ):
        self.table_name = table_name
        self.lease_seconds = lease_seconds
        
        boto3 = _get_boto3()
        if region:
            self._resource = boto3.resource("dynamodb", region_name=region)
        else:
            self._resource = boto3.resource("dynamodb")
        
        self._table = self._resource.Table(table_name)
        
        # Generate unique holder ID for this process
        import uuid
        self._holder_id = str(uuid.uuid4())
    
    def _lease_expiry(self) -> int:
        """Calculate lease expiration timestamp."""
        return int(datetime.now(timezone.utc).timestamp()) + self.lease_seconds
    
    async def acquire(self, key: str) -> bool:
        """
        Attempt to acquire lock for the given key.
        
        Uses conditional write to ensure atomicity:
        - Succeeds if lock doesn't exist
        - Succeeds if existing lock has expired (TTL < now)
        - Fails if lock held by another process
        
        Returns True if lock acquired, False otherwise.
        """
        now = int(datetime.now(timezone.utc).timestamp())
        
        try:
            await asyncio.to_thread(
                self._table.put_item,
                Item={
                    "pk": key,
                    "sk": "lock",
                    "holder": self._holder_id,
                    "ttl": self._lease_expiry(),
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                },
                ConditionExpression=(
                    "attribute_not_exists(pk) OR "
                    "attribute_not_exists(sk) OR "
                    "#ttl < :now OR "
                    "holder = :holder"
                ),
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":now": now,
                    ":holder": self._holder_id
                }
            )
            logger.info(f"DynamoDB: acquired lock for {key}")
            return True
            
        except self._resource.meta.client.exceptions.ConditionalCheckFailedException:
            logger.debug(f"DynamoDB: failed to acquire lock for {key} (held by another)")
            return False
        except Exception as e:
            logger.error(f"DynamoDB: error acquiring lock for {key}: {e}")
            return False
    
    async def release(self, key: str) -> None:
        """
        Release lock for the given key.
        
        Only releases if we are the current holder (prevents releasing
        someone else's lock if ours expired).
        """
        try:
            await asyncio.to_thread(
                self._table.delete_item,
                Key={"pk": key, "sk": "lock"},
                ConditionExpression="holder = :holder",
                ExpressionAttributeValues={":holder": self._holder_id}
            )
            logger.debug(f"DynamoDB: released lock for {key}")
            
        except self._resource.meta.client.exceptions.ConditionalCheckFailedException:
            # We don't hold this lock anymore (expired or never held)
            logger.debug(f"DynamoDB: lock for {key} not held by us, skipping release")
        except Exception as e:
            logger.warning(f"DynamoDB: error releasing lock for {key}: {e}")
    
    async def renew(self, key: str) -> bool:
        """
        Renew lock lease (extend TTL).
        
        Call periodically during long operations to prevent lock expiration.
        Returns True if renewal succeeded, False if lock was lost.
        """
        try:
            await asyncio.to_thread(
                self._table.update_item,
                Key={"pk": key, "sk": "lock"},
                UpdateExpression="SET #ttl = :ttl",
                ConditionExpression="holder = :holder",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":ttl": self._lease_expiry(),
                    ":holder": self._holder_id
                }
            )
            logger.debug(f"DynamoDB: renewed lock for {key}")
            return True
            
        except self._resource.meta.client.exceptions.ConditionalCheckFailedException:
            logger.warning(f"DynamoDB: failed to renew lock for {key} (lost lock)")
            return False
