"""Optional metrics collection for Roundtable MCP Server.

This module is OPTIONAL and disabled by default.
Enable with CLI_MCP_METRICS=true environment variable.
"""
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetric:
    """Metrics for a single agent execution."""
    agent: str
    timestamp: str
    duration_seconds: float
    success: bool
    error: Optional[str] = None
    message_count: int = 0
    tool_uses: int = 0
    session_id: Optional[str] = None


class MetricsCollector:
    """Collects and stores execution metrics."""
    
    def __init__(self, enabled: bool = False, storage_path: Optional[Path] = None):
        self.enabled = enabled
        self.storage_path = storage_path or Path.home() / ".roundtable" / "metrics.jsonl"
        self.metrics: List[ExecutionMetric] = []
        
        if self.enabled:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Metrics collection enabled: {self.storage_path}")
    
    @contextmanager
    def track_execution(self, agent: str, session_id: Optional[str] = None):
        """Context manager to track agent execution time.
        
        Usage:
            with metrics.track_execution("codex"):
                # Execute agent
                pass
        """
        if not self.enabled:
            yield None
            return
        
        start_time = time.time()
        metric = ExecutionMetric(
            agent=agent,
            timestamp=datetime.now().isoformat(),
            duration_seconds=0.0,
            success=False,
            session_id=session_id
        )
        
        try:
            yield metric
            metric.success = True
        except Exception as e:
            metric.error = str(e)
            raise
        finally:
            metric.duration_seconds = time.time() - start_time
            self.record(metric)
    
    def record(self, metric: ExecutionMetric):
        """Record a metric."""
        if not self.enabled:
            return
        
        self.metrics.append(metric)
        
        # Append to file
        try:
            with open(self.storage_path, 'a') as f:
                f.write(json.dumps(asdict(metric)) + '\n')
        except Exception as e:
            logger.warning(f"Failed to write metric: {e}")
    
    def get_stats(self) -> Dict:
        """Get aggregated statistics."""
        if not self.metrics:
            return {}
        
        stats = {
            "total_executions": len(self.metrics),
            "successful": sum(1 for m in self.metrics if m.success),
            "failed": sum(1 for m in self.metrics if not m.success),
            "by_agent": {},
            "avg_duration": sum(m.duration_seconds for m in self.metrics) / len(self.metrics)
        }
        
        # Per-agent stats
        for metric in self.metrics:
            if metric.agent not in stats["by_agent"]:
                stats["by_agent"][metric.agent] = {
                    "count": 0,
                    "success": 0,
                    "failed": 0,
                    "avg_duration": 0.0
                }
            
            agent_stats = stats["by_agent"][metric.agent]
            agent_stats["count"] += 1
            if metric.success:
                agent_stats["success"] += 1
            else:
                agent_stats["failed"] += 1
        
        # Calculate averages
        for agent, agent_stats in stats["by_agent"].items():
            agent_metrics = [m for m in self.metrics if m.agent == agent]
            agent_stats["avg_duration"] = sum(m.duration_seconds for m in agent_metrics) / len(agent_metrics)
        
        return stats
    
    def export_json(self, path: Path):
        """Export metrics to JSON file."""
        if not self.enabled:
            logger.warning("Metrics not enabled, nothing to export")
            return
        
        with open(path, 'w') as f:
            json.dump({
                "metrics": [asdict(m) for m in self.metrics],
                "stats": self.get_stats()
            }, f, indent=2)
        
        logger.info(f"Metrics exported to {path}")


# Global metrics collector (disabled by default)
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create global metrics collector."""
    global _metrics_collector
    
    if _metrics_collector is None:
        import os
        enabled = os.getenv("CLI_MCP_METRICS", "false").lower() in ("true", "1", "yes")
        _metrics_collector = MetricsCollector(enabled=enabled)
    
    return _metrics_collector


def track_execution(agent: str, session_id: Optional[str] = None):
    """Convenience wrapper around MetricsCollector.track_execution."""
    return get_metrics_collector().track_execution(agent, session_id)
