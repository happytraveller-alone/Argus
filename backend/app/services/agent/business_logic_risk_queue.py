"""
Business Logic risk queue service for managing BusinessLogicReconAgent risk points.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RedisBusinessLogicRiskQueue:
    """Redis-based Business Logic risk queue."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.queue_key_prefix = "bl_risk_queue"
        self.stats_key_prefix = "bl_risk_queue_stats"
        self.seen_key_prefix = "bl_risk_queue_seen"

    def _queue_key(self, task_id: str) -> str:
        return f"{self.queue_key_prefix}:{task_id}"

    def _stats_key(self, task_id: str) -> str:
        return f"{self.stats_key_prefix}:{task_id}"

    def _seen_key(self, task_id: str) -> str:
        return f"{self.seen_key_prefix}:{task_id}"

    @staticmethod
    def _fingerprint(risk_point: Dict[str, Any]) -> str:
        file_path = str(risk_point.get("file_path") or "").strip().lower()
        line_start = int(risk_point.get("line_start") or 0)
        vuln_type = str(risk_point.get("vulnerability_type") or risk_point.get("description") or "").strip().lower()
        return f"{file_path}|{line_start}|{vuln_type}"

    def enqueue(self, task_id: str, risk_point: Dict[str, Any]) -> bool:
        try:
            queue_key = self._queue_key(task_id)
            stats_key = self._stats_key(task_id)
            seen_key = self._seen_key(task_id)

            fp = self._fingerprint(risk_point)
            if not fp:
                return False
            if self.redis.sadd(seen_key, fp) == 0:
                self.redis.hincrby(stats_key, "total_deduplicated", 1)
            self.redis.rpush(queue_key, json.dumps(risk_point, ensure_ascii=False))
            self.redis.hincrby(stats_key, "total_enqueued", 1)
            self.redis.hset(stats_key, "last_enqueue_time", datetime.now(timezone.utc).isoformat())
            logger.info("[BLRiskQueue] Enqueued risk point %s for task %s", risk_point.get("file_path"), task_id)
            return True
        except Exception as exc:
            logger.error("[BLRiskQueue] Enqueue failed: %s", exc)
            return False

    def enqueue_batch(self, task_id: str, risk_points: List[Dict[str, Any]]) -> int:
        """批量入队多个业务逻辑风险点，使用 pipeline 提升效率。返回成功入队的数量。"""
        if not risk_points:
            return 0
        try:
            queue_key = self._queue_key(task_id)
            stats_key = self._stats_key(task_id)
            seen_key = self._seen_key(task_id)

            serialized: List[str] = []
            dedup_count = 0
            for risk_point in risk_points:
                fp = self._fingerprint(risk_point)
                if not fp:
                    continue
                if self.redis.sadd(seen_key, fp) == 0:
                    dedup_count += 1
                serialized.append(json.dumps(risk_point, ensure_ascii=False))

            count = len(serialized)
            if count > 0:
                pipe = self.redis.pipeline()
                pipe.rpush(queue_key, *serialized)
                pipe.hincrby(stats_key, "total_enqueued", count)
                if dedup_count > 0:
                    pipe.hincrby(stats_key, "total_deduplicated", dedup_count)
                pipe.hset(stats_key, "last_enqueue_time", datetime.now(timezone.utc).isoformat())
                pipe.execute()
            logger.info("[BLRiskQueue] Batch enqueued %d risk points for task %s", count, task_id)
            return count
        except Exception as exc:
            logger.error("[BLRiskQueue] Batch enqueue failed: %s", exc)
            return 0

    def dequeue(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            queue_key = self._queue_key(task_id)
            stats_key = self._stats_key(task_id)
            raw = self.redis.lpop(queue_key)
            if raw is None:
                return None
            self.redis.hincrby(stats_key, "total_dequeued", 1)
            self.redis.hset(stats_key, "last_dequeue_time", datetime.now(timezone.utc).isoformat())
            return json.loads(raw)
        except Exception as exc:
            logger.error("[BLRiskQueue] Dequeue failed: %s", exc)
            return None

    def peek(self, task_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            queue_key = self._queue_key(task_id)
            items = self.redis.lrange(queue_key, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as exc:
            logger.error("[BLRiskQueue] Peek failed: %s", exc)
            return []

    def size(self, task_id: str) -> int:
        try:
            return int(self.redis.llen(self._queue_key(task_id)))
        except Exception as exc:
            logger.error("[BLRiskQueue] Size failed: %s", exc)
            return 0

    def stats(self, task_id: str) -> Dict[str, Any]:
        try:
            stats_raw = self.redis.hgetall(self._stats_key(task_id))
            return {
                "current_size": self.size(task_id),
                "total_enqueued": int(stats_raw.get(b"total_enqueued", 0)),
                "total_dequeued": int(stats_raw.get(b"total_dequeued", 0)),
                "total_deduplicated": int(stats_raw.get(b"total_deduplicated", 0)),
                "last_enqueue_time": stats_raw.get(b"last_enqueue_time"),
                "last_dequeue_time": stats_raw.get(b"last_dequeue_time"),
            }
        except Exception as exc:
            logger.error("[BLRiskQueue] Stats failed: %s", exc)
            return {"current_size": 0}

    def contains(self, task_id: str, risk_point: Dict[str, Any]) -> bool:
        try:
            seen_key = self._seen_key(task_id)
            fp = self._fingerprint(risk_point)
            return bool(fp and self.redis.sismember(seen_key, fp))
        except Exception as exc:
            logger.error("[BLRiskQueue] Contains check failed: %s", exc)
            return False

    def clear(self, task_id: str) -> bool:
        try:
            self.redis.delete(self._queue_key(task_id))
            self.redis.delete(self._stats_key(task_id))
            self.redis.delete(self._seen_key(task_id))
            logger.info("[BLRiskQueue] Cleared queue for %s", task_id)
            return True
        except Exception as exc:
            logger.error("[BLRiskQueue] Clear failed: %s", exc)
            return False


class InMemoryBusinessLogicRiskQueue:
    """In-memory Business Logic risk queue."""

    def __init__(self):
        self.queues: Dict[str, List[Dict[str, Any]]] = {}
        self._stats: Dict[str, Dict[str, Any]] = {}
        self.seen: Dict[str, set] = {}

    def _ensure_task(self, task_id: str):
        if task_id not in self.queues:
            self.queues[task_id] = []
            self._stats[task_id] = {
                "total_enqueued": 0,
                "total_dequeued": 0,
                "total_deduplicated": 0,
                "last_enqueue_time": None,
                "last_dequeue_time": None,
            }
            self.seen[task_id] = set()

    @staticmethod
    def _fingerprint(risk_point: Dict[str, Any]) -> str:
        file_path = str(risk_point.get("file_path") or "").strip().lower()
        line_start = int(risk_point.get("line_start") or 0)
        vuln_type = str(risk_point.get("vulnerability_type") or risk_point.get("description") or "").strip().lower()
        return f"{file_path}|{line_start}|{vuln_type}"

    def enqueue(self, task_id: str, risk_point: Dict[str, Any]) -> bool:
        try:
            self._ensure_task(task_id)
            fp = self._fingerprint(risk_point)
            if not fp:
                return False
            if fp in self.seen[task_id]:
                self._stats[task_id]["total_deduplicated"] += 1
            else:
                self.seen[task_id].add(fp)
            self.queues[task_id].append(risk_point)
            self._stats[task_id]["total_enqueued"] += 1
            self._stats[task_id]["last_enqueue_time"] = datetime.now(timezone.utc).isoformat()
            return True
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory enqueue failed: %s", exc)
            return False

    def enqueue_batch(self, task_id: str, risk_points: List[Dict[str, Any]]) -> int:
        """批量入队多个业务逻辑风险点。返回成功入队的数量。"""
        count = 0
        for risk_point in risk_points:
            if self.enqueue(task_id, risk_point):
                count += 1
        return count

    def dequeue(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            self._ensure_task(task_id)
            if not self.queues[task_id]:
                return None
            item = self.queues[task_id].pop(0)
            self._stats[task_id]["total_dequeued"] += 1
            self._stats[task_id]["last_dequeue_time"] = datetime.now(timezone.utc).isoformat()
            return item
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory dequeue failed: %s", exc)
            return None

    def peek(self, task_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            self._ensure_task(task_id)
            return self.queues[task_id][:limit]
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory peek failed: %s", exc)
            return []

    def size(self, task_id: str) -> int:
        try:
            self._ensure_task(task_id)
            return len(self.queues[task_id])
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory size failed: %s", exc)
            return 0

    def stats(self, task_id: str) -> Dict[str, Any]:
        try:
            self._ensure_task(task_id)
            data = dict(self._stats[task_id])
            data["current_size"] = len(self.queues[task_id])
            return data
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory stats failed: %s", exc)
            return {"current_size": 0}

    def contains(self, task_id: str, risk_point: Dict[str, Any]) -> bool:
        try:
            self._ensure_task(task_id)
            fp = self._fingerprint(risk_point)
            return fp in self.seen[task_id]
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory contains failed: %s", exc)
            return False

    def clear(self, task_id: str) -> bool:
        try:
            self._ensure_task(task_id)
            self.queues[task_id].clear()
            self._stats[task_id] = {
                "total_enqueued": 0,
                "total_dequeued": 0,
                "total_deduplicated": 0,
                "last_enqueue_time": None,
                "last_dequeue_time": None,
            }
            self.seen[task_id].clear()
            return True
        except Exception as exc:
            logger.error("[BLRiskQueue] InMemory clear failed: %s", exc)
            return False
